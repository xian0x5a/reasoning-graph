"""`exclusive_sets`: claims of which at most one can be true. They change no belief; the page
lists them and flags a set whose members are each likelier than not."""

import re
import sys
from copy import deepcopy
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.mermaid import to_mermaid
from reasoning_graph.page import html_document
from reasoning_graph.validation import validate_state


def edge(source: str, target: str, edge_type: str = "supports") -> dict:
    return {"from": source, "to": target, "type": edge_type}


def state_with(supports: dict[str, int], members: list[str] | None = None, **set_extra) -> dict:
    """H1, H2, CS1 are claims; `supports` gives each claim's number of default supports (2x odds each)."""
    nodes = [
        {"id": "G1", "type": "goal", "text": "Who did it?"},
        {"id": "H1", "type": "hypothesis", "text": "First"},
        {"id": "H2", "type": "hypothesis", "text": "Second"},
        {"id": "CS1", "type": "candidate_solution", "text": "Third", "answer_kind": "exact_answer"},
    ]
    edges = [edge("CS1", "G1", "answers")]
    for claim, count in supports.items():
        for index in range(count):
            node_id = f"O{claim}{index}"
            nodes.append({"id": node_id, "type": "observation", "text": f"Clue {node_id}", "source": "case.txt"})
            edges.append(edge(node_id, claim))
    state = {"nodes": nodes, "edges": edges}
    if members:
        state["exclusive_sets"] = [{"id": "X1", "members": members, **set_extra}]
    return state


def exclusive_section(document: str) -> str:
    match = re.search(r'<section id="exclusive-sets-section">.*?</section>', document, re.DOTALL)
    assert match, "no Exclusive sets section"
    return match[0]


def test_a_valid_set_validates() -> None:
    assert validate_state(state_with({}, ["H1", "CS1"], note="one culprit")).ok


def test_invalid_sets_are_validation_errors() -> None:
    cases = {
        "single member": lambda s: s.update(exclusive_sets=[{"id": "X1", "members": ["H1"]}]),
        "duplicate members": lambda s: s.update(exclusive_sets=[{"id": "X1", "members": ["H1", "H1"]}]),
        "unknown member": lambda s: s.update(exclusive_sets=[{"id": "X1", "members": ["H1", "H9"]}]),
        "observation member": lambda s: s.update(exclusive_sets=[{"id": "X1", "members": ["H1", "OH10"]}]),
        "goal member": lambda s: s.update(exclusive_sets=[{"id": "X1", "members": ["H1", "G1"]}]),
        "duplicate set ids": lambda s: s.update(exclusive_sets=[
            {"id": "X1", "members": ["H1", "H2"]}, {"id": "X1", "members": ["H1", "CS1"]}]),
    }
    for name, break_state in cases.items():
        state = state_with({"H1": 1})
        break_state(state)
        assert not validate_state(state).ok, name


def test_a_set_changes_no_belief() -> None:
    plain = state_with({"H1": 3, "H2": 3})
    with_set = deepcopy(plain)
    with_set["exclusive_sets"] = [{"id": "X1", "members": ["H1", "H2"]}]

    def beliefs(state: dict) -> list[str]:
        return re.findall(r"Effective belief: [^<]+", html_document(state, to_mermaid(state)))

    assert beliefs(plain) == beliefs(with_set)
    assert beliefs(with_set)


def test_the_page_lists_members_with_beliefs_most_believed_first() -> None:
    state = state_with({"H1": 1, "H2": 3, "CS1": 2}, ["H1", "H2", "CS1"], note="one culprit")

    section = exclusive_section(html_document(state, to_mermaid(state)))

    assert "Exclusive sets" in section and "X1" in section and "one culprit" in section
    assert section.index("H2") < section.index("CS1") < section.index("H1")
    assert "89%" in section and "80%" in section and "67%" in section


def test_a_set_with_two_members_each_above_half_is_flagged() -> None:
    state = state_with({"H1": 2, "H2": 3}, ["H1", "H2"])

    document = html_document(state, to_mermaid(state))

    text = re.sub(r"<[^>]+>", "", document)
    assert re.search(r"Exclusive set X1: .*H1.*H2.* are each above 50%, but at most one of them can be true\.", text) or \
        re.search(r"Exclusive set X1: .*H2.*H1.* are each above 50%, but at most one of them can be true\.", text)


@pytest.mark.parametrize("supports,case", [
    ({"H1": 2, "H2": 0}, "only one member above 50%"),
    ({"H1": 0, "H2": 0}, "all members at exactly 50%"),
])
def test_no_flag_unless_two_members_are_above_half(supports: dict, case: str) -> None:
    state = state_with(supports, ["H1", "H2"])

    document = html_document(state, to_mermaid(state))

    assert "but at most one of them can be true" not in document, case
    assert "Exclusive sets" in document
