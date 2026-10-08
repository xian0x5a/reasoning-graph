"""The case for the claimed answer: the argument a reader checks, taken from the graph alone."""

import sys
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.case import answer_cases


def edge(source: str, edge_type: str, target: str, **fields) -> dict:
    return {"from": source, "to": target, "type": edge_type, **fields}


def observation(node_id: str, quote: str | None = "said so") -> dict:
    node = {"id": node_id, "type": "observation", "text": f"{node_id} text", "source": "notes.txt"}
    if quote is not None:
        node["quote"] = quote
    return node


def hypothesis(node_id: str, **fields) -> dict:
    return {"id": node_id, "type": "hypothesis", "text": f"{node_id} text", **fields}


def candidate(node_id: str) -> dict:
    return {"id": node_id, "type": "candidate_solution", "text": f"{node_id} text"}


GOAL = {"id": "G1", "type": "goal", "text": "Who did it?"}


def case_of(state: dict):
    cases = answer_cases(state)
    assert len(cases) == 1
    return cases[0]


def outline(links) -> list:
    """Each link as (relation, node id, reference?, its own links), for readable asserts."""
    return [(link.relation, link.node.id, link.reference, outline(link.reasons)) for link in links]


def test_no_case_while_no_answer_is_claimed() -> None:
    state = {
        "nodes": [GOAL, observation("O1"), candidate("CS1")],
        "edges": [edge("O1", "supports", "CS1"), edge("CS1", "answers", "G1")],
    }

    assert answer_cases(state) == []


def test_why_walks_premises_and_support_down_to_observations_and_shows_a_shared_node_once() -> None:
    state = {
        "summary": {"answer": "CS1"},
        "nodes": [GOAL, observation("O1"), observation("O2"), hypothesis("H1"), hypothesis("H2"), candidate("CS1")],
        "edges": [
            edge("O1", "supports", "H1", score=4),
            edge("O1", "supports", "H2"),
            edge("O2", "supports", "H2"),
            edge("H1", "leads_to", "CS1"),
            edge("H2", "leads_to", "CS1"),
            edge("CS1", "answers", "G1"),
        ],
    }

    case = case_of(state)

    assert (case.goal.id, case.answer.id) == ("G1", "CS1")
    assert outline(case.why) == [
        ("leads_to", "H1", False, [("supports", "O1", False, [])]),
        ("leads_to", "H2", False, [("supports", "O1", True, []), ("supports", "O2", False, [])]),
    ]
    first_o1 = case.why[0].reasons[0]
    assert (first_o1.score, first_o1.node.source, first_o1.node.quote) == (4, "notes.txt", "said so")
    assert case.why[1].reasons[0].score is None


def test_a_grouped_edge_carries_the_group_and_its_score() -> None:
    state = {
        "summary": {"answer": "CS1"},
        "nodes": [GOAL, observation("O1"), observation("O2"), candidate("CS1")],
        "edges": [edge("O1", "supports", "CS1"), edge("O2", "supports", "CS1"), edge("CS1", "answers", "G1")],
        "factors": [{"id": "F1", "edges": ["O1-CS1", "O2-CS1"], "score": 4}],
    }

    why = case_of(state).why

    assert [(link.node.id, link.group, link.score) for link in why] == [("O1", "F1", 4), ("O2", "F1", 4)]


def test_against_holds_contradictions_of_the_answer_and_its_why_tree_but_not_of_rivals() -> None:
    state = {
        "summary": {"answer": "CS1"},
        "nodes": [GOAL, observation("O1"), observation("O2"), observation("O3"), observation("O4"), hypothesis("H1"), candidate("CS1"), candidate("CS2")],
        "edges": [
            edge("O1", "supports", "H1"),
            edge("H1", "leads_to", "CS1"),
            edge("O2", "contradicts", "CS1", score=2),
            edge("O3", "contradicts", "H1"),
            edge("O4", "contradicts", "CS2", score=5),
            edge("CS1", "answers", "G1"),
            edge("CS2", "answers", "G1"),
        ],
    }

    against = case_of(state).against

    assert [(item.target, item.node.id, item.score) for item in against] == [("CS1", "O2", 2), ("H1", "O3", None)]


def test_tests_of_the_why_tree_show_their_results_or_why_they_were_not_run() -> None:
    state = {
        "summary": {"answer": "CS1"},
        "nodes": [
            GOAL,
            observation("O1"),
            observation("O2"),
            hypothesis("H1"),
            {"id": "T1", "type": "test", "text": "check the stamp"},
            {"id": "T2", "type": "test", "text": "call the bank", "not_run": "no phone"},
            {"id": "T3", "type": "test", "text": "a test of a rival"},
            candidate("CS1"),
            candidate("CS2"),
        ],
        "edges": [
            # T1 is linked twice: prompted by H1, and its result O1 is part of the why-tree.
            edge("H1", "prompts", "T1"),
            edge("T1", "leads_to", "O1"),
            edge("O1", "supports", "H1"),
            edge("T2", "tests", "CS1"),
            edge("H1", "leads_to", "CS1"),
            edge("CS2", "prompts", "T3"),
            edge("T3", "leads_to", "O2"),
            edge("CS1", "answers", "G1"),
            edge("CS2", "answers", "G1"),
        ],
    }

    tests = case_of(state).tests

    assert [(test.node.id, [result.id for result in test.results], test.node.not_run) for test in tests] == [
        ("T1", ["O1"], None),
        ("T2", [], "no phone"),
    ]


def test_rivals_rank_by_belief_with_what_counts_against_each() -> None:
    state = {
        "summary": {"answer": "CS1"},
        "nodes": [GOAL, observation("O1"), observation("O2"), candidate("CS1"), candidate("CS2"), candidate("CS3")],
        "edges": [
            edge("O1", "contradicts", "CS2", score=5),
            edge("O2", "contradicts", "CS3", score=1),
            edge("CS1", "answers", "G1"),
            edge("CS2", "answers", "G1"),
            edge("CS3", "answers", "G1"),
        ],
    }

    rivals = case_of(state).rivals

    assert [rival.node.id for rival in rivals] == ["CS3", "CS2"]
    assert rivals[0].node.belief > rivals[1].node.belief
    assert [(item.node.id, item.score) for item in rivals[1].against] == [("O1", 5)]


def test_weak_spots_name_unrun_tests_unquoted_observations_and_claims_on_one_input() -> None:
    state = {
        "summary": {"answer": "CS1"},
        "nodes": [
            GOAL,
            observation("O1"),
            observation("O2", quote=None),
            observation("O3", quote=None),
            hypothesis("H1"),
            hypothesis("H2"),
            {"id": "T1", "type": "test", "text": "call the bank", "not_run": "no phone"},
            candidate("CS1"),
            candidate("CS2"),
        ],
        "edges": [
            edge("O1", "supports", "H1"),
            edge("O2", "supports", "H1"),
            edge("O1", "supports", "H2"),
            edge("H1", "leads_to", "CS1"),
            edge("H2", "leads_to", "CS1"),
            edge("H2", "prompts", "T1"),
            # Outside the why-tree: a rival's unquoted evidence is not a weak spot of the answer.
            edge("O3", "contradicts", "CS2"),
            edge("CS1", "answers", "G1"),
            edge("CS2", "answers", "G1"),
        ],
    }

    weak_spots = case_of(state).weak_spots

    # In outline order: the why-tree walk, then the tests.
    assert [(spot.kind, spot.node_id) for spot in weak_spots] == [
        ("no_quote", "O2"),
        ("single_input", "H2"),
        ("test_not_run", "T1"),
    ]
