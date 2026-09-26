"""Belief sources, not zero costs or node roles, determine score requirements."""

import sys
from copy import deepcopy
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.costs import node_effective_truth_costs, probability_from_cost
from reasoning_graph.policy import below_threshold_messages, ranked_viable_candidates
from reasoning_graph.validation import validate_state


CLAIM_TYPES = ("observation", "hypothesis", "hypothesis", "candidate_solution")


def edge(source, target, relation="leads_to", **extra):
    return {"id": f"{source}-{target}-{relation}", "from": source, "to": target, "type": relation,
            "reasoning": "The source supplies the stated relationship to the target.", **extra}


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


@pytest.mark.parametrize("node_type", CLAIM_TYPES)
def test_unscored_standalone_claim_is_invalid_and_not_certain(node_type):
    state = claim_state(node_type)
    result = validate_state(state)
    assert not result.ok
    # Direct consumers of the cost engine must not recover the old free certainty.
    assert belief(state) == pytest.approx(0.5)
    assert any("belief source" in error for error in result.errors), result.errors
    assert belief(state, "G1") == 1.0  # Objectives still have no local truth penalty.


@pytest.mark.parametrize("node_type", CLAIM_TYPES)
def test_claim_inherits_scored_premises_without_an_extra_local_factor(node_type):
    state = claim_state(node_type)
    state["nodes"].extend([
        {"id": "A1", "type": "hypothesis", "text": "Premise", "prior": 0.6},
        {"id": "D1", "type": "hypothesis", "text": "Intermediate conclusion"},
    ])
    state["edges"].extend([edge("A1", "D1"), edge("D1", "N1")])
    result = validate_state(state)
    assert result.ok, result.errors
    assert belief(state) == pytest.approx(0.6)

    state["nodes"][1]["prior"] = 0.9
    result = validate_state(state)
    assert result.ok, result.errors
    assert belief(state) == pytest.approx(0.54)


@pytest.mark.parametrize("source_type", ["goal", "constraint", "test"])
def test_scoreless_nonclaim_premise_does_not_ground_a_candidate(source_type):
    state = claim_state()
    state["nodes"].append({"id": "S1", "type": source_type, "text": "Stipulation or action"})
    state["edges"].append(edge("S1", "N1"))
    result = validate_state(state)
    assert not result.ok
    assert any("belief source" in error for error in result.errors), result.errors
    assert belief(state) == pytest.approx(0.5)


def test_likelihood_update_is_not_a_substitute_for_a_starting_belief():
    state = claim_state()
    state["nodes"].append({"id": "E1", "type": "observation", "text": "Observation", "prior": 0.9})
    state["edges"].append(edge("E1", "N1", "supports", likelihood_ratio=2))
    result = validate_state(state)
    assert not result.ok
    assert any("belief source" in error for error in result.errors), result.errors
    assert belief(state) == pytest.approx(2 / 3)


@pytest.mark.parametrize("relation,ratio", [("supports", 2), ("contradicts", 0.1)])
@pytest.mark.parametrize("grouped", [False, True])
def test_certain_premises_remain_certain_under_finite_likelihoods(relation, ratio, grouped):
    state = claim_state()
    state["nodes"].extend([
        {"id": "E1", "type": "observation", "text": "Certain premise", "prior": 1.0},
        {"id": "E2", "type": "observation", "text": "Second premise", "prior": 1.0},
        {"id": "D1", "type": "hypothesis", "text": "Intermediate conclusion"},
        {"id": "L1", "type": "observation", "text": "Likelihood observation", "prior": 0.9},
        {"id": "L2", "type": "observation", "text": "Related observation", "prior": 0.9},
    ])
    state["edges"].extend([edge("E1", "D1"), edge("E2", "D1"), edge("D1", "N1")])
    assert belief(state, "D1") == 1.0
    assert belief(state) == 1.0
    state["edges"].append(edge("L1", "D1", relation, likelihood_ratio=ratio))
    if grouped:
        state["edges"].append(edge("L2", "D1", relation, likelihood_ratio=ratio))
        state["factors"] = [
            {"id": "F1", "relation": "leads_to", "target": "D1", "inputs": ["E1", "E2"],
             "aggregation": {"kind": "joint_probability", "probability": 1.0}},
            {"id": "F2", "relation": relation, "target": "D1", "inputs": ["L1", "L2"],
             "aggregation": {"kind": "likelihood", "if_target_true": min(ratio, 1),
                             "if_target_false": min(1 / ratio, 1)}},
        ]
    assert belief(state, "D1") == 1.0
    assert belief(state) == 1.0
    result = validate_state(state)
    assert result.ok, result.errors


