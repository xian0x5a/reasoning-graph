"""Edge vocabulary contract: models and the packaged schema stay in sync."""

import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.models import EDGE_TYPES
from reasoning_graph.schema_validation import load_schema, state_schema_errors


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
            "edges": [{"id": "D1-A1-assumes", "from": "D1", "to": "A1", "type": "assumes"}],
        }
        errors = state_schema_errors(state)
        self.assertTrue(any("assumes" in error for error in errors), errors)
