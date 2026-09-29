import json
import re
import sys
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.identities import render_identity_map
from reasoning_graph.mermaid import to_mermaid
from reasoning_graph.offline_render import offline_graph_svg
from reasoning_graph.page import html_document


class RenderIdentityTests(unittest.TestCase):
    def state(self, reverse: bool = False) -> dict:
        nodes = [
            {"id": "A.B", "type": "observation", "text": "hyphen", "score": 3},
            {"id": "A_B", "type": "hypothesis", "text": "underscore", "score": 2},
            {"id": "A B", "type": "goal", "text": "space"},
        ]
        if reverse:
            nodes.reverse()
        return {
            "nodes": nodes,
            "edges": [
                {"from": "A.B", "to": "A_B", "type": "supports", "score": 3},
                {"from": "A B", "to": "A.B", "type": "leads_to"},
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
        self.assertEqual(first.node_ids["A.B"], "A_B_2")
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
        # Score 2 gives odds 3/7; the supporting ratio 2 gives 6/13.
        self.assertIn("belief 0.462", source)
        self.assertIn("belief 0.462", svg)
        self.assertIn("Effective belief: 0.461538", document)
        self.assertIn("Score: 2", document)

    def test_html_focus_map_uses_collision_safe_candidate_ids(self) -> None:
        state = {
            "nodes": [
                {"id": "A.B", "type": "candidate_solution", "text": "hyphen", "score": 3, "answer_kind": "exact_answer"},
                {"id": "A_B", "type": "candidate_solution", "text": "underscore", "score": 2, "answer_kind": "exact_answer"},
                {"id": "A B", "type": "goal", "text": "goal"},
            ],
            "edges": [
                {"from": "A.B", "to": "A B", "type": "answers"},
                {"from": "A_B", "to": "A B", "type": "answers"},
            ],
        }
        identities = render_identity_map(state)
        document = html_document(state, to_mermaid(state, identities=identities), render_mode="offline")

        for raw_id in ("A.B", "A_B"):
            render_id = identities.node_ids[raw_id]
            self.assertIn(f'option value="{render_id}">{raw_id}</option>', document)
            self.assertIn(f'"{render_id}": ["{render_id}"]', document)

    def test_html_focus_map_covers_full_candidate_derivation(self) -> None:
        """Focusing a candidate must light its whole derivation chain (tests, the
        observations they produced, and the hypotheses that prompted them), not stop
        at the first observation, while leaving rival and contradicting branches dim."""

        def edge(source: str, edge_type: str, target: str) -> dict:
            return {"from": source, "to": target, "type": edge_type}

        state = {
            "nodes": [
                {"id": "G1", "type": "goal", "text": "goal"},
                {"id": "O1", "type": "observation", "text": "clue"},
                {"id": "H1", "type": "hypothesis", "text": "clue encodes data", "score": 4},
                {"id": "T1", "type": "test", "text": "extract data"},
                {"id": "O4", "type": "observation", "text": "extracted data"},
                {"id": "H3", "type": "hypothesis", "text": "decoding A", "score": 4},
                {"id": "T3", "type": "test", "text": "decode with A"},
                {"id": "O5", "type": "observation", "text": "decoding A works"},
                {"id": "CS1", "type": "candidate_solution", "text": "answer A", "answer_kind": "exact_answer"},
                {"id": "H4", "type": "hypothesis", "text": "decoding B", "score": 2},
                {"id": "O6", "type": "observation", "text": "decoding B fails"},
                {"id": "CS2", "type": "candidate_solution", "text": "answer B", "score": 1, "answer_kind": "exact_answer"},
            ],
            "edges": [
                edge("O1", "supports", "H1"),
                edge("H1", "prompts", "T1"),
                edge("T1", "leads_to", "O4"),
                edge("O4", "leads_to", "H3"),
                edge("H3", "prompts", "T3"),
                edge("T3", "leads_to", "O5"),
                edge("O5", "supports", "H3"),
                edge("H3", "leads_to", "CS1"),
                edge("CS1", "answers", "G1"),
                edge("O4", "leads_to", "H4"),
                edge("O6", "contradicts", "H4"),
                edge("H4", "leads_to", "CS2"),
                edge("CS2", "answers", "G1"),
            ],
        }
        document = html_document(state, to_mermaid(state), render_mode="offline")
        page_data = re.search(r'<script type="application/json" id="page-data">(.*?)</script>', document, re.DOTALL)
        focus_map = json.loads(page_data.group(1))["candidateFocusMap"]

        self.assertEqual(set(focus_map["CS1"]), {"CS1", "H3", "O4", "O5", "T3", "T1", "H1", "O1"})
        self.assertEqual(set(focus_map["CS2"]), {"CS2", "H4", "O4", "T1", "H1", "O1"})

    def test_html_candidates_come_from_the_graph(self) -> None:
        state = {
            "nodes": [
                {"id": "CS1", "type": "candidate_solution", "text": "First answer", "score": 3, "answer_kind": "exact_answer"},
                {"id": "CS2", "type": "candidate_solution", "text": "Second answer", "score": 2, "answer_kind": "exact_answer"},
                {"id": "G1", "type": "goal", "text": "goal"},
            ],
            "edges": [
                {"from": "CS1", "to": "G1", "type": "answers"},
                {"from": "CS2", "to": "G1", "type": "answers"},
            ],
        }
        identities = render_identity_map(state)
        document = html_document(state, to_mermaid(state, identities=identities), render_mode="offline")

        for raw_id in ("CS1", "CS2"):
            self.assertIn(f'option value="{identities.node_ids[raw_id]}">{raw_id}</option>', document)
        self.assertIn("First answer", document)

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
        self.assertIn("supports group, score 4", svg)

    def test_mermaid_preserves_declared_factor_and_input_order(self) -> None:
        state = {
            "nodes": [
                {"id": "I_1", "type": "observation", "score": 5},
                {"id": "I.1", "type": "observation", "score": 5},
                {"id": "TZ", "type": "hypothesis", "score": 3},
                {"id": "TA", "type": "hypothesis", "score": 3},
            ],
            "edges": [
                {"from": source, "to": target, "type": "supports"}
                for target in ("TZ", "TA") for source in ("I_1", "I.1")
            ],
            "factors": [
                {"id": "Z", "edges": ["I_1-TZ", "I.1-TZ"], "score": 4},
                {"id": "A", "edges": ["I.1-TA", "I_1-TA"], "score": 4},
            ],
        }
        identities = render_identity_map(state)
        source = to_mermaid(state, identities=identities)
        z_factor_id = identities.factor("Z")
        a_factor_id = identities.factor("A")

        self.assertLess(source.index(f'{z_factor_id}{{{{"Z'), source.index(f'{a_factor_id}{{{{"A'))
        self.assertLess(
            source.index(f'{identities.node("I_1")} -. grouped supports .-> {z_factor_id}'),
            source.index(f'{identities.node("I.1")} -. grouped supports .-> {z_factor_id}'),
        )

    def test_offline_svg_is_order_independent_for_nodes_edges_factors_and_inputs(self) -> None:
        fixture = Path(__file__).resolve().parents[1] / "fixtures" / "valid" / "factors-state.json"
        state = json.loads(fixture.read_text(encoding="utf-8"))
        reversed_state = {
            **state,
            "nodes": list(reversed(state["nodes"])),
            "edges": list(reversed(state["edges"])),
            "factors": [
                {**factor, "edges": list(reversed(factor["edges"]))}
                for factor in reversed(state["factors"])
            ],
        }

        self.assertEqual(offline_graph_svg(state), offline_graph_svg(reversed_state))

    def test_offline_svg_keeps_raw_node_and_factor_positions_separate(self) -> None:
        raw_node_id = "@factor:factor_F1"
        state = {
            "nodes": [
                {"id": raw_node_id, "type": "observation", "score": 5},
                {"id": "E2", "type": "observation", "score": 5},
                {"id": "A1", "type": "hypothesis", "score": 3},
            ],
            "edges": [
                {"from": source, "to": "A1", "type": "supports"}
                for source in (raw_node_id, "E2")
            ],
            "factors": [{"id": "F1", "edges": [f"{raw_node_id}-A1", "E2-A1"], "score": 4}],
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

class GraphCanvasLayoutTests(unittest.TestCase):
    def test_mermaid_wrapper_fills_canvas_and_view_stays_clamped(self) -> None:
        """Mermaid renders inside its own <pre class="mermaid"> wrapper, so the wrapper
        has to carry the canvas height: otherwise the svg's height:100% cannot resolve,
        the graph collapses into an intrinsic-height strip and pan/zoom clips inside it."""
        state = {
            "nodes": [
                {"id": "E1", "type": "observation", "text": "Observed premise", "score": 5},
                {"id": "G1", "type": "goal", "text": "Answer the question"},
            ],
            "edges": [{"from": "E1", "to": "G1", "type": "leads_to"}],
        }
        document = html_document(state, to_mermaid(state))

        wrapper_rule = re.search(r"\.graph-canvas \.mermaid \{([^}]*)\}", document)
        self.assertIsNotNone(wrapper_rule)
        self.assertIn("height: 100%", wrapper_rule.group(1))
        self.assertIn('<pre class="mermaid">', document)

        # The canvas is a real focus target: it shows a focus ring, paints a dotted
        # sheet, and only the focused canvas consumes the wheel.
        self.assertIn('class="mermaid-wrap graph-canvas graph-canvas-audit" tabindex="0"', document)
        # :focus-within, because clicking a node link focuses the <a> inside the canvas
        # and the wheel still zooms then, so the ring must stay.
        self.assertIn(".graph-canvas:focus-within {", document)
        self.assertIn("radial-gradient(circle", document)
        self.assertIn("if (!canvas.contains(document.activeElement)) return;", document)
        # Hover only tints the sheet and border; the solid ring stays focus-only.
        self.assertIn(".graph-canvas:hover:not(:focus-within) { border-color: #bfdbfe;", document)
        # Control buttons acknowledge the press with a tint, a ring, and a sink.
        self.assertIn(".graph-controls button:active {", document)
        self.assertIn("transform: translateY(1px);", document)

        # The mode button keeps one label (pressed styling carries the state) and the
        # control bar is spaced away from the canvas edge.
        self.assertNotIn("Canvas mode on", document)
        # Canvas mode starts on for mouse/trackpad only: on touch screens it would
        # set touch-action:none and trap page swipes over the tall canvas.
        self.assertIn('setCanvasMode(window.matchMedia("(pointer: fine)").matches);', document)
        # Esc releases the captured wheel so the page scrolls again.
        self.assertIn("if (event.key === \"Escape\" && canvas.contains(document.activeElement)) document.activeElement.blur();", document)
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
