"""The page header tells the reader what was asked before what was answered."""

import copy
import html
import re
import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.mermaid import to_mermaid
from reasoning_graph.page import html_document

STATE = {
    "summary": {"answer": "CS1"},
    "nodes": [
        {"id": "G1", "type": "goal", "text": "Who took the <key>?"},
        {"id": "O1", "type": "observation", "text": "The butler had the key", "source": "case.txt"},
        {"id": "CS1", "type": "candidate_solution", "text": "The butler", "answer_kind": "exact_answer"},
    ],
    "edges": [
        {"from": "O1", "to": "CS1", "type": "supports"},
        {"from": "CS1", "to": "G1", "type": "answers"},
    ],
}


def header(document: str) -> str:
    match = re.search(r'<header class="hero">.*?</header>', document, re.DOTALL)
    assert match, "the page has no header"
    return match[0]


def text_of(fragment: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def test_a_single_goal_is_the_page_heading_and_title() -> None:
    document = html_document(STATE, to_mermaid(STATE))

    heading = re.search(r"<h1>(.*?)</h1>", header(document), re.DOTALL)
    assert heading and text_of(heading[1]) == "Who took the <key>?"
    title = re.search(r"<title>(.*?)</title>", document)
    assert title and text_of(title[1]) == "Who took the <key>?"


def test_each_of_several_goals_is_named_in_the_header() -> None:
    state = copy.deepcopy(STATE)
    state["nodes"].append({"id": "G2", "type": "goal", "text": "When was the door opened?"})
    state["nodes"].append({"id": "CS2", "type": "candidate_solution", "text": "At nine", "answer_kind": "exact_answer"})
    state["edges"] += [{"from": "O1", "to": "CS2", "type": "supports"}, {"from": "CS2", "to": "G2", "type": "answers"}]
    state["summary"]["answer"] = "G1: CS1; G2: CS2"

    top = text_of(header(html_document(state, to_mermaid(state))))

    assert "Who took the <key>?" in top
    assert "When was the door opened?" in top


def test_the_status_badge_says_whether_the_answer_holds() -> None:
    def outcome(state: dict) -> str:
        match = re.search(r'<p class="status" data-outcome="([a-z]+)"', html_document(state, to_mermaid(state)))
        assert match, "the header has no status badge"
        return match[1]

    unanswered = copy.deepcopy(STATE)
    unanswered["summary"]["answer"] = ""
    failing = copy.deepcopy(STATE)
    failing["summary"]["answer"] = "CS9"

    assert outcome(STATE) == "pass"
    assert outcome(unanswered) == "open"
    assert outcome(failing) == "fail"