def test_calibrated_joint_premise_factor_is_a_belief_source():
    state = claim_state()
    state["nodes"].extend([
        {"id": "S1", "type": "constraint", "text": "First condition"},
        {"id": "S2", "type": "constraint", "text": "Second condition"},
    ])
    state["edges"].extend([edge("S1", "N1"), edge("S2", "N1")])
    state["factors"] = [
        {"id": "F1", "relation": "leads_to", "target": "N1", "inputs": ["S1", "S2"],
         "aggregation": {"kind": "joint_probability", "probability": 0.7}},
    ]
    result = validate_state(state)
    assert result.ok, result.errors
    assert belief(state) == pytest.approx(0.7)


def test_local_inference_prior_matches_an_explicit_validity_assumption():
    state = claim_state("hypothesis", prior=0.9)
    state["nodes"].append({"id": "E1", "type": "observation", "text": "Observation", "prior": 0.8})
    state["edges"].append(edge("E1", "N1"))
    result = validate_state(state)
    assert result.ok, result.errors
    assert belief(state) == pytest.approx(0.72)

    del state["nodes"][1]["prior"]
    state["nodes"].append({"id": "A1", "type": "hypothesis", "text": "Inference is valid", "prior": 0.9})
    state["edges"].append(edge("A1", "N1"))
    assert validate_state(state).ok
    assert belief(state) == pytest.approx(0.72)


def test_candidate_ranking_and_stopping_use_inherited_belief():
    state = claim_state()
    state["nodes"].extend([
        {"id": "O1", "type": "observation", "text": "Observed clue", "prior": 1.0},
        {"id": "A1", "type": "hypothesis", "text": "Premise", "prior": 0.6},
        {"id": "CS2", "type": "candidate_solution", "text": "The answer is 43",
         "answer_kind": "exact_answer", "prior": 0.55},
    ])
    # O1 grounds the premise chain; the threshold only credits evidence-grounded candidates.
    state["edges"].extend([edge("O1", "A1"), edge("A1", "N1"), edge("CS2", "G1", "answers")])
    state["stop_policy"] = {"belief_threshold": 0.6, "severity": "error"}
    assert validate_state(state).ok
    ranked = ranked_viable_candidates(state)
    assert [(item["node"], item["belief"]) for item in ranked] == [("N1", 0.6), ("CS2", 0.55)]
    assert below_threshold_messages(state) == []

    # Removing the only absolute belief sources must not pass the threshold.
    del next(node for node in state["nodes"] if node["id"] == "A1")["prior"]
    state["edges"] = [item for item in state["edges"] if item["from"] != "O1"]
    assert not validate_state(state).ok
    assert belief(state) == pytest.approx(0.5)
    assert below_threshold_messages(state)


def test_computed_belief_recalculates_without_writing_node_scores():
    state = claim_state()
    state["nodes"].extend([
        {"id": "E1", "type": "observation", "text": "Premise", "prior": 0.8},
        {"id": "L1", "type": "observation", "text": "Independent observation", "prior": 0.9},
        {"id": "D1", "type": "hypothesis", "text": "Soft inference", "prior": 0.9},
    ])
    state["edges"].extend([
        edge("E1", "D1"), edge("L1", "D1", "supports", likelihood_ratio=2), edge("D1", "N1"),
    ])
    original = deepcopy(state)
    assert validate_state(state).ok
    # Local 0.9 times inherited 0.8 gives 0.72; LR 2 gives 36/43.
    assert belief(state) == pytest.approx(36 / 43)
    assert ranked_viable_candidates(state)[0]["belief"] == pytest.approx(36 / 43, abs=1e-6)
    assert state == original

    state["nodes"][2]["prior"] = 0.5
    updated = deepcopy(state)
    assert belief(state) == pytest.approx(18 / 29)
    assert state == updated


