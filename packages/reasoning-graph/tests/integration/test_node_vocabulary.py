"""Node vocabulary contract: models, the packaged schema, and the goal-routing rule stay in sync."""

import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.models import NODE_TYPES, RESULT_NODE_TYPES
from reasoning_graph.schema_validation import load_schema
from reasoning_graph.validation import validate_state


EXPECTED_NODE_TYPES = {"goal", "observation", "constraint", "hypothesis", "test", "candidate_solution"}


def schema_node_types() -> set[str]:
    node = load_schema("state.schema.json")["$defs"]["node"]
    return set(node["properties"]["type"]["enum"])


class NodeVocabularyTests(unittest.TestCase):
    def test_schema_enum_matches_models(self) -> None:
        self.assertEqual(set(NODE_TYPES), EXPECTED_NODE_TYPES)
        self.assertEqual(schema_node_types(), EXPECTED_NODE_TYPES)

    def test_test_results_are_observations_only(self) -> None:
        self.assertEqual(set(RESULT_NODE_TYPES), {"observation"})

    def test_hypothesis_to_goal_edge_is_rejected(self) -> None:
        # Both hypothesis shapes are covered: one carrying its own score, one whose belief
        # comes from a leads_to premise. Neither may reach a goal except through a candidate.
        score_backed = {
            "nodes": [
                {"id": "G1", "type": "goal", "text": "Find answer"},
                {"id": "H1", "type": "hypothesis", "text": "Direct answer", "score": 3},
            ],
            "edges": [{"id": "H1G1", "from": "H1", "to": "G1", "type": "supports", "score": 3, "reasoning": "Claims the goal directly."}],
            "frontier": [{"id": "Q1", "node": "H1", "cost_components": {"truth": "auto"}}],
        }
        premise_backed = {
            "nodes": [
                {"id": "G1", "type": "goal", "text": "Find answer"},
                {"id": "O1", "type": "observation", "text": "Seen in the source", "source": "probe"},
                {"id": "H1", "type": "hypothesis", "text": "Established step"},
            ],
            "edges": [
                {"id": "O1H1", "from": "O1", "to": "H1", "type": "leads_to", "reasoning": "The observation establishes the step."},
                {"id": "H1G1", "from": "H1", "to": "G1", "type": "leads_to", "reasoning": "The step is taken as the answer."},
            ],
        }
        for label, state in {"score-backed": score_backed, "premise-backed": premise_backed}.items():
            with self.subTest(hypothesis=label):
                errors = validate_state(state).errors
                self.assertTrue(any("connects hypothesis H1 directly to goal G1" in error for error in errors), errors)
                self.assertTrue(any("route hypotheses through tests/candidate nodes" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
