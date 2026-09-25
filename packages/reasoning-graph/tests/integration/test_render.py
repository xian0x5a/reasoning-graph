import json
import re
import sys
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.identities import render_identity_map
from reasoning_graph.offline_render import offline_graph_svg
from reasoning_graph.render import html_document, to_mermaid


class RenderIdentityTests(unittest.TestCase):
    def state(self, reverse: bool = False) -> dict:
        nodes = [
            {"id": "A-B", "type": "hypothesis", "text": "hyphen", "prior": 0.6},
            {"id": "A_B", "type": "hypothesis", "text": "underscore", "prior": 0.4},
            {"id": "A B", "type": "goal", "text": "space"},
        ]
        if reverse:
            nodes.reverse()
        return {
            "nodes": nodes,
            "edges": [
                {"id": "A-B>A_B", "from": "A-B", "to": "A_B", "type": "supports", "likelihood_ratio": 2, "reasoning": "The hyphenated claim supports the underscored claim."},
                {"id": "A B>A-B", "from": "A B", "to": "A-B", "type": "leads_to", "reasoning": "The goal motivates the hyphenated claim."},
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
                {"id": "A-B>A B", "from": "A-B", "to": "A B", "type": "answers", "reasoning": "The hyphenated candidate answers the goal."},
                {"id": "A_B-A B-answers", "from": "A_B", "to": "A B", "type": "answers", "reasoning": "The underscored candidate answers the goal."},
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

    def test_offline_svg_renders_factors_and_replaces_member_edges(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "valid" / "factors-state.json"
        state = json.loads(fixture.read_text(encoding="utf-8"))
        identities = render_identity_map(state)
        svg = offline_graph_svg(state, identities=identities)
        factor_id = identities.factor("F_SUPPORTS_A1")

        self.assertIsNotNone(factor_id)
        self.assertIn(f'<g id="{factor_id}" class="node factor" data-factor-id="F_SUPPORTS_A1"', svg)
        self.assertIn(f"LS-{identities.node('E1')} LE-{factor_id}", svg)
        self.assertIn(f"LS-{factor_id} LE-{identities.node('A1')}", svg)
        self.assertNotIn(f"LS-{identities.node('E1')} LE-{identities.node('A1')}", svg)
        self.assertIn("supports joint likelihood", svg)

    def test_mermaid_preserves_declared_factor_and_input_order(self) -> None:
        state = {
            "nodes": [
                {"id": "I_1", "type": "observation", "prior": 0.9},
                {"id": "I-1", "type": "observation", "prior": 0.9},
                {"id": "TZ", "type": "hypothesis", "prior": 0.5},
                {"id": "TA", "type": "hypothesis", "prior": 0.5},
            ],
            "edges": [
                {"id": f"{source}-{target}", "from": source, "to": target, "type": "supports", "reasoning": "The observation supports this claim."}
                for target in ("TZ", "TA") for source in ("I_1", "I-1")
            ],
            "factors": [
                {"id": "Z", "relation": "supports", "inputs": ["I_1", "I-1"], "target": "TZ",
                 "aggregation": {"kind": "likelihood", "if_target_true": 0.8, "if_target_false": 0.2}},
                {"id": "A", "relation": "supports", "inputs": ["I-1", "I_1"], "target": "TA",
                 "aggregation": {"kind": "likelihood", "if_target_true": 0.8, "if_target_false": 0.2}},
            ],
        }
        identities = render_identity_map(state)
        source = to_mermaid(state, identities=identities)
        z_factor_id = identities.factor("Z")
        a_factor_id = identities.factor("A")

        self.assertLess(source.index(f'{z_factor_id}{{{{"Z'), source.index(f'{a_factor_id}{{{{"A'))
        self.assertLess(
            source.index(f'{identities.node("I_1")} -. grouped supports .-> {z_factor_id}'),
            source.index(f'{identities.node("I-1")} -. grouped supports .-> {z_factor_id}'),
        )

    def test_offline_svg_is_order_independent_for_nodes_edges_factors_and_inputs(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "valid" / "factors-state.json"
        state = json.loads(fixture.read_text(encoding="utf-8"))
        reversed_state = {
            **state,
            "nodes": list(reversed(state["nodes"])),
            "edges": list(reversed(state["edges"])),
            "factors": [
                {**factor, "inputs": list(reversed(factor["inputs"]))}
                for factor in reversed(state["factors"])
            ],
        }

        self.assertEqual(offline_graph_svg(state), offline_graph_svg(reversed_state))

    def test_offline_svg_keeps_raw_node_and_factor_positions_separate(self) -> None:
        raw_node_id = "@factor:factor_F1"
        state = {
            "nodes": [
                {"id": raw_node_id, "type": "observation", "prior": 0.9},
                {"id": "E2", "type": "observation", "prior": 0.9},
                {"id": "A1", "type": "hypothesis", "prior": 0.5},
            ],
            "edges": [
                {"id": f"{source}-A1", "from": source, "to": "A1", "type": "supports", "reasoning": "The observation supports A1."}
                for source in (raw_node_id, "E2")
            ],
            "factors": [{"id": "F1", "relation": "supports", "inputs": [raw_node_id, "E2"], "target": "A1",
                         "aggregation": {"kind": "likelihood", "if_target_true": 0.8, "if_target_false": 0.2}}],
        }
        identities = render_identity_map(state)
        svg = offline_graph_svg(state, identities=identities)

        node_id = identities.node(raw_node_id)
        factor_id = identities.factor("F1")
        self.assertIsNotNone(node_id)
        self.assertIsNotNone(factor_id)
        root = ElementTree.fromstring(svg)
        node_group = next(element for element in root.iter() if element.get("data-node-id") == raw_node_id)
        factor_group = next(element for element in root.iter() if element.get("data-factor-id") == "F1")
        node_shape = next(element for element in node_group if element.tag.endswith("rect"))
        factor_shape = next(element for element in factor_group if element.tag.endswith("polygon"))
        factor_points = [tuple(map(int, point.split(","))) for point in factor_shape.get("points", "").split()]
        node_position = (int(node_shape.get("x", "0")), int(node_shape.get("y", "0")))
        factor_position = (min(x for x, _ in factor_points), min(y for _, y in factor_points))

        self.assertEqual(node_group.get("id"), node_id)
        self.assertEqual(factor_group.get("id"), factor_id)
        self.assertNotEqual(node_position, factor_position)

    def test_offline_presentation_omits_factors_with_unselected_members(self) -> None:
        state = {
            "nodes": [
                {"id": "E1", "type": "observation", "prior": 0.9},
                {"id": "E2", "type": "observation", "prior": 0.9},
                {"id": "A1", "type": "hypothesis", "prior": 0.5},
            ],
            "edges": [
                {"id": "E1-A1-supports", "from": "E1", "to": "A1", "type": "supports", "reasoning": "E1 supports A1."},
                {"id": "E2-A1-supports", "from": "E2", "to": "A1", "type": "supports", "reasoning": "E2 supports A1."},
            ],
            "factors": [{"id": "F1", "relation": "supports", "inputs": ["E1", "E2"], "target": "A1",
                         "aggregation": {"kind": "likelihood", "if_target_true": 0.8, "if_target_false": 0.2}}],
        }
        identities = render_identity_map(state)
        presentation_svg = offline_graph_svg(state, {"E1", "A1"}, identities=identities)
        audit_svg = offline_graph_svg(state, identities=identities)
        presentation_mermaid = to_mermaid(state, {"E1", "A1"}, identities=identities)
        audit_mermaid = to_mermaid(state, identities=identities)

        self.assertNotIn('data-factor-id="F1"', presentation_svg)
        self.assertIn('data-factor-id="F1"', audit_svg)
        self.assertNotIn(f"LE-{identities.factor('F1')}", presentation_svg)
        self.assertNotIn("grouped supports", presentation_mermaid)
        self.assertIn("grouped supports", audit_mermaid)
        # Hidden factor members still contribute to the target's final belief.
        self.assertIn("belief 0.8", presentation_svg)
        self.assertIn("belief 0.8", presentation_mermaid)


class GraphCanvasLayoutTests(unittest.TestCase):
    def test_mermaid_wrapper_fills_canvas_and_view_stays_clamped(self) -> None:
        """Mermaid renders inside its own <pre class="mermaid"> wrapper, so the wrapper
        has to carry the canvas height: otherwise the svg's height:100% cannot resolve,
        the graph collapses into an intrinsic-height strip and pan/zoom clips inside it."""
        state = {
            "nodes": [
                {"id": "E1", "type": "observation", "text": "Observed premise", "prior": 0.9},
                {"id": "G1", "type": "goal", "text": "Answer the question"},
            ],
            "edges": [{"id": "E1-G1-leads_to", "from": "E1", "to": "G1", "type": "leads_to", "reasoning": "E1 motivates G1."}],
        }
        document = html_document(state, to_mermaid(state))

        wrapper_rule = re.search(r"\.graph-canvas \.mermaid \{([^}]*)\}", document)
        self.assertIsNotNone(wrapper_rule)
        self.assertIn("height: 100%", wrapper_rule.group(1))
        self.assertIn('<pre class="mermaid">', document)

        # The canvas is a real focus target: it shows a focus ring, paints a dotted
        # sheet, and only the focused canvas consumes the wheel.
        self.assertIn('class="mermaid-wrap graph-canvas graph-canvas-audit" tabindex="0"', document)
        self.assertIn(".graph-canvas:focus {", document)
        self.assertIn("radial-gradient(circle", document)
        self.assertIn("if (!canvas.contains(document.activeElement)) return;", document)
        # Hover only tints the sheet and border; the solid ring stays focus-only.
        self.assertIn(".graph-canvas:hover:not(:focus) { border-color: #bfdbfe;", document)
        # Control buttons acknowledge the press with a tint, a ring, and a sink.
        self.assertIn(".graph-controls button:active {", document)
        self.assertIn("transform: translateY(1px);", document)

        # The mode button keeps one label (pressed styling carries the state) and the
        # control bar is spaced away from the canvas edge.
        self.assertNotIn("Canvas mode on", document)
        self.assertIn(".graph-section .section-head { margin-bottom:", document)
        self.assertIn(".graph-controls button { white-space: nowrap;", document)

        # Wheel zoom is capped by the fitted content box, while drag pan stays
        # unbounded on purpose: dragging the graph off the canvas is allowed and
        # recovered with "Reset view", so no pan clamp may creep back in.
        self.assertIn("const maxZoom = 50;", document)
        self.assertIn("bounds.width", document)
        self.assertNotIn("clampView", document)


if __name__ == "__main__":
    unittest.main()
