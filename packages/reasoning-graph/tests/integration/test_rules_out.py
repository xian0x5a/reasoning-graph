"""`rules_out`: an observation that eliminates a candidate or hypothesis outright."""

import html
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.index import index_document
from reasoning_graph.mermaid import to_mermaid
from reasoning_graph.page import html_document
from reasoning_graph.validation import validate_state


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT, text=True, capture_output=True,
    )


def edge(source: str, target: str, edge_type: str, **extra) -> dict:
    return {"from": source, "to": target, "type": edge_type, **extra}


def observation(node_id: str) -> dict:
    return {"id": node_id, "type": "observation", "text": f"Observation {node_id}", "source": "case.txt"}


def candidate(node_id: str) -> dict:
    return {"id": node_id, "type": "candidate_solution", "text": f"Candidate {node_id}", "answer_kind": "exact_answer"}


def base_state(answer: str = "CS1") -> dict:
    """H1 has three default supports (89%) and CS1 follows from it; CS2 is a rival with one support."""
    return {
        "summary": {"answer": answer},
        "nodes": [
            {"id": "G1", "type": "goal", "text": "Who did it?"},
            *(observation(f"O{i}") for i in range(1, 6)),
            {"id": "H1", "type": "hypothesis", "text": "A hypothesis"},
            candidate("CS1"),
            candidate("CS2"),
        ],
        "edges": [
            edge("O1", "H1", "supports"),
            edge("O2", "H1", "supports"),
            edge("O3", "H1", "supports"),
            edge("H1", "CS1", "premise_of"),
            edge("O4", "CS2", "supports"),
            edge("CS1", "G1", "answers"),
            edge("CS2", "G1", "answers"),
        ],
    }


def card(document: str, node_id: str) -> str:
    """The card's visible text: tags dropped, entities decoded."""
    match = re.search(rf'<article class="detail-card[^"]*"[^>]* id="details-{node_id}".*?</article>', document, re.DOTALL)
    assert match, f"no card for {node_id}"
    return html.unescape(re.sub(r"<[^>]+>", "", match[0]))


def case_part(document: str, heading: str) -> str:
    case = re.search(r'<section id="case-section".*?</section>', document, re.DOTALL)[0]
    match = re.search(rf'<h3>{heading}.*?(?=<div class="case-part">|<p class="case-empty">|$)', case, re.DOTALL)
    assert match, f"no {heading} part"
    return match[0]


def test_a_ruled_out_claim_is_below_one_percent_whatever_supports_it() -> None:
    state = base_state()
    state["edges"].append(edge("O5", "H1", "rules_out"))
    assert validate_state(state).ok

    document = html_document(state, to_mermaid(state))

    assert "Effective belief: 89%" not in card(document, "H1")
    assert "Effective belief: <1%" in card(document, "H1")


def test_a_claim_leading_from_a_ruled_out_premise_is_also_below_one_percent() -> None:
    state = base_state()
    state["edges"].append(edge("O5", "H1", "rules_out"))

    assert "Effective belief: <1%" in card(html_document(state, to_mermaid(state)), "CS1")


@pytest.mark.parametrize("target_type", ["hypothesis", "candidate_solution"])
def test_rules_out_is_allowed_from_an_observation_to_a_claim(target_type: str) -> None:
    state = base_state()
    target = "H1" if target_type == "hypothesis" else "CS2"
    state["edges"].append(edge("O5", target, "rules_out"))

    assert validate_state(state).ok


@pytest.mark.parametrize("source,target", [
    ("H1", "CS2"),   # a claim cannot rule out another
    ("CS2", "H1"),
    ("O5", "G1"),    # goal is not a claim
    ("O5", "O1"),    # observation target
    ("G1", "H1"),
])
def test_rules_out_between_other_endpoint_types_is_a_validation_error(source: str, target: str) -> None:
    state = base_state()
    state["edges"].append(edge(source, target, "rules_out"))

    assert not validate_state(state).ok


def test_rules_out_takes_no_score() -> None:
    state = base_state()
    state["edges"].append(edge("O5", "H1", "rules_out", score=5))

    assert not validate_state(state).ok


