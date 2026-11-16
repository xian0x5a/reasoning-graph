"""The page marks the strongest challenge to a claim: a score-5 contradiction (÷5) or a rule-out."""

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

from reasoning_graph.mermaid import to_mermaid
from reasoning_graph.page import html_document
from reasoning_graph.validation import validate_state

RENDER_MODES = ("mermaid", "offline")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT, text=True, capture_output=True,
    )


def edge(source: str, target: str, edge_type: str, **extra) -> dict:
    return {"from": source, "to": target, "type": edge_type, **extra}


def state_with(*edges: dict, factors: list | None = None) -> dict:
    state = {
        "summary": {"answer": "CS1"},
        "nodes": [
            {"id": "G1", "type": "goal", "text": "Who did it?"},
            *({"id": f"O{i}", "type": "observation", "text": f"Observation {i}", "source": "case.txt"} for i in (1, 2, 3)),
            {"id": "H1", "type": "hypothesis", "text": "A hypothesis"},
            {"id": "CS1", "type": "candidate_solution", "text": "The answer", "answer_kind": "exact_answer"},
        ],
        "edges": [edge("H1", "CS1", "premise_of"), edge("CS1", "G1", "answers"), *edges],
    }
    if factors:
        state["factors"] = factors
    assert validate_state(state).ok
    return state


def claim_contradiction_state() -> dict:
    """H2, a claim, contradicts H1 at score 5."""
    state = state_with()
    state["nodes"].append({"id": "H2", "type": "hypothesis", "text": "A rival hypothesis"})
    state["edges"].append(edge("H2", "H1", "contradicts", score=5))
    assert validate_state(state).ok
    return state


def card(document: str, node_id: str) -> str:
    """The card's visible text: tags dropped, entities decoded."""
    markup = re.search(rf'<article class="detail-card[^"]*"[^>]* id="details-{node_id}".*?</article>', document, re.DOTALL)[0]
    return html.unescape(re.sub(r"<[^>]+>", "", markup))


def node_label(mermaid: str, node_id: str) -> str:
    return re.search(rf'^\s+{node_id}\["(.*?)"\]', mermaid, re.MULTILINE)[1]


@pytest.mark.parametrize("render_mode", RENDER_MODES)
def test_an_ungrouped_score_five_contradiction_marks_the_claim(render_mode: str) -> None:
    state = state_with(edge("O1", "H1", "contradicts", score=5))
    mermaid = to_mermaid(state)
    document = html_document(state, mermaid, render_mode=render_mode)

    assert "÷5 by O1" in node_label(mermaid, "H1")
    assert "÷5 by O1" in document
    assert "Strongest against: ÷5 by O1" in card(document, "H1")
    assert "÷5 by" not in node_label(mermaid, "CS1")


def test_a_score_five_factors_group_marks_the_claim_with_the_groups_sources() -> None:
    state = state_with(
        edge("O1", "H1", "contradicts"), edge("O2", "H1", "contradicts"),
        factors=[{"id": "F1", "edges": ["O1-H1", "O2-H1"], "score": 5}],
    )
    mermaid = to_mermaid(state)
    marked = re.search(r"÷5 by ([^\"]*)", node_label(mermaid, "H1"))

    assert marked and "O1" in marked[1] and "O2" in marked[1]
    assert re.search(r"Strongest against: ÷5 by [^<]*O1[^<]*O2|Strongest against: ÷5 by [^<]*O2[^<]*O1",
                     card(html_document(state, mermaid), "H1"))


@pytest.mark.parametrize("render_mode", RENDER_MODES)
@pytest.mark.parametrize("contradiction", [
    edge("O1", "H1", "contradicts", score=4),
    # A claim source divides by less than its score says, scaled by its own belief.
    edge("CS1", "H1", "contradicts", score=5),
], ids=["score-four", "claim-source"])
def test_a_contradiction_below_the_top_score_or_from_a_claim_gives_no_mark(render_mode: str, contradiction: dict) -> None:
    state = state_with(contradiction) if contradiction["from"] != "CS1" else claim_contradiction_state()
    mermaid = to_mermaid(state)
    document = html_document(state, mermaid, render_mode=render_mode)

    assert "÷5 by" not in mermaid + document
    assert "Strongest against" not in document


@pytest.mark.parametrize("render_mode", RENDER_MODES)
def test_a_ruled_out_claim_shows_the_rule_out_instead_of_the_contradiction(render_mode: str) -> None:
    state = state_with(edge("O1", "H1", "contradicts", score=5), edge("O2", "H1", "rules_out"))
    mermaid = to_mermaid(state)
    document = html_document(state, mermaid, render_mode=render_mode)

    assert "ruled out by O2" in node_label(mermaid, "H1")
    assert "ruled out by O2" in document
    assert "÷5 by" not in node_label(mermaid, "H1")
    assert "÷5 by" not in card(document, "H1")


def test_the_mark_never_reaches_record_or_audit_output() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        state_path = Path(tmp_dir, "state.json")
        state_path.write_text(json.dumps(state_with(edge("O1", "H1", "contradicts", score=5), edge("O2", "CS1", "rules_out"))), encoding="utf-8")

        for command in (("audit", str(state_path)), ("refresh", str(state_path))):
            result = run_cli(*command)
            shown = result.stdout + result.stderr
            assert "÷5" not in shown and "ruled out by" not in shown and "Strongest against" not in shown
        assert "÷5" not in state_path.with_suffix(".index.md").read_text(encoding="utf-8")
