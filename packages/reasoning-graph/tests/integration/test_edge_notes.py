"""An edge takes an optional note, the same field nodes have; nothing forces one."""

import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.models import EDGE_TYPES
from reasoning_graph.render import node_detail_cards
from reasoning_graph.schema_validation import patch_schema_errors, state_schema_errors
from reasoning_graph.validation import validate_state


def state_with(**edge_fields: object) -> dict:
    return {
        "nodes": [
            {"id": "O1", "type": "observation", "text": "Deployment finished at 02:10"},
            {"id": "H1", "type": "hypothesis", "text": "The deployment caused the outage"},
        ],
        "edges": [{"id": "O1-H1", "from": "O1", "to": "H1", "type": "supports", **edge_fields}],
    }


@pytest.mark.parametrize("edge_type", sorted(EDGE_TYPES))
def test_every_edge_type_is_valid_without_a_note(edge_type):
    edge = {"id": "A-B", "from": "A", "to": "B", "type": edge_type}
    assert not patch_schema_errors({"edges": [edge]})
    assert not patch_schema_errors({"edges": [{**edge, "note": "The source supplies what the target needs."}]})


def test_state_is_valid_with_and_without_an_edge_note():
    assert validate_state(state_with()).ok
    assert validate_state(state_with(note="The first failing request came two minutes later.")).ok


@pytest.mark.parametrize("note", [17, None, ["text"]])
def test_edge_note_must_be_text(note):
    assert state_schema_errors(state_with(note=note))
    assert patch_schema_errors({"edges": state_with(note=note)["edges"]})


def test_removed_reasoning_is_rejected_and_names_note():
    state = state_with(reasoning="The first failing request came two minutes later.")
    assert state_schema_errors(state)
    assert patch_schema_errors({"edges": state["edges"]})
    errors = validate_state(state).errors
    assert any("edge O1-H1: reasoning was removed; use the optional note" in error for error in errors), errors


def test_detail_cards_show_and_escape_edge_notes():
    state = state_with(note="The <script> tag is text, not executable markup.")
    cards = node_detail_cards(state)
    assert "&lt;script&gt;" in cards
    assert "<script>" not in cards
    # An edge without a note still lists its relationship.
    assert "O1 → H1 (supports)" in node_detail_cards(state_with())
