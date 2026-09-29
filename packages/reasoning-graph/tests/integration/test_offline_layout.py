"""The offline SVG keeps its edge labels readable: no two labels share space (#39)."""

import sys
from itertools import combinations
from pathlib import Path
from xml.etree import ElementTree

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.offline_render import offline_graph_svg

SVG = "{http://www.w3.org/2000/svg}"
# A rough glyph width, as a share of the font size, for a sans-serif label.
GLYPH_WIDTH = 0.55


def observation(node_id: str) -> dict:
    return {"id": node_id, "type": "observation", "text": node_id, "source": "s", "quote": "q"}


# Crossed support lands two edge midpoints on one spot: O1->H2 and O2->H1.
CROSSED_STATE = {
    "nodes": [
        observation("O1"),
        observation("O2"),
        observation("O3"),
        {"id": "H1", "type": "hypothesis", "text": "one"},
        {"id": "H2", "type": "hypothesis", "text": "two"},
        {"id": "H3", "type": "hypothesis", "text": "three"},
    ],
    "edges": [
        {"from": source, "to": target, "type": "supports"}
        for source in ("O1", "O2", "O3")
        for target in ("H1", "H2", "H3")
    ],
}


def label_boxes(svg: str) -> list[tuple[float, float, float, float]]:
    boxes = []
    for text in ElementTree.fromstring(svg).iter(f"{SVG}text"):
        if text.get("class") != "edgeLabel":
            continue
        size = float(text.get("font-size"))
        width = len(text.findtext(f"{SVG}tspan")) * size * GLYPH_WIDTH
        x, y = float(text.get("x")), float(text.get("y"))
        # Labels are centred on x and sit on their baseline at y.
        boxes.append((x - width / 2, y - size, x + width / 2, y))
    return boxes


def overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_edge_labels_never_overlap() -> None:
    boxes = label_boxes(offline_graph_svg(CROSSED_STATE))

    assert len(boxes) == 9
    assert [pair for pair in combinations(boxes, 2) if overlap(*pair)] == []
