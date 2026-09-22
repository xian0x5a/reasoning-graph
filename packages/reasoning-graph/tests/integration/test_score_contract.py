"""Prior is a local input, belief is computed, and posterior is an override."""

import json
import sys
import unittest
from pathlib import Path

import jsonschema
import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.cli import starter_state
from reasoning_graph.costs import node_effective_truth_costs, node_local_truth_cost, probability_from_cost
from reasoning_graph.models import NODE_TYPES
from reasoning_graph.offline_render import offline_graph_svg
from reasoning_graph.render import compact_node_label, to_mermaid
from reasoning_graph.schema_validation import patch_schema_errors, standalone_schema, state_schema_errors
from reasoning_graph.validation import validate_state


FIELDS = ("prior", "posterior")
REJECTED_INPUT_FIELDS = ("confidence", "probability", "belief")

CLAIM_TYPES = ("evidence", "assumption", "candidate_solution", "derived")
SCORE_FREE_TYPES = ("goal", "constraint", "test")
ACCEPTED = [(node_type, field) for node_type in CLAIM_TYPES for field in FIELDS]


def build_node(node_type: str, **extra: object) -> dict:
    node: dict = {"id": "N1", "type": node_type, "text": "claim"}
    if node_type == "candidate_solution":
        node["answer_kind"] = "exact_answer"
    node.update(extra)
    return node


def state_with(node_type: str, **extra: object) -> dict:
    return {"nodes": [build_node(node_type, **extra)], "edges": [], "frontier": []}


@pytest.mark.parametrize("node_type,field", ACCEPTED)
def test_allowed_score_field(node_type, field):
    assert not state_schema_errors(state_with(node_type, **{field: 0.8}))
    assert not patch_schema_errors({"nodes": [build_node(node_type, **{field: 0.8})]})


@pytest.mark.parametrize("node_type", CLAIM_TYPES)
def test_schema_defers_belief_source_checks_to_complete_graph_validation(node_type):
    assert not state_schema_errors(state_with(node_type))
    assert not patch_schema_errors({"nodes": [build_node(node_type)]})


@pytest.mark.parametrize("node_type", SCORE_FREE_TYPES)
def test_score_free_types_reject_every_score(node_type):
    for field in FIELDS:
        assert state_schema_errors(state_with(node_type, **{field: 0.8})), field


@pytest.mark.parametrize("field", REJECTED_INPUT_FIELDS)
@pytest.mark.parametrize("node_type", sorted(NODE_TYPES))
def test_obsolete_scores_and_computed_belief_are_rejected_as_node_inputs(node_type, field):
    score = {"prior": 0.8} if node_type in CLAIM_TYPES else {}
    node = build_node(node_type, **score, **{field: 0.9})
    state = {"nodes": [node], "edges": [], "frontier": []}
    patch = {"nodes": [node]}
    assert state_schema_errors(state)
    assert patch_schema_errors(patch)
    assert not jsonschema.Draft202012Validator(standalone_schema("state.schema.json")).is_valid(state)
    assert not jsonschema.Draft202012Validator(standalone_schema("patch.schema.json")).is_valid(patch)


@pytest.mark.parametrize("field", REJECTED_INPUT_FIELDS)
@pytest.mark.parametrize("override", [False, True])
def test_direct_cost_consumers_reject_invalid_score_inputs(field, override):
    node = build_node("derived", prior=0.8, **{field: 0.9})
    if override:
        node["posterior"] = 0.7
    with pytest.raises(ValueError, match=field):
        node_local_truth_cost(node)
    with pytest.raises(ValueError, match=field):
        node_effective_truth_costs({"nodes": [node], "edges": [], "frontier": []})


@pytest.mark.parametrize("value", [0, -0.1, 1.1, True, "0.8", None])
@pytest.mark.parametrize("node_type,field", ACCEPTED)
def test_invalid_score_values_are_rejected(node_type, field, value):
    assert state_schema_errors(state_with(node_type, **{field: value}))


