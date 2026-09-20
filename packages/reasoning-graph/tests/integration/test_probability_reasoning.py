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
