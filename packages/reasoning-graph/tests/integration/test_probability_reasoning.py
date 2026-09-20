"""Contract checks for explicit node scores and bounded edge explanations."""


import jsonschema
import pytest

from reasoning_graph.cli import starter_state
from reasoning_graph.costs import node_effective_truth_costs, probability_from_cost
from reasoning_graph.models import EDGE_TYPES, NODE_TYPES
from reasoning_graph.offline_render import offline_graph_svg
from reasoning_graph.render import node_detail_cards, to_mermaid
from reasoning_graph.schema_validation import (
    REASONING_FORMAT_CHECKER,
    patch_schema_errors,
    standalone_schema,
    state_schema_errors,
)
from reasoning_graph.validation import validate_state


@pytest.mark.parametrize("node_type", sorted(NODE_TYPES))
@pytest.mark.parametrize("field", ["prior", "confidence", "probability", "posterior"])
def test_every_node_type_requires_an_explicit_score(node_type, field):
    node = {"id": "N1", "type": node_type}
    assert state_schema_errors({"nodes": [node], "edges": [], "frontier": []})
    assert patch_schema_errors({"nodes": [node]})
    node[field] = 0.8
    assert not state_schema_errors({"nodes": [node], "edges": [], "frontier": []})
    assert not patch_schema_errors({"nodes": [node]})


@pytest.mark.parametrize("value", [0, -0.1, 1.1, True, "0.8", None])
@pytest.mark.parametrize("field", ["prior", "confidence", "probability", "posterior"])
def test_invalid_scores_are_rejected(value, field):
    node = {"id": "D1", "type": "derived", field: value}
    assert patch_schema_errors({"nodes": [node]})


@pytest.mark.parametrize("edge_type", sorted(EDGE_TYPES))
def test_all_edge_types_require_reasoning(edge_type):
    edge = {"from": "A", "to": "B", "type": edge_type}
    assert patch_schema_errors({"edges": [edge]})
    edge["reasoning"] = "The source supplies the premise needed for the target."
    assert not patch_schema_errors({"edges": [edge]})


@pytest.mark.parametrize("reasoning,valid", [
    ("", False), (" \n\t", False), (None, False), (17, False),
    ("...?!", False), ("One explanation", True),
    ("One. Two! Three? Four. Five.", True),
    ("One. Two! Three? Four. Five. Six.", False),
    ('One. Two. Three. Four. "Five." Six.', False),
    ("One.\nTwo.\nThree.\nFour.\nFive.\nSix", False),
    ("At 0.75 confidence the result supports the claim. See https://example.org/log.", True),
])
def test_sentence_limits_apply_to_state_patch_and_exported_schema(reasoning, valid):
    edge = {"from": "A", "to": "B", "type": "supports", "reasoning": reasoning}
    state = {"nodes": [], "edges": [edge], "frontier": []}
    patch = {"edges": [edge]}
    assert (not state_schema_errors(state)) == valid
    assert (not patch_schema_errors(patch)) == valid
    validator = jsonschema.Draft202012Validator(
        standalone_schema("patch.schema.json"), format_checker=REASONING_FORMAT_CHECKER,
    )
    assert validator.is_valid(patch) == valid


def test_derived_local_score_and_posterior_do_not_double_count():
    state = {
        "nodes": [
            {"id": "E1", "type": "evidence", "confidence": 0.8},
            {"id": "D1", "type": "derived", "confidence": 0.9},
        ],
        "edges": [{"from": "E1", "to": "D1", "type": "leads_to",
                   "reasoning": "The timestamp comparison relies on this observation."}],
        "frontier": [],
    }
    assert validate_state(state).ok
    assert probability_from_cost(node_effective_truth_costs(state)["D1"]) == pytest.approx(0.72)
    state["nodes"][1]["posterior"] = 0.72
    assert probability_from_cost(node_effective_truth_costs(state)["D1"]) == pytest.approx(0.72)
    assert "posterior 0.72" in to_mermaid(state)
    assert "posterior 0.72" in offline_graph_svg(state)
    state["edges"][0]["reasoning"] = "The <script> tag is text, not executable markup."
    assert "&lt;script&gt;" in node_detail_cards(state)
    assert "<script>" not in node_detail_cards(state)


def test_partial_update_can_retain_existing_score():
    assert not patch_schema_errors({"update_nodes": [{"id": "G1", "set": {"text": "Updated goal"}}]})
    assert validate_state(starter_state("default")).ok


@pytest.mark.parametrize("relation,ratio,expected", [
    ("supports", 2.0, 2 / 3),
    ("contradicts", 0.1, 1 / 11),
])
def test_neutral_fixture_likelihoods_propagate_to_derived_and_candidate(relation, ratio, expected):
    import json
    from pathlib import Path

    fixture = Path(__file__).parents[1] / "fixtures/valid/neutral-likelihood-state.json"
    state = json.loads(fixture.read_text())
    state["edges"][0].update(type=relation, likelihood_ratio=ratio)
    assert validate_state(state).ok
    costs = node_effective_truth_costs(state)
    for node_id in ("A1", "D1", "CS1"):
        assert probability_from_cost(costs[node_id]) == pytest.approx(expected)

    # The old unscored calculation used neutral odds in this precise case.
    # Such a state is now invalid, but the low-level arithmetic is a useful
    # reference: explicit neutral belief must retain its likelihood response.
    del state["nodes"][2]["prior"]
    assert not validate_state(state).ok
    assert probability_from_cost(node_effective_truth_costs(state)["A1"]) == pytest.approx(expected)

    # Certainty must remain certainty; the fix must not silently reinterpret 1.
    state["nodes"][2]["probability"] = 1.0
    assert probability_from_cost(node_effective_truth_costs(state)["A1"]) == 1.0


def test_certain_local_inference_still_updates_from_uncertain_premises():
    state = {
        "nodes": [
            {"id": "E1", "type": "evidence", "confidence": 0.8},
            {"id": "E2", "type": "evidence", "confidence": 0.95},
            {"id": "D1", "type": "derived", "confidence": 1.0},
        ],
        "edges": [
            {"from": "E1", "to": "D1", "type": "leads_to",
             "reasoning": "The conclusion follows deterministically if the premise is true."},
            {"from": "E2", "to": "D1", "type": "contradicts", "likelihood_ratio": 0.1,
             "reasoning": "This independent observation is ten times less likely if the conclusion is true."},
        ],
        "frontier": [],
    }
    assert validate_state(state).ok
    # Premise P=.8 gives odds 4; LR=.1 gives odds .4 and P=2/7.
    assert probability_from_cost(node_effective_truth_costs(state)["D1"]) == pytest.approx(2 / 7)
