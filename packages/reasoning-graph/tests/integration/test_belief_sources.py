"""Defaults and premises give every claim its starting belief; scores are written only on exceptions."""

import sys
from copy import deepcopy
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.costs import node_effective_truth_costs, probability_from_cost
from reasoning_graph.policy import sorted_report_candidates
from reasoning_graph.validation import validate_state


CLAIM_DEFAULTS = {"observation": 0.9, "hypothesis": 0.5, "candidate_solution": 0.5}
CLAIM_TABLE = {1: 0.1, 2: 0.3, 3: 0.5, 4: 0.7, 5: 0.9}
RATIO_TABLE = {1: 1.2, 2: 1.5, 3: 2, 4: 3, 5: 5}


def edge(source, target, relation="leads_to", **extra):
    return {"from": source, "to": target, "type": relation,
            **extra}


def claim_state(node_type="candidate_solution", **score):
    return {
        "nodes": [
            {"id": "G1", "type": "goal", "text": "Find the answer"},
            {"id": "N1", "type": node_type, "text": "The answer is 42",
             **({"answer_kind": "exact_answer"} if node_type == "candidate_solution" else {}), **score},
        ],
        "edges": [edge("N1", "G1", "answers")] if node_type == "candidate_solution" else [],
    }


def belief(state, node_id="N1"):
    return probability_from_cost(node_effective_truth_costs(state)[node_id])


@pytest.mark.parametrize("node_type,expected", sorted(CLAIM_DEFAULTS.items()))
def test_unscored_standalone_claim_takes_its_type_default(node_type, expected):
    state = claim_state(node_type)
    result = validate_state(state)
    assert result.ok, result.errors
    assert belief(state) == pytest.approx(expected)
    assert belief(state, "G1") == 1.0  # Objectives have no truth penalty.


@pytest.mark.parametrize("score,expected", sorted(CLAIM_TABLE.items()))
@pytest.mark.parametrize("node_type", sorted(CLAIM_DEFAULTS))
def test_claim_score_maps_through_one_table(node_type, score, expected):
    state = claim_state(node_type, score=score)
    assert validate_state(state).ok
    assert belief(state) == pytest.approx(expected)


@pytest.mark.parametrize("node_type", sorted(CLAIM_DEFAULTS))
def test_premise_backed_claim_adds_no_default_factor(node_type):
    # A default of 0.5 on every derived claim would halve belief at each step of a chain.
    state = claim_state(node_type)
    state["nodes"].extend([
        {"id": "A1", "type": "hypothesis", "text": "Premise", "score": 4},
        {"id": "D1", "type": "hypothesis", "text": "Intermediate conclusion"},
    ])
    state["edges"].extend([edge("A1", "D1"), edge("D1", "N1")])
    result = validate_state(state)
    assert result.ok, result.errors
    assert belief(state) == pytest.approx(0.7)

    # An explicit score on a premise-backed claim is a further local factor.
    state["nodes"][1]["score"] = 5
    assert validate_state(state).ok
    assert belief(state) == pytest.approx(0.63)


@pytest.mark.parametrize("source_type", ["goal", "constraint", "test"])
def test_scoreless_nonclaim_premise_leaves_the_default_in_place(source_type):
    state = claim_state()
    state["nodes"].append({"id": "S1", "type": source_type, "text": "Stipulation or action"})
    state["edges"].append(edge("S1", "N1"))
    result = validate_state(state)
    assert result.ok, result.errors
    assert belief(state) == pytest.approx(0.5)


@pytest.mark.parametrize("relation,expected", [("supports", 2 / 3), ("contradicts", 1 / 3)])
def test_unscored_evidence_edge_takes_the_default_ratio(relation, expected):
    state = claim_state()
    state["nodes"].append({"id": "E1", "type": "observation", "text": "Observation"})
    state["edges"].append(edge("E1", "N1", relation))
    assert validate_state(state).ok
    assert belief(state) == pytest.approx(expected)


@pytest.mark.parametrize("score,ratio", sorted(RATIO_TABLE.items()))
def test_evidence_score_maps_through_one_table_and_contradicts_uses_the_reciprocal(score, ratio):
    for relation, expected in (("supports", ratio / (1 + ratio)), ("contradicts", 1 / (1 + ratio))):
        state = claim_state()
        state["nodes"].append({"id": "E1", "type": "observation", "text": "Observation"})
        state["edges"].append(edge("E1", "N1", relation, score=score))
        assert validate_state(state).ok
        assert belief(state) == pytest.approx(expected)


def test_premise_group_replaces_the_default():
    state = claim_state()
    state["nodes"].extend([
        {"id": "S1", "type": "constraint", "text": "First condition"},
        {"id": "S2", "type": "constraint", "text": "Second condition"},
    ])
    state["edges"].extend([edge("S1", "N1"), edge("S2", "N1")])
    state["factors"] = [{"id": "F1", "edges": ["S1-N1", "S2-N1"], "score": 4}]
    result = validate_state(state)
    assert result.ok, result.errors
    assert belief(state) == pytest.approx(0.7)


def test_local_inference_score_matches_an_explicit_validity_assumption():
    state = claim_state("hypothesis", score=5)
    state["nodes"].append({"id": "E1", "type": "observation", "text": "Observation", "score": 4})
    state["edges"].append(edge("E1", "N1"))
    result = validate_state(state)
    assert result.ok, result.errors
    assert belief(state) == pytest.approx(0.63)

    del state["nodes"][1]["score"]
    state["nodes"].append({"id": "A1", "type": "hypothesis", "text": "Inference is valid", "score": 5})
    state["edges"].append(edge("A1", "N1"))
    assert validate_state(state).ok
    assert belief(state) == pytest.approx(0.63)


