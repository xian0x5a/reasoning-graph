"""Edge explanations are required; sentence counts are authoring guidance only."""

import sys
from pathlib import Path

import jsonschema
import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.models import EDGE_TYPES
from reasoning_graph.render import node_detail_cards
from reasoning_graph.schema_validation import (
    patch_schema_errors,
    standalone_schema,
    state_schema_errors,
)


@pytest.mark.parametrize("edge_type", sorted(EDGE_TYPES))
def test_all_edge_types_require_reasoning(edge_type):
    edge = {"from": "A", "to": "B", "type": edge_type}
    assert patch_schema_errors({"edges": [edge]})
    edge["reasoning"] = "The source supplies what the target needs."
    assert not patch_schema_errors({"edges": [edge]})


@pytest.mark.parametrize("reasoning,valid", [
    ("", False), (" \n\t", False), (None, False), (17, False),
    ("...?!", True), ("One explanation", True),
    ("One. Two! Three? Four. Five.", True),
    ("One. Two! Three? Four. Five. Six.", True),
    ('One. Two. Three. Four. "Five." Six.', True),
    ("One.\nTwo.\nThree.\nFour.\nFive.\nSix", True),
    ("Dr. A. Smith compared U.S. and U.K. results, e.g. Fig. 2, and confirmed the match.", True),
    ("At 0.75 confidence the result supports the claim. See https://example.org/log.", True),
])
def test_nonblank_reasoning_applies_to_state_patch_and_exported_schema(reasoning, valid):
    edge = {"from": "A", "to": "B", "type": "supports", "reasoning": reasoning}
    state = {"nodes": [], "edges": [edge], "frontier": []}
    patch = {"edges": [edge]}
    assert (not state_schema_errors(state)) == valid
    assert (not patch_schema_errors(patch)) == valid
    validator = jsonschema.Draft202012Validator(
        standalone_schema("patch.schema.json"),
    )
    assert validator.is_valid(patch) == valid


def test_detail_cards_escape_edge_reasoning():
    state = {
        "nodes": [{"id": "E1", "type": "evidence", "text": "Observation", "confidence": 0.9}],
        "edges": [
            {"from": "E1", "to": "D1", "type": "leads_to",
             "reasoning": "The <script> tag is text, not executable markup."},
        ],
        "frontier": [],
    }
    cards = node_detail_cards(state)
    assert "&lt;script&gt;" in cards
    assert "<script>" not in cards

