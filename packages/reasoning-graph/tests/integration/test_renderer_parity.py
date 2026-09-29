"""Mermaid and the offline SVG draw one graph: same nodes, labels, edges and colours (#18)."""

import html
import json
import re
import sys
import unittest
from pathlib import Path
from xml.etree import ElementTree

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.mermaid import to_mermaid
from reasoning_graph.offline_render import offline_graph_svg

FIXTURES = PACKAGE_ROOT / "tests" / "fixtures" / "valid"
SVG = "{http://www.w3.org/2000/svg}"

MIXED_STATE = {
    "summary": {"answer": "CS1"},
    "nodes": [
        {"id": "G1", "type": "goal", "text": "Find it"},
        {"id": "O1", "type": "observation", "text": "seen", "source": "s", "quote": "q"},
        {"id": "C1", "type": "constraint", "text": "must"},
        {"id": "H1", "type": "hypothesis", "text": "maybe", "score": 4},
        {"id": "T1", "type": "test", "text": "check"},
        {"id": "T2", "type": "test", "text": "skipped", "not_run": "no access"},
        {"id": "CS1", "type": "candidate_solution", "text": "it"},
    ],
    "edges": [
        {"from": "O1", "to": "H1", "type": "supports", "score": 4},
        {"from": "H1", "to": "T1", "type": "prompts"},
        {"from": "H1", "to": "T2", "type": "prompts"},
        {"from": "T1", "to": "O1", "type": "leads_to"},
        {"from": "H1", "to": "CS1", "type": "leads_to"},
        {"from": "C1", "to": "CS1", "type": "contradicts", "score": 2},
        {"from": "CS1", "to": "G1", "type": "answers"},
    ],
}

MERMAID_NODE = re.compile(r'^\s+(\w+)(?:\["(.*)"\]|\{\{"(.*)"\}\})$')
MERMAID_EDGE = re.compile(r"^\s+(\w+) (?:-- (.+?) -->|-\. (.+?) \.->) (\w+)$")
MERMAID_CLASS_DEF = re.compile(r"^\s+classDef (\w+) fill:(#\w+),stroke:(#\w+)")
MERMAID_CLASS = re.compile(r"^\s+class ([\w,]+) (\w+);$")


def mermaid_graph(source: str) -> tuple[dict[str, str], set[tuple[str, str, str]], dict[str, tuple[str, str]]]:
    labels: dict[str, str] = {}
    edges: set[tuple[str, str, str]] = set()
    class_colors: dict[str, tuple[str, str]] = {}
    node_class: dict[str, str] = {}
    for line in source.splitlines():
        if match := MERMAID_EDGE.match(line):
            edges.add((match[1], match[4], match[2] or match[3]))
        elif match := MERMAID_NODE.match(line):
            raw_label = match[2] if match[2] is not None else match[3]
            labels[match[1]] = html.unescape(raw_label.replace("<br/>", "\n"))
        elif match := MERMAID_CLASS_DEF.match(line):
            class_colors[match[1]] = (match[2], match[3])
        elif match := MERMAID_CLASS.match(line):
            for node_id in match[1].split(","):
                node_class[node_id] = match[2]
    colors = {node_id: class_colors[cls] for node_id, cls in node_class.items()}
    return labels, edges, colors


def svg_graph(svg: str) -> tuple[dict[str, str], set[tuple[str, str, str]], dict[str, tuple[str, str]]]:
    root = ElementTree.fromstring(svg)
    labels: dict[str, str] = {}
    colors: dict[str, tuple[str, str]] = {}
    for group in root.iter(f"{SVG}g"):
        if "node" not in (group.get("class") or "").split():
            continue
        labels[group.get("id")] = "\n".join(tspan.text or "" for tspan in group.iter(f"{SVG}tspan"))
        shape = next(child for child in group if child.tag in {f"{SVG}rect", f"{SVG}polygon"})
        colors[group.get("id")] = (shape.get("fill"), shape.get("stroke"))
    paths = [path for path in root.iter(f"{SVG}path") if "flowchart-link" in (path.get("class") or "")]
    edge_labels = [text.findtext(f"{SVG}tspan") for text in root.iter(f"{SVG}text") if text.get("class") == "edgeLabel"]
    edges = set()
    for path, label in zip(paths, edge_labels, strict=True):
        ends = dict(part.split("-", 1) for part in path.get("class").split() if part[:3] in {"LS-", "LE-"})
        edges.add((ends["LS"], ends["LE"], label))
    return labels, edges, colors


def parity_states() -> dict[str, dict]:
    states = {path.name: json.loads(path.read_text(encoding="utf-8")) for path in sorted(FIXTURES.glob("*.json"))}
    states["mixed"] = MIXED_STATE
    return states


class RendererParityTests(unittest.TestCase):
    def test_both_renderers_draw_the_same_nodes_labels_and_edges(self) -> None:
        for name, state in parity_states().items():
            with self.subTest(name):
                mermaid_labels, mermaid_edges, _ = mermaid_graph(to_mermaid(state))
                svg_labels, svg_edges, _ = svg_graph(offline_graph_svg(state))
                self.assertEqual(mermaid_labels, svg_labels)
                self.assertEqual(mermaid_edges, svg_edges)

    def test_both_renderers_colour_each_node_alike(self) -> None:
        for name, state in parity_states().items():
            with self.subTest(name):
                _, _, mermaid_colors = mermaid_graph(to_mermaid(state))
                _, _, svg_colors = svg_graph(offline_graph_svg(state))
                self.assertEqual(mermaid_colors, svg_colors)


if __name__ == "__main__":
    unittest.main()