def test_candidate_ranking_uses_inherited_belief():
    state = claim_state()
    state["nodes"].extend([
        {"id": "O1", "type": "observation", "text": "Observed clue"},
        {"id": "CS2", "type": "candidate_solution", "text": "The answer is 43",
         "answer_kind": "exact_answer", "score": 4},
    ])
    state["edges"].extend([edge("O1", "N1"), edge("CS2", "G1", "answers")])
    assert validate_state(state).ok
    ranked = sorted_report_candidates(state)
    assert [(item["id"], item["belief"]) for item in ranked] == [("N1", 0.9), ("CS2", 0.7)]


def test_computed_belief_recalculates_without_writing_node_scores():
    state = claim_state()
    state["nodes"].extend([
        {"id": "E1", "type": "observation", "text": "Premise", "score": 4},
        {"id": "L1", "type": "observation", "text": "Independent observation"},
        {"id": "D1", "type": "hypothesis", "text": "Soft inference", "score": 5},
    ])
    state["edges"].extend([edge("E1", "D1"), edge("L1", "D1", "supports"), edge("D1", "N1")])
    original = deepcopy(state)
    assert validate_state(state).ok
    # Local 0.9 times inherited 0.7 gives 0.63; ratio 2 gives odds 126/37.
    assert belief(state) == pytest.approx(126 / 163)
    assert sorted_report_candidates(state)[0]["belief"] == pytest.approx(126 / 163, abs=1e-6)
    assert state == original

    state["nodes"][2]["score"] = 3
    updated = deepcopy(state)
    # Local 0.9 times inherited 0.5 gives 0.45; ratio 2 gives odds 18/11.
    assert belief(state) == pytest.approx(18 / 29)
    assert state == updated


def test_long_chain_keeps_a_finite_cost_after_an_evidence_update():
    # 400 premises at 0.1 put the base belief far below what a float holds.
    state = claim_state("hypothesis")
    premises = [{"id": f"P{index}", "type": "hypothesis", "text": "Unlikely premise", "score": 1} for index in range(400)]
    state["nodes"].extend([*premises, {"id": "E1", "type": "observation", "text": "Signal"}])
    state["edges"].extend([*(edge(premise["id"], "N1") for premise in premises), edge("E1", "N1", "supports", score=3)])

    assert validate_state(state).ok
    cost = node_effective_truth_costs(state)["N1"]
    assert cost == pytest.approx(400 * 2.302585092994046 - 0.6931471805599453)


def hypothesis_evidence_state(source_nodes, source_edges, relation, score):
    """N1 starts at 0.5; H2 bears evidence on it with the given relation and score."""
    state = claim_state()
    state["nodes"].extend(source_nodes)
    state["edges"].extend([*source_edges, edge("H2", "N1", relation, score=score)])
    return state


def test_support_from_an_ungrounded_hypothesis_has_no_effect_on_belief():
    state = hypothesis_evidence_state([{"id": "H2", "type": "hypothesis", "text": "Guess", "score": 5}], [], "supports", 5)
    assert belief(state) == pytest.approx(0.5)


def test_support_from_a_grounded_hypothesis_is_scaled_by_its_belief():
    # H2 has belief 0.5 from O1, so ratio 5 becomes 1 + 0.5 * 4 = 3: odds 1 -> 3.
    state = hypothesis_evidence_state(
        [{"id": "O1", "type": "observation", "text": "Clue", "score": 3}, {"id": "H2", "type": "hypothesis", "text": "Lemma"}],
        [edge("O1", "H2")],
        "supports",
        5,
    )
    assert belief(state) == pytest.approx(0.75)


def test_contradiction_from_an_ungrounded_hypothesis_is_scaled_by_its_belief():
    # Ratio 1/5 at source belief 0.5 becomes 1 - 0.5 * 0.8 = 0.6: odds 1 -> 0.6.
    state = hypothesis_evidence_state([{"id": "H2", "type": "hypothesis", "text": "Rival"}], [], "contradicts", 5)
    assert belief(state) == pytest.approx(0.375)


def test_observation_evidence_is_not_scaled_by_its_score():
    state = claim_state()
    state["nodes"].append({"id": "O1", "type": "observation", "text": "Clue", "score": 3})
    state["edges"].append(edge("O1", "N1", "supports", score=5))
    assert belief(state) == pytest.approx(5 / 6)


def test_ungrounded_support_does_not_raise_a_grounded_candidate():
    state = claim_state()
    state["nodes"].extend([
        {"id": "O1", "type": "observation", "text": "Clue", "score": 4},
        {"id": "H2", "type": "hypothesis", "text": "Guess", "score": 5},
    ])
    state["edges"].extend([edge("O1", "N1"), edge("H2", "N1", "supports", score=5)])
    assert belief(state) == pytest.approx(0.7)


def test_evidence_cycle_between_hypotheses_is_invalid():
    state = claim_state()
    state["nodes"].extend([
        {"id": "H1", "type": "hypothesis", "text": "First"},
        {"id": "H2", "type": "hypothesis", "text": "Second"},
    ])
    state["edges"].extend([
        edge("H1", "H2", "supports"),
        edge("H2", "H1", "supports"),
        edge("H1", "N1"),
    ])
    result = validate_state(state)
    assert not result.ok
    assert any("cycle" in error for error in result.errors), result.errors
