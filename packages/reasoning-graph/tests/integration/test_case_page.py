"""The page leads with the case: a reader checks the answer before meeting the graph (#39)."""

import re
import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.mermaid import to_mermaid
from reasoning_graph.page import html_document

STATE = {
    "summary": {"answer": "CS1"},
    "nodes": [
        {"id": "G1", "type": "goal", "text": "Who took the key?"},
        {"id": "O1", "type": "observation", "text": "The butler had the key", "source": "case.txt", "quote": "The butler had <the> key."},
        {"id": "O2", "type": "observation", "text": "The gardener left at nine", "source": "case.txt"},
        {"id": "H1", "type": "hypothesis", "text": "The butler could open the door"},
        {"id": "T1", "type": "test", "text": "Check the lock", "not_run": "no access"},
        {"id": "CS1", "type": "candidate_solution", "text": "The butler"},
        {"id": "CS2", "type": "candidate_solution", "text": "The gardener"},
    ],
    "edges": [
        {"from": "O1", "to": "H1", "type": "supports", "score": 4},
        {"from": "H1", "to": "CS1", "type": "leads_to"},
        {"from": "H1", "to": "T1", "type": "prompts"},
        {"from": "O2", "to": "CS2", "type": "contradicts", "score": 5},
        {"from": "CS1", "to": "G1", "type": "answers"},
        {"from": "CS2", "to": "G1", "type": "answers"},
    ],
}

RENDER_MODES = ("mermaid", "offline")


def case_section(document: str) -> str:
    match = re.search(r'<section id="case-section".*?</section>', document, re.DOTALL)
    assert match, "the page has no case section"
    return match[0]


@pytest.mark.parametrize("render_mode", RENDER_MODES)
def test_the_case_comes_before_the_graph_and_the_details_start_closed(render_mode: str) -> None:
    document = html_document(STATE, to_mermaid(STATE), render_mode=render_mode)

    assert document.index('id="case-section"') < document.index('id="section-audit-graph"') < document.index('id="node-details-section"')
    details = re.search(r'<section id="node-details-section">\s*<details[^>]*>', document)
    assert details and " open" not in details[0]


@pytest.mark.parametrize("render_mode", RENDER_MODES)
def test_every_id_in_the_case_opens_its_node_card(render_mode: str) -> None:
    document = html_document(STATE, to_mermaid(STATE), render_mode=render_mode)
    case = case_section(document)

    linked = set(re.findall(r'href="#(details-[^"]+)"', case))

    card_ids = set(re.findall(r'<article class="detail-card[^"]*"[^>]* id="([^"]+)"', document))
    assert linked == {f"details-{node_id}" for node_id in ("CS1", "H1", "O1", "T1", "CS2", "O2")}
    assert linked <= card_ids


def test_the_case_shows_each_part_with_quotes_escaped() -> None:
    case = case_section(html_document(STATE, to_mermaid(STATE)))

    for heading in ("Why believe it", "Tests", "Rivals", "Weak spots"):
        assert f">{heading}" in case
    assert "The butler had &lt;the&gt; key." in case
    assert "no access" in case


def test_empty_parts_of_the_case_share_one_line() -> None:
    state = {**STATE, "edges": [edge for edge in STATE["edges"] if edge["type"] != "prompts"]}
    case = case_section(html_document(state, to_mermaid(state)))

    headings = re.findall(r"<h3>([^<]+)", case)
    assert [heading.strip() for heading in headings] == ["Why believe it", "Rivals", "Weak spots"]
    empty = re.search(r'<p class="case-empty">(.*?)</p>', case)
    assert empty and empty[1] == "Nothing against it · No tests"


def test_no_case_is_shown_while_no_answer_is_claimed() -> None:
    state = {**STATE, "summary": {}}

    assert 'id="case-section"' not in html_document(state, to_mermaid(state))


def node_card(document: str, node_id: str) -> str:
    match = re.search(rf'<article class="detail-card[^"]*"[^>]* id="details-{node_id}".*?</article>', document, re.DOTALL)
    assert match, f"no card for {node_id}"
    return match[0]


def test_a_card_shows_the_prior_a_claim_starts_from_even_by_default() -> None:
    document = html_document(STATE, to_mermaid(STATE))

    # H1 has no score: it starts from the hypothesis default, 50%.
    assert "Prior: 50%" in node_card(document, "H1")
    # CS1 takes its belief from its premise H1, so no prior of its own applies.
    assert "Prior:" not in node_card(document, "CS1")


def test_the_case_shows_how_far_each_piece_of_evidence_moves_its_claim() -> None:
    state = {**STATE, "edges": [*STATE["edges"], {"from": "O2", "to": "H1", "type": "supports"}]}
    case = case_section(html_document(state, to_mermaid(state)))

    # Score 4 multiplies the odds by 3, the unscored default by 2; contradicting score 5 divides them by 5.
    # The premise H1 → CS1 is not evidence and carries no weight.
    assert sorted(re.findall(r'<span class="case-weight">([^<]+)</span>', case)) == ["×2", "×3", "÷5"]
    assert "score" not in case
