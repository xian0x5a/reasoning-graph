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

from reasoning_graph.costs import likelihood_ratio_from_likelihood, node_effective_truth_costs
from reasoning_graph.state import dump_state
from reasoning_graph.validation import validate_state


def truth_cost(state: dict, node_id: str = "A1") -> float:
    return node_effective_truth_costs(state)[node_id]


class ReasoningGraphCostInvariantTests(unittest.TestCase):
    def base_state(self, *, prior: float = 0.5, edges: list[dict] | None = None, factors: list[dict] | None = None) -> dict:
        return {
            "nodes": [
                {"id": "E1", "type": "observation", "text": "Signal one", "prior": 1.0},
                {"id": "E2", "type": "observation", "text": "Signal two", "prior": 1.0},
                {"id": "A1", "type": "hypothesis", "text": "Target hypothesis", "prior": prior},
            ],
            "edges": edges or [],
            "factors": factors or [],
        }

    def test_recomputed_costs_track_later_evidence(self) -> None:
        # Belief is derived on every read, never cached in state, so later evidence always counts.
        state = self.base_state(prior=0.5)
        first = truth_cost(state)
        state["edges"].append(
            {"id": "E1A1", "from": "E1", "to": "A1", "type": "contradicts", "likelihood_ratio": 0.25, "reasoning": "The signal is less likely when A1 holds."}
        )
        state = json.loads(json.dumps(state))

        second = truth_cost(state)

        self.assertAlmostEqual(first, -math.log(0.5), places=6)
        self.assertAlmostEqual(second, -math.log(0.2), places=6)

    def test_supporting_likelihood_update_lowers_truth_cost(self) -> None:
        baseline = truth_cost(self.base_state(prior=0.5))
        supported = truth_cost(
            self.base_state(
                prior=0.5,
                edges=[{"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 3}],
            )
        )

        self.assertLess(supported, baseline)
        self.assertAlmostEqual(supported, -math.log(0.75), places=6)

    def test_contradicting_likelihood_update_raises_truth_cost(self) -> None:
        baseline = truth_cost(self.base_state(prior=0.5))
        contradicted = truth_cost(
            self.base_state(
                prior=0.5,
                edges=[{"reasoning": "The observed signal is less likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "contradicts", "likelihood_ratio": 0.25}],
            )
        )

        self.assertGreater(contradicted, baseline)
        self.assertAlmostEqual(contradicted, -math.log(0.2), places=6)

    def test_grouped_support_factor_replaces_member_likelihood_updates(self) -> None:
        edges = [
            {"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 4},
            {"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E2A1", "from": "E2", "to": "A1", "type": "supports", "likelihood_ratio": 4},
        ]
        factor = {
            "id": "F1",
            "relation": "supports",
            "target": "A1",
            "inputs": ["E1", "E2"],
            "aggregation": {"kind": "likelihood", "if_target_true": 0.8, "if_target_false": 0.2},
            "reason": "Correlated evidence should count once as grouped LR 4.",
        }

        grouped = truth_cost(self.base_state(prior=0.5, edges=edges, factors=[factor]))
        independent = truth_cost(self.base_state(prior=0.5, edges=edges))

        self.assertGreater(grouped, independent)
        self.assertAlmostEqual(grouped, -math.log(0.8), places=6)
        self.assertAlmostEqual(independent, -math.log(16 / 17), places=6)

    def test_neutral_explanatory_edges_do_not_change_truth_cost(self) -> None:
        baseline = truth_cost(self.base_state(prior=0.5))
        explanatory = truth_cost(
            self.base_state(
                prior=0.5,
                edges=[{"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "supports"}],
            )
        )

        self.assertAlmostEqual(explanatory, baseline, places=6)

    def test_inherited_tiny_belief_keeps_finite_cost_after_likelihood_update(self) -> None:
        for relation, ratio in (("supports", 2.0), ("contradicts", 5e-324)):
            with self.subTest(relation=relation):
                state = self.base_state(prior=1e-200, edges=[
                    {"id": "E1-A1", "from": "E1", "to": "A1", "type": "leads_to", "reasoning": "A1 requires the rare premise."},
                    {"id": "E2-A1", "from": "E2", "to": "A1", "type": relation, "likelihood_ratio": ratio,
                     "reasoning": "The signal updates the inherited belief."},
                ])
                state["nodes"][0]["prior"] = 1e-200
                original_nodes = json.loads(json.dumps(state["nodes"]))

                cost = truth_cost(state)

                self.assertTrue(math.isfinite(cost))
                self.assertAlmostEqual(cost, -2 * math.log(1e-200) - math.log(ratio), places=6)
                self.assertEqual(state["nodes"], original_nodes)
                self.assertTrue(validate_state(state).ok)

    def test_likelihood_ratios_reject_non_finite_values(self) -> None:
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                state = self.base_state(
                    edges=[
                        {
                            "id": "E1A1",
                            "from": "E1",
                            "to": "A1",
                            "type": "supports",
                            "likelihood_ratio": invalid,
                        }
                    ]
                )
                with self.assertRaises(ValueError):
                    node_effective_truth_costs(state)

    def test_likelihood_ratio_from_likelihood_rejects_extreme_overflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "ratio must be finite"):
            likelihood_ratio_from_likelihood({"if_target_true": 1.0, "if_target_false": 5e-324})

        tiny_ratio = likelihood_ratio_from_likelihood(
            {"if_target_true": 5e-324, "if_target_false": 1.0}
        )
        self.assertTrue(math.isfinite(tiny_ratio))
        self.assertGreater(tiny_ratio, 0.0)

    def test_belief_rejects_extreme_edge_ratio(self) -> None:
        state = self.base_state(
            edges=[
                {
                    "id": "E1A1",
                    "from": "E1",
                    "to": "A1",
                    "type": "supports",
                    "likelihood": {"if_target_true": 1.0, "if_target_false": 5e-324},
                }
            ]
        )

        with self.assertRaisesRegex(ValueError, "ratio must be finite"):
            node_effective_truth_costs(state)

    def test_validator_reports_non_finite_json_numbers(self) -> None:
        for invalid in (math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                state = json.loads(json.dumps(self.base_state()))
                state["nodes"][2]["prior"] = invalid

                result = validate_state(state)

                self.assertFalse(result.ok)
                self.assertTrue(
                    any("schema $.nodes[2].prior: number must be finite" in error for error in result.errors)
                )

    def test_validator_reports_invalid_probability_without_throwing(self) -> None:
        state = self.base_state(prior=0.5)
        state["nodes"][2]["prior"] = "not-a-number"

        result = validate_state(state)

        self.assertFalse(result.ok)
        self.assertTrue(any("prior must be numeric" in error for error in result.errors))
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
