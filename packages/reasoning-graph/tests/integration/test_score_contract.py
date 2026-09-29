"""One optional 1-5 `score` is the only authored number on claims and evidence edges."""

import json
import sys
import unittest
from pathlib import Path

import jsonschema
import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.cli import starter_state
from reasoning_graph.costs import node_effective_truth_costs, probability_from_cost
from reasoning_graph.models import EDGE_TYPES, NODE_TYPES
from reasoning_graph.offline_render import offline_graph_svg
from reasoning_graph.render import compact_node_label, to_mermaid
from reasoning_graph.schema_validation import patch_schema_errors, standalone_schema, state_schema_errors
from reasoning_graph.validation import validate_state


REMOVED_NODE_FIELDS = ("prior", "confidence", "probability", "posterior")
REMOVED_EDGE_FIELDS = {"likelihood": {"if_target_true": 0.8, "if_target_false": 0.2}, "likelihood_ratio": 2}

CLAIM_TYPES = ("candidate_solution", "hypothesis", "observation")
SCORE_FREE_TYPES = ("goal", "constraint", "test")
EVIDENCE_EDGE_TYPES = ("contradicts", "supports")
INVALID_SCORES = [0, 6, -1, 2.5, True, "3", None]


def build_node(node_type: str, **extra: object) -> dict:
    node: dict = {"id": "N1", "type": node_type, "text": "claim"}
    if node_type == "candidate_solution":
        node["answer_kind"] = "exact_answer"
    node.update(extra)
    return node


def state_with(node_type: str, **extra: object) -> dict:
    return {"nodes": [build_node(node_type, **extra)], "edges": []}


def score_errors(state: dict) -> list[str]:
    # A lone candidate fails validation for lacking an answers edge; only score errors matter here.
    return [error for error in validate_state(state).errors if "score" in error]


def evidence_state(edge_type: str = "supports", **extra: object) -> dict:
    return {
        "nodes": [
            {"id": "O1", "type": "observation", "text": "Signal"},
            {"id": "H1", "type": "hypothesis", "text": "Target"},
        ],
        "edges": [{"from": "O1", "to": "H1", "type": edge_type, **extra}],
    }