def test_rules_out_cannot_join_a_factors_group() -> None:
    state = base_state()
    state["edges"].append(edge("O5", "H1", "rules_out"))
    state["factors"] = [{"id": "F1", "edges": ["O5-H1", "O1-H1"], "score": 3}]

    assert not validate_state(state).ok


def test_record_and_audit_reject_a_misplaced_rules_out() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_path = Path(tmp_dir, "state.json")
        patch_path = Path(tmp_dir, "patch.json")
        assert run_cli("init", "--goal", "Who did it?", "-o", str(state_path)).returncode == 0
        before = state_path.read_text(encoding="utf-8")
        patch_path.write_text(json.dumps({
            "nodes": [observation("O1"), observation("O2")],
            "edges": [edge("O1", "O2", "rules_out")],
        }), encoding="utf-8")
        assert run_cli("record", str(state_path), "--patch", str(patch_path)).returncode == 1
        assert state_path.read_text(encoding="utf-8") == before

        bad_state = base_state()
        bad_state["edges"].append(edge("H1", "CS2", "rules_out"))
        state_path.write_text(json.dumps(bad_state), encoding="utf-8")
        assert run_cli("audit", str(state_path)).returncode == 1


@pytest.mark.parametrize("answer,ruled_out", [
    ("CS2", "CS2"),  # the answer itself
    ("CS1", "H1"),   # a premise the answer rests on
])
def test_audit_fails_an_answer_that_is_ruled_out_without_printing_belief(answer: str, ruled_out: str) -> None:
    # Both answers are evidence-grounded without the rule-out; a score 5 contradicts already
    # failed such an answer, so the stronger edge must not gate less.
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_path = Path(tmp_dir, "state.json")
        state = base_state(answer=answer)
        state["edges"].append(edge("O5", ruled_out, "rules_out"))
        state_path.write_text(json.dumps(state), encoding="utf-8")

        result = run_cli("audit", str(state_path))

        assert result.returncode == 1
        assert f"answer candidate {answer} is ruled out" in result.stderr
        assert not re.search(r"\d\s*%|belief", result.stdout + result.stderr)


def test_a_ruled_out_premise_caps_its_descendant_whatever_lifts_the_descendant() -> None:
    # A premise group would replace H1's cost with its joint score, and stacked supports
    # would multiply an inherited 0.001 back up; neither may lift CS1.
    state = base_state()
    state["nodes"].append({"id": "H2", "type": "hypothesis", "text": "Another premise"})
    state["nodes"].extend(observation(f"P{i}") for i in range(5))
    state["edges"] += [
        edge("O5", "H1", "rules_out"),
        edge("H2", "CS1", "premise_of"),
        *(edge(f"P{i}", "CS1", "supports", score=5) for i in range(5)),
    ]
    state["factors"] = [{"id": "F1", "edges": ["H1-CS1", "H2-CS1"], "score": 5}]
    assert validate_state(state).ok

    assert "Effective belief: <1%" in card(html_document(state, to_mermaid(state)), "CS1")


def test_a_ruled_out_hypothesis_is_not_listed_as_open_in_the_index() -> None:
    state = base_state()
    state["nodes"].append({"id": "H2", "type": "hypothesis", "text": "A rival hypothesis"})
    state["edges"].append(edge("O5", "H2", "rules_out"))

    open_section = index_document(state).split("## Open")[1].split("\n## ")[0]

    assert "H2" not in open_section


def test_rules_out_into_the_answers_why_tree_is_listed_against_it() -> None:
    state = base_state()
    state["edges"].append(edge("O5", "H1", "rules_out"))

    against = case_part(html_document(state, to_mermaid(state)), "Against it")

    assert "rules_out" in against and "O5" in against


def test_rules_out_into_a_rival_candidate_is_listed_under_rivals() -> None:
    state = base_state()
    state["edges"].append(edge("O5", "CS2", "rules_out"))
    document = html_document(state, to_mermaid(state))

    rivals = case_part(document, "Rivals")
    assert "rules_out" in rivals and "O5" in rivals
    assert "Against it" not in re.search(r'<section id="case-section".*?</section>', document, re.DOTALL)[0]