def test_posterior_overrides_only_its_node_and_can_be_removed():
    state = claim_state(prior=0.5)
    state["nodes"].extend([
        {"id": "E1", "type": "observation", "text": "Premise", "prior": 0.8},
        {"id": "L1", "type": "observation", "text": "Independent observation", "prior": 0.9},
        {"id": "D1", "type": "hypothesis", "text": "Calibrated inference", "prior": 0.9, "posterior": 0.7},
    ])
    state["edges"].extend([
        edge("E1", "D1"), edge("L1", "D1", "supports", likelihood_ratio=2), edge("D1", "N1"),
    ])
    original = deepcopy(state)
    assert validate_state(state).ok
    assert belief(state, "D1") == pytest.approx(0.7)
    assert belief(state) == pytest.approx(0.35)
    assert state == original

    state["nodes"][2]["prior"] = 0.5
    state["edges"][2]["likelihood_ratio"] = 3
    assert belief(state, "D1") == pytest.approx(0.7)
    assert belief(state) == pytest.approx(0.35)

    del state["nodes"][4]["posterior"]
    # Removing the override resumes current inputs: 0.5 * 0.9, then LR 3.
    assert belief(state, "D1") == pytest.approx(27 / 38)
    assert belief(state) == pytest.approx(27 / 76)


def hypothesis_evidence_state(source_nodes, source_edges, relation, ratio):
    """N1 starts at 0.5; H2 bears evidence on it with the given relation and ratio."""
    state = claim_state(prior=0.5)
    state["nodes"].extend(source_nodes)
    state["edges"].extend([*source_edges, edge("H2", "N1", relation, likelihood_ratio=ratio)])
    return state


def test_support_from_an_ungrounded_hypothesis_has_no_effect_on_belief():
    state = hypothesis_evidence_state([{"id": "H2", "type": "hypothesis", "text": "Guess", "prior": 0.9}], [], "supports", 9)
    assert belief(state) == pytest.approx(0.5)


def test_support_from_a_grounded_hypothesis_is_scaled_by_its_belief():
    # H2 has belief 0.5 from O1, so ratio 9 becomes 1 + 0.5 * 8 = 5: odds 1 -> 5.
    state = hypothesis_evidence_state(
        [{"id": "O1", "type": "observation", "text": "Clue", "prior": 0.5}, {"id": "H2", "type": "hypothesis", "text": "Lemma"}],
        [edge("O1", "H2")],
        "supports",
        9,
    )
    assert belief(state) == pytest.approx(5 / 6)


def test_contradiction_from_an_ungrounded_hypothesis_is_scaled_by_its_belief():
    # Ratio 0.2 at source belief 0.5 becomes 1 - 0.5 * 0.8 = 0.6: odds 1 -> 0.6.
    state = hypothesis_evidence_state([{"id": "H2", "type": "hypothesis", "text": "Rival", "prior": 0.5}], [], "contradicts", 0.2)
    assert belief(state) == pytest.approx(0.375)


def test_observation_evidence_is_not_scaled_by_its_prior():
    state = claim_state(prior=0.5)
    state["nodes"].append({"id": "O1", "type": "observation", "text": "Clue", "prior": 0.5})
    state["edges"].append(edge("O1", "N1", "supports", likelihood_ratio=9))
    assert belief(state) == pytest.approx(0.9)


def test_ungrounded_support_cannot_lift_a_grounded_candidate_past_the_threshold():
    state = claim_state()
    state["nodes"].extend([
        {"id": "O1", "type": "observation", "text": "Clue", "prior": 0.6},
        {"id": "H2", "type": "hypothesis", "text": "Guess", "prior": 0.9},
    ])
    state["edges"].extend([edge("O1", "N1"), edge("H2", "N1", "supports", likelihood_ratio=9)])
    state["stop_policy"] = {"belief_threshold": 0.8, "severity": "error"}
    assert belief(state) == pytest.approx(0.6)
    assert below_threshold_messages(state)


def test_evidence_cycle_between_hypotheses_is_invalid():
    state = claim_state(prior=0.5)
    state["nodes"].extend([
        {"id": "H1", "type": "hypothesis", "text": "First", "prior": 0.6},
        {"id": "H2", "type": "hypothesis", "text": "Second", "prior": 0.6},
    ])
    state["edges"].extend([
        edge("H1", "H2", "supports", likelihood_ratio=3),
        edge("H2", "H1", "supports", likelihood_ratio=3),
        edge("H1", "N1"),
    ])
    result = validate_state(state)
    assert not result.ok
    assert any("cycle" in error for error in result.errors), result.errors