@pytest.mark.parametrize("score", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("node_type", CLAIM_TYPES)
def test_claims_accept_a_score_from_one_to_five(node_type, score):
    assert not state_schema_errors(state_with(node_type, score=score))
    assert not patch_schema_errors({"nodes": [build_node(node_type, score=score)]})
    assert not score_errors(state_with(node_type, score=score))


@pytest.mark.parametrize("node_type", CLAIM_TYPES)
def test_claims_need_no_score(node_type):
    assert not patch_schema_errors({"nodes": [build_node(node_type)]})
    assert not score_errors(state_with(node_type))


@pytest.mark.parametrize("node_type", SCORE_FREE_TYPES)
def test_score_free_types_reject_a_score(node_type):
    assert state_schema_errors(state_with(node_type, score=3))
    assert any("score is only valid on" in error for error in score_errors(state_with(node_type, score=3)))


@pytest.mark.parametrize("value", INVALID_SCORES)
@pytest.mark.parametrize("node_type", CLAIM_TYPES)
def test_claim_score_outside_the_scale_is_rejected(node_type, value):
    assert state_schema_errors(state_with(node_type, score=value))
    result = validate_state(state_with(node_type, score=value))
    assert any("score must be an integer from 1 to 5" in error for error in result.errors), result.errors


@pytest.mark.parametrize("value", INVALID_SCORES)
@pytest.mark.parametrize("edge_type", EVIDENCE_EDGE_TYPES)
def test_edge_score_outside_the_scale_is_rejected(edge_type, value):
    state = evidence_state(edge_type, score=value)
    assert state_schema_errors(state)
    result = validate_state(state)
    assert any("score must be an integer from 1 to 5" in error for error in result.errors), result.errors


@pytest.mark.parametrize("edge_type", sorted(set(EDGE_TYPES) - set(EVIDENCE_EDGE_TYPES)))
def test_only_evidence_edges_take_a_score(edge_type):
    state = evidence_state(edge_type, score=3)
    result = validate_state(state)
    assert any("score is only valid on supports/contradicts edges" in error for error in result.errors), result.errors


@pytest.mark.parametrize("field", REMOVED_NODE_FIELDS)
@pytest.mark.parametrize("node_type", sorted(NODE_TYPES))
def test_removed_node_scores_are_rejected_and_name_the_replacement(node_type, field):
    node = build_node(node_type, **{field: 0.9})
    state = {"nodes": [node], "edges": []}
    patch = {"nodes": [node]}
    assert state_schema_errors(state)
    assert patch_schema_errors(patch)
    assert not jsonschema.Draft202012Validator(standalone_schema("state.schema.json")).is_valid(state)
    assert not jsonschema.Draft202012Validator(standalone_schema("patch.schema.json")).is_valid(patch)
    errors = validate_state(state).errors
    assert any(f"{field} was removed" in error and "score" in error for error in errors), errors


@pytest.mark.parametrize("field,value", sorted(REMOVED_EDGE_FIELDS.items()))
def test_removed_edge_scores_are_rejected_and_name_the_replacement(field, value):
    state = evidence_state(**{field: value})
    assert state_schema_errors(state)
    assert patch_schema_errors({"edges": state["edges"]})
    errors = validate_state(state).errors
    assert any(f"{field} was removed" in error and "score" in error for error in errors), errors


@pytest.mark.parametrize("field", REMOVED_NODE_FIELDS)
def test_direct_cost_consumers_reject_removed_score_inputs(field):
    node = build_node("hypothesis", **{field: 0.9})
    with pytest.raises(ValueError, match=field):
        node_effective_truth_costs({"nodes": [node], "edges": []})


@pytest.mark.parametrize("node_type", sorted(NODE_TYPES))
def test_computed_belief_is_rejected_in_state_and_patch(node_type):
    node = build_node(node_type, belief=0.9)
    assert state_schema_errors({"nodes": [node], "edges": []})
    assert patch_schema_errors({"nodes": [node]})
    errors = validate_state({"nodes": [node], "edges": []}).errors
    assert any("belief was removed from the state" in error for error in errors), errors


def derived_state(**derived: object) -> dict:
    return {
        "nodes": [
            {"id": "E1", "type": "observation", "text": "Observation", "score": 4},
            {"id": "A1", "type": "hypothesis", "text": "Premise", "score": 5},
            {"id": "D1", "type": "hypothesis", "text": "Conclusion", **derived},
        ],
        "edges": [
            {"from": "E1", "to": "D1", "type": "leads_to"},
            {"from": "A1", "to": "D1", "type": "leads_to"},
        ],
    }


def test_derived_belief_is_the_premise_product():
    state = derived_state()
    assert validate_state(state).ok
    assert probability_from_cost(node_effective_truth_costs(state)["D1"]) == pytest.approx(0.63)

    assert "belief 0.63" in to_mermaid(state)
    assert "belief 0.63" in offline_graph_svg(state)


def test_score_free_labels_carry_no_score_line():
    assert compact_node_label(build_node("goal"), 0.0) == "N1\ngoal"
    assert compact_node_label(build_node("constraint"), 0.0) == "N1\nconstraint"
    assert compact_node_label(build_node("test"), 0.0) == "N1\ntest"


@pytest.mark.parametrize("relation,expected", [
    ("supports", 2 / 3),
    ("contradicts", 1 / 3),
])
def test_default_hypothesis_propagates_its_updated_belief(relation, expected):
    fixture = PACKAGE_ROOT / "tests" / "fixtures" / "valid" / "neutral-likelihood-state.json"
    state = json.loads(fixture.read_text(encoding="utf-8"))
    state["edges"][0].update(type=relation)
    assert validate_state(state).ok
    costs = node_effective_truth_costs(state)
    for node_id in ("A1", "D1", "CS1"):
        assert probability_from_cost(costs[node_id]) == pytest.approx(expected)


def test_derived_belief_updates_from_evidence_on_uncertain_premises():
    state = {
        "nodes": [
            {"id": "E1", "type": "observation", "text": "Premise", "score": 4},
            {"id": "E2", "type": "observation", "text": "Counter-observation"},
            {"id": "D1", "type": "hypothesis", "text": "Deterministic conclusion"},
        ],
        "edges": [
            {"from": "E1", "to": "D1", "type": "leads_to"},
            {"from": "E2", "to": "D1", "type": "contradicts", "score": 5},
        ],
    }
    assert validate_state(state).ok
    # Premise 0.7 gives odds 7/3; ratio 1/5 gives odds 7/15 and belief 7/22.
    assert probability_from_cost(node_effective_truth_costs(state)["D1"]) == pytest.approx(7 / 22)


def test_partial_update_can_retain_existing_score():
    assert not patch_schema_errors({"update_nodes": [{"id": "G1", "set": {"text": "Updated goal"}}]})
    assert validate_state(starter_state("default")).ok


class ScoreContractCliTests(unittest.TestCase):
    """Starter objectives need no claim score."""

    def test_starter_goal_has_no_score(self) -> None:
        state = starter_state("default")
        self.assertEqual([node["type"] for node in state["nodes"]], ["goal"])
        self.assertNotIn("score", state["nodes"][0])
