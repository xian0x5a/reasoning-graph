import io
import json
import math
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC_ROOT = PACKAGE_ROOT / "src"
sys.path.insert(0, str(PACKAGE_SRC_ROOT))

from reasoning_graph.costs import node_effective_truth_costs
from reasoning_graph.state import dump_state
from reasoning_graph.validation import validate_state


def truth_cost(state: dict, node_id: str = "A1") -> float:
    return node_effective_truth_costs(state)[node_id]


class ReasoningGraphCostInvariantTests(unittest.TestCase):
    def base_state(self, *, edges: list[dict] | None = None, factors: list[dict] | None = None) -> dict:
        return {
            "nodes": [
                {"id": "E1", "type": "observation", "text": "Signal one"},
                {"id": "E2", "type": "observation", "text": "Signal two"},
                {"id": "A1", "type": "hypothesis", "text": "Target hypothesis"},
            ],
            "edges": edges or [],
            "factors": factors or [],
        }

    def test_recomputed_costs_track_later_evidence(self) -> None:
        # Belief is derived on every read, never cached in state, so later evidence always counts.
        state = self.base_state()
        first = truth_cost(state)
        state["edges"].append(
            {"id": "E1A1", "from": "E1", "to": "A1", "type": "contradicts", "score": 4, "reasoning": "The signal is less likely when A1 holds."}
        )
        state = json.loads(json.dumps(state))

        second = truth_cost(state)

        self.assertAlmostEqual(first, -math.log(0.5), places=6)
        self.assertAlmostEqual(second, -math.log(0.25), places=6)

    def test_supporting_evidence_lowers_truth_cost(self) -> None:
        baseline = truth_cost(self.base_state())
        supported = truth_cost(
            self.base_state(
                edges=[{"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "supports", "score": 4}],
            )
        )

        self.assertLess(supported, baseline)
        self.assertAlmostEqual(supported, -math.log(0.75), places=6)

    def test_contradicting_evidence_raises_truth_cost(self) -> None:
        baseline = truth_cost(self.base_state())
        contradicted = truth_cost(
            self.base_state(
                edges=[{"reasoning": "The observed signal is less likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "contradicts", "score": 4}],
            )
        )

        self.assertGreater(contradicted, baseline)
        self.assertAlmostEqual(contradicted, -math.log(0.25), places=6)

    def test_support_group_replaces_member_updates(self) -> None:
        edges = [
            {"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "supports"},
            {"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E2A1", "from": "E2", "to": "A1", "type": "supports"},
        ]
        factor = {"id": "F1", "edges": ["E1A1", "E2A1"], "score": 4, "note": "Correlated evidence counts once, at ratio 3."}

        grouped = truth_cost(self.base_state(edges=edges, factors=[factor]))
        independent = truth_cost(self.base_state(edges=edges))

        self.assertGreater(grouped, independent)
        self.assertAlmostEqual(grouped, -math.log(0.75), places=6)
        self.assertAlmostEqual(independent, -math.log(0.8), places=6)

    def test_validator_reports_non_finite_json_numbers(self) -> None:
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                state = json.loads(json.dumps(self.base_state()))
                state["nodes"][2]["score"] = invalid

                result = validate_state(state)

                self.assertFalse(result.ok)
                self.assertTrue(
                    any("schema $.nodes[2].score: number must be finite" in error for error in result.errors)
                )

    def test_validator_reports_invalid_score_without_throwing(self) -> None:
        state = self.base_state()
        state["nodes"][2]["score"] = "not-a-number"

        result = validate_state(state)

        self.assertFalse(result.ok)
        self.assertTrue(any("score must be an integer from 1 to 5" in error for error in result.errors))
        self.assertTrue(any("belief computation failed" in error for error in result.errors))

    def test_state_serialization_rejects_non_finite_values_before_writing(self) -> None:
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp_dir, redirect_stdout(output):
            output_path = Path(tmp_dir) / "state.json"
            with self.assertRaises(ValueError):
                dump_state({"not_json": math.nan}, str(output_path))
            self.assertFalse(output_path.exists())

        self.assertEqual(output.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