def derived_state(**derived: object) -> dict:
    return {
        "nodes": [
            {"id": "E1", "type": "evidence", "text": "Observation", "prior": 0.8},
            {"id": "A1", "type": "assumption", "text": "Premise", "prior": 0.9},
            {"id": "D1", "type": "derived", "text": "Conclusion", **derived},
        ],
        "edges": [
            {"from": "E1", "to": "D1", "type": "leads_to", "reasoning": "The conclusion rests on this observation."},
            {"from": "A1", "to": "D1", "type": "leads_to", "reasoning": "The conclusion rests on this premise."},
        ],
        "frontier": [],
    }


def test_derived_belief_is_the_premise_product():
    state = derived_state()
    assert validate_state(state).ok
    assert probability_from_cost(node_effective_truth_costs(state)["D1"]) == pytest.approx(0.72)

    state["nodes"][2]["posterior"] = 0.72
    assert probability_from_cost(node_effective_truth_costs(state)["D1"]) == pytest.approx(0.72)
    assert "posterior 0.72" in to_mermaid(state)
    assert "posterior 0.72" in offline_graph_svg(state)


def test_score_free_labels_carry_no_score_line():
    assert compact_node_label(build_node("goal")) == "N1\ngoal"
    assert compact_node_label(build_node("constraint")) == "N1\nconstraint"
    assert compact_node_label(build_node("test")) == "N1\ntest"


@pytest.mark.parametrize("relation,ratio,expected", [
    ("supports", 2.0, 2 / 3),
    ("contradicts", 0.1, 1 / 11),
])
def test_neutral_prior_propagates_and_certainty_stays_certain(relation, ratio, expected):
    fixture = PACKAGE_ROOT / "tests" / "fixtures" / "valid" / "neutral-likelihood-state.json"
    state = json.loads(fixture.read_text(encoding="utf-8"))
    state["edges"][0].update(type=relation, likelihood_ratio=ratio)
    assert validate_state(state).ok
    costs = node_effective_truth_costs(state)
    for node_id in ("A1", "D1", "CS1"):
        assert probability_from_cost(costs[node_id]) == pytest.approx(expected)

    # An unscored node still falls back to neutral odds, but that state is invalid now.
    del state["nodes"][2]["prior"]
    assert not validate_state(state).ok
    assert probability_from_cost(node_effective_truth_costs(state)["A1"]) == pytest.approx(expected)

    # Explicit certainty stays certain: 1.0 must not be reinterpreted as unknown.
    state["nodes"][2]["prior"] = 1.0
    assert probability_from_cost(node_effective_truth_costs(state)["A1"]) == 1.0


def test_derived_belief_updates_from_likelihoods_on_uncertain_premises():
    state = {
        "nodes": [
            {"id": "E1", "type": "evidence", "text": "Premise", "prior": 0.8},
            {"id": "E2", "type": "evidence", "text": "Counter-observation", "prior": 0.95},
            {"id": "D1", "type": "derived", "text": "Deterministic conclusion"},
        ],
        "edges": [
            {"from": "E1", "to": "D1", "type": "leads_to",
             "reasoning": "The conclusion follows deterministically if this premise is true."},
            {"from": "E2", "to": "D1", "type": "contradicts", "likelihood_ratio": 0.1,
             "reasoning": "This independent observation is ten times less likely if the conclusion is true."},
        ],
        "frontier": [],
    }
    assert validate_state(state).ok
    # Premise 0.8 gives odds 4; ratio 0.1 gives odds 0.4 and belief 2/7.
    assert probability_from_cost(node_effective_truth_costs(state)["D1"]) == pytest.approx(2 / 7)


def test_partial_update_can_retain_existing_score():
    assert not patch_schema_errors({"update_nodes": [{"id": "G1", "set": {"text": "Updated goal"}}]})
    assert validate_state(starter_state("default")).ok


class ScoreContractCliTests(unittest.TestCase):
    """Starter objectives need no claim score."""

    def test_starter_goal_has_no_score(self) -> None:
        state = starter_state("default")
        self.assertEqual([node["type"] for node in state["nodes"]], ["goal"])
        self.assertFalse(set(FIELDS) & set(state["nodes"][0]))
