"""Edge vocabulary contract: models and the packaged schema stay in sync."""

import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.costs import node_effective_truth_costs
from reasoning_graph.models import EDGE_TYPES
from reasoning_graph.schema_validation import load_schema, state_schema_errors
from reasoning_graph.validation import validate_state


def schema_edge_types() -> set[str]:
    edge = load_schema("state.schema.json")["$defs"]["edge"]
    return set(edge["properties"]["type"]["enum"])


class EdgeVocabularyTests(unittest.TestCase):
    def test_schema_enum_matches_models(self) -> None:
        self.assertEqual(schema_edge_types(), set(EDGE_TYPES))

    def test_removed_assumes_edge_type_is_rejected(self) -> None:
        state = {
            "nodes": [
                {"id": "A1", "type": "hypothesis", "text": "Branch", "score": 3},
                {"id": "D1", "type": "hypothesis", "text": "Conclusion"},
            ],
            "edges": [{"from": "D1", "to": "A1", "type": "assumes"}],
        }
        errors = state_schema_errors(state)
        self.assertTrue(any("assumes" in error for error in errors), errors)


def untyped_edge_state() -> dict:
    """E1 bears on H1 only through an edge that carries the removed `label` instead of a `type`."""
    return {
        "nodes": [
            {"id": "E1", "type": "observation", "text": "A log line", "score": 4},
            {"id": "H1", "type": "hypothesis", "text": "The cause"},
        ],
        "edges": [{"from": "E1", "to": "H1", "label": "supports", "score": 4}],
    }


class UntypedEdgeTests(unittest.TestCase):
    def test_edge_without_a_type_adds_nothing_to_belief(self) -> None:
        # label is a removed field, so it must not stand in for the type.
        labelled = untyped_edge_state()
        without_edge = {**labelled, "edges": []}
        self.assertEqual(node_effective_truth_costs(labelled)["H1"], node_effective_truth_costs(without_edge)["H1"])

    def test_audit_names_label_as_removed_and_points_to_type(self) -> None:
        errors = validate_state(untyped_edge_state()).errors
        self.assertTrue(
            any("label" in error and "removed" in error and "type" in error for error in errors),
            errors,
        )
