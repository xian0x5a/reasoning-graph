import sys
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.identities import render_identity_map
from reasoning_graph.offline_render import offline_graph_svg
from reasoning_graph.render import html_document, to_mermaid


class RenderIdentityTests(unittest.TestCase):
    def state(self, reverse: bool = False) -> dict:
        nodes = [
            {"id": "A-B", "type": "assumption", "text": "hyphen", "prior": 0.6},
            {"id": "A_B", "type": "assumption", "text": "underscore", "prior": 0.4},
            {"id": "A B", "type": "goal", "text": "space"},
        ]
        if reverse:
            nodes.reverse()
        return {
            "nodes": nodes,
            "edges": [
                {"from": "A-B", "to": "A_B", "type": "supports", "likelihood_ratio": 2, "reasoning": "The hyphenated claim supports the underscored claim."},
                {"from": "A B", "to": "A-B", "type": "leads_to", "reasoning": "The goal motivates the hyphenated claim."},
            ],
        }

    def test_identity_allocation_is_collision_free_and_order_independent(self) -> None:
        state = self.state()
        state["factors"] = [{"id": "F-1"}, {"id": "F_1"}]
        reversed_state = self.state(reverse=True)
        reversed_state["factors"] = list(reversed(state["factors"]))
        first = render_identity_map(state)
        second = render_identity_map(reversed_state)

        self.assertEqual(first, second)
        self.assertEqual(len(set(first.node_ids.values())), 3)
        self.assertEqual(len(set(first.factor_ids.values())), 2)
        self.assertEqual(first.node_ids["A B"], "A_B")
        self.assertEqual(first.node_ids["A-B"], "A_B_2")
        self.assertEqual(first.node_ids["A_B"], "A_B_3")
        self.assertNotEqual(first.factor_ids["F-1"], first.factor_ids["F_1"])

    def test_mermaid_offline_and_html_share_node_identity_map(self) -> None:
        state = self.state()
        identities = render_identity_map(state)
        source = to_mermaid(state, identities=identities)
        svg = offline_graph_svg(state, identities=identities)
        document = html_document(state, source, render_mode="offline")

        for raw_id, render_id in identities.node_ids.items():
            self.assertIn(f'click {render_id} "#details-{render_id}"', source)
            self.assertIn(f'id="{render_id}"', svg)
            self.assertIn(f'data-node-id="{raw_id}"', svg)
            self.assertIn(f'href="#details-{render_id}"', svg)
            self.assertIn(f'id="details-{render_id}"', document)
        self.assertIn('"from": "A_B_2", "to": "A_B_3"', document)
        self.assertIn('"from": "A_B", "to": "A_B_2"', document)
        self.assertIn("belief 0.571", source)
        self.assertIn("belief 0.571", svg)
        self.assertIn("Effective belief: 0.571429", document)
        self.assertIn("Local prior: 0.4", document)

    def test_html_focus_map_uses_collision_safe_candidate_ids(self) -> None:
        state = {
            "nodes": [
                {"id": "A-B", "type": "candidate_solution", "text": "hyphen", "prior": 0.6, "answer_kind": "exact_answer"},
                {"id": "A_B", "type": "candidate_solution", "text": "underscore", "prior": 0.4, "answer_kind": "exact_answer"},
                {"id": "A B", "type": "goal", "text": "goal"},
            ],
            "edges": [
                {"from": "A-B", "to": "A B", "type": "answers", "reasoning": "The hyphenated candidate answers the goal."},
                {"from": "A_B", "to": "A B", "type": "answers", "reasoning": "The underscored candidate answers the goal."},
            ],
            "frontier": [],
            "report": {"candidates": [{"id": "A-B"}, {"id": "A_B"}]},
        }
        identities = render_identity_map(state)
        document = html_document(state, to_mermaid(state, identities=identities), render_mode="offline")

        for raw_id in ("A-B", "A_B"):
            render_id = identities.node_ids[raw_id]
            self.assertIn(f'option value="{render_id}">{raw_id}</option>', document)
            self.assertIn(f'"{render_id}": ["{render_id}"]', document)

    def test_filtered_mermaid_view_keeps_full_graph_identities(self) -> None:
        state = self.state()
        identities = render_identity_map(state)
        source = to_mermaid(state, {"A-B", "A B"}, identities=identities)

        self.assertIn(f'click {identities.node_ids["A-B"]} "#details-{identities.node_ids["A-B"]}"', source)
        self.assertIn(f'click {identities.node_ids["A B"]} "#details-{identities.node_ids["A B"]}"', source)
        self.assertNotIn(f'click {identities.node_ids["A_B"]} ', source)


if __name__ == "__main__":
    unittest.main()
