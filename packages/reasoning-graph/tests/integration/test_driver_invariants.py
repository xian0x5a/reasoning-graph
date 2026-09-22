import math
import sys
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_SRC_ROOT = PACKAGE_ROOT / "src"
sys.path.insert(0, str(PACKAGE_SRC_ROOT))

from reasoning_graph.costs import compute_costs
from reasoning_graph.validation import validate_state


def frontier_truth_cost(state: dict, item_id: str = "Q1") -> float:
    costed = compute_costs(state)
    for item in costed["frontier"]:
        if item["id"] == item_id:
            return float(item["truth_cost"])
    raise AssertionError(f"missing frontier item {item_id}")


class ReasoningGraphCostInvariantTests(unittest.TestCase):
    def base_state(self, *, prior: float = 0.5, edges: list[dict] | None = None, factors: list[dict] | None = None) -> dict:
        return {
            "nodes": [
                {"id": "E1", "type": "evidence", "text": "Signal one", "prior": 1.0},
                {"id": "E2", "type": "evidence", "text": "Signal two", "prior": 1.0},
                {"id": "A1", "type": "assumption", "text": "Target assumption", "prior": prior},
            ],
            "edges": edges or [],
            "factors": factors or [],
            "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
        }

    def test_posterior_overrides_prior_edges_and_factors(self) -> None:
        state = self.base_state(
            prior=0.1,
            edges=[
                {"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 100},
                {"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E2A1", "from": "E2", "to": "A1", "type": "supports", "likelihood_ratio": 2},
            ],
            factors=[
                {
                    "id": "F1",
                    "relation": "supports",
                    "target": "A1",
                    "inputs": ["E1", "E2"],
                    "aggregation": {"kind": "likelihood", "if_target_true": 0.9, "if_target_false": 0.1},
                    "reason": "Grouped update should still lose to explicit posterior.",
                }
            ],
        )
        state["nodes"][2]["posterior"] = 0.3

        self.assertAlmostEqual(frontier_truth_cost(state), -math.log(0.3), places=6)

    def test_supporting_likelihood_update_lowers_truth_cost(self) -> None:
        baseline = frontier_truth_cost(self.base_state(prior=0.5))
        supported = frontier_truth_cost(
            self.base_state(
                prior=0.5,
                edges=[{"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 3}],
            )
        )

        self.assertLess(supported, baseline)
        self.assertAlmostEqual(supported, -math.log(0.75), places=6)

    def test_contradicting_likelihood_update_raises_truth_cost(self) -> None:
        baseline = frontier_truth_cost(self.base_state(prior=0.5))
        contradicted = frontier_truth_cost(
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

        grouped = frontier_truth_cost(self.base_state(prior=0.5, edges=edges, factors=[factor]))
        independent = frontier_truth_cost(self.base_state(prior=0.5, edges=edges))

        self.assertGreater(grouped, independent)
        self.assertAlmostEqual(grouped, -math.log(0.8), places=6)
        self.assertAlmostEqual(independent, -math.log(16 / 17), places=6)

    def test_neutral_explanatory_edges_do_not_change_truth_cost(self) -> None:
        baseline = frontier_truth_cost(self.base_state(prior=0.5))
        explanatory = frontier_truth_cost(
            self.base_state(
                prior=0.5,
                edges=[{"reasoning": "The observed signal is more likely when the target claim is true.", "id": "E1A1", "from": "E1", "to": "A1", "type": "supports"}],
            )
        )

        self.assertAlmostEqual(explanatory, baseline, places=6)

    def test_validator_reports_invalid_probability_without_throwing(self) -> None:
        state = self.base_state(prior=0.5)
        state["nodes"][2]["prior"] = "not-a-number"

        result = validate_state(state)

        self.assertFalse(result.ok)
        self.assertTrue(any("prior must be numeric" in error for error in result.errors))
        self.assertTrue(any("cost computation failed" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
