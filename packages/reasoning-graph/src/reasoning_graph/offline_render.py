"""Offline SVG rendering fallback for reasoning graph HTML reports."""

from __future__ import annotations

import html
from typing import Any

from .graph_view import ViewEdge, graph_view
from .identities import RenderIdentityMap, html_anchor

EDGE_LABEL_FONT_SIZE = 12
# A generous glyph width, as a share of the font size, to reserve room for a label.
EDGE_LABEL_GLYPH_WIDTH = 0.6
EDGE_LABEL_GAP = 2


def _spacing_metrics(spacing: str) -> dict[str, int]:
    presets = {
        # A node holds up to four label lines: id, two of claim, belief.
        "default": {"rank_gap": 290, "row_gap": 130, "node_width": 210, "node_height": 92},
        "relaxed": {"rank_gap": 330, "row_gap": 155, "node_width": 220, "node_height": 96},
        "wide": {"rank_gap": 380, "row_gap": 175, "node_width": 240, "node_height": 100},
        "compact": {"rank_gap": 250, "row_gap": 110, "node_width": 200, "node_height": 88},
    }
    return presets.get(spacing, presets["default"])


def _node_rank(node: dict[str, Any]) -> int:
    node_type = str(node.get("type") or "")
    return {
        "observation": 0,
        "constraint": 0,
        "hypothesis": 1,
        "test": 2,
        "candidate_solution": 3,
        "goal": 4,
    }.get(node_type, 2)


def _label_tspans(label: str, x: int, y: int) -> str:
    lines = [line.strip() for line in str(label).split("\n") if line.strip()] or ["node"]
    start_y = y - (len(lines) - 1) * 9
    tspans = []
    for index, line in enumerate(lines):
        weight = "600" if index == 0 else "400"
        line_y = start_y if index == 0 else start_y + index * 18
        tspans.append(f'<tspan x="{x}" y="{line_y}" font-weight="{weight}">{html.escape(line)}</tspan>')
    return "".join(tspans)


LabelBox = tuple[float, float, float, float]


def _boxes_overlap(a: LabelBox, b: LabelBox) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _spread_labels(labels: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    """Move each edge label down until it clears the labels placed before it.

    Edges that converge on one node, or cross between two columns, put their midpoints
    on one spot, and their labels would print over each other.
    """
    line_height = EDGE_LABEL_FONT_SIZE + EDGE_LABEL_GAP
    placed: list[LabelBox] = []
    spread = []
    for label, x, y in labels:
        half_width = len(label) * EDGE_LABEL_FONT_SIZE * EDGE_LABEL_GLYPH_WIDTH / 2 + EDGE_LABEL_GAP
        box = (x - half_width, y - line_height, x + half_width, y)
        while any(_boxes_overlap(box, other) for other in placed):
            y += line_height
            box = (box[0], box[1] + line_height, box[2], box[3] + line_height)
        placed.append(box)
        spread.append((label, x, y))
    return spread


def offline_graph_svg(
    state: dict[str, Any],
    spacing: str = "default",
    graph_id: str = "graph",
    *,
    identities: RenderIdentityMap | None = None,
) -> str:
    """Render a deterministic inline SVG fallback without network or browser-side layout."""
    view = graph_view(state, identities)
    metrics = _spacing_metrics(spacing)
    node_width = metrics["node_width"]
    node_height = metrics["node_height"]
    rank_gap = metrics["rank_gap"]
    row_gap = metrics["row_gap"]
    margin_x = 70
    margin_y = 70
    if not view.nodes:
        return '<svg class="offline-graph" viewBox="0 0 640 240" role="img" aria-label="Empty graph"><text x="40" y="120">No graph nodes selected.</text></svg>'

    # Layout must not depend on record order. Render identities are stable across
    # equivalent states, so use them first and raw IDs as a deterministic tie-breaker.
    nodes = sorted(view.nodes, key=lambda node: (node.render_id, node.raw_id))
    factors = sorted(view.factors, key=lambda factor: (factor.render_id, factor.raw_id))
    node_ranks = {node.raw_id: _node_rank(node.record) for node in nodes}
    ranks: dict[int, list[tuple[str, str]]] = {}
    for node in nodes:
        ranks.setdefault(node_ranks[node.raw_id], []).append(("node", node.raw_id))
    for factor in factors:
        ranks.setdefault(max(0, node_ranks[factor.factor.target] - 1), []).append(("factor", factor.raw_id))

    sorted_ranks = sorted(ranks)
    rank_x = {rank: margin_x + index * rank_gap for index, rank in enumerate(sorted_ranks)}
    positions: dict[tuple[str, str], tuple[int, int]] = {}
    max_rows = 1
    for rank in sorted_ranks:
        rank_items = ranks[rank]
        max_rows = max(max_rows, len(rank_items))
        for row, key in enumerate(rank_items):
            positions[key] = (rank_x[rank], margin_y + row * row_gap)

    width = max(720, margin_x * 2 + (len(sorted_ranks) - 1) * rank_gap + node_width)
    height = max(360, margin_y * 2 + (max_rows - 1) * row_gap + node_height)
    marker_id = html.escape(html_anchor(graph_id, "arrowhead"), quote=True)

    edge_parts: list[str] = []
    labels: list[tuple[str, int, int]] = []

    def append_edge(edge: ViewEdge) -> None:
        sx, sy = positions[edge.source_key]
        dx, dy = positions[edge.target_key]
        start_x = sx + node_width
        start_y = sy + node_height // 2
        end_x = dx
        end_y = dy + node_height // 2
        if end_x <= start_x:
            start_x = sx + node_width // 2
            start_y = sy + node_height
            end_x = dx + node_width // 2
            end_y = dy
        control_gap = max(40, abs(end_x - start_x) // 2)
        c1x = start_x + control_gap
        c2x = end_x - control_gap
        mid_x = (start_x + end_x) // 2
        mid_y = (start_y + end_y) // 2 - 8
        edge_parts.append(
            f'<path id="edge-{len(edge_parts)}" class="flowchart-link LS-{html.escape(edge.source)} LE-{html.escape(edge.target)}" '
            f'd="M {start_x} {start_y} C {c1x} {start_y}, {c2x} {end_y}, {end_x} {end_y}" '
            f'fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#{marker_id})"/>'
        )
        labels.append((edge.label, mid_x, mid_y))

    for edge in sorted(view.edges, key=lambda edge: (edge.source_key[1], edge.target_key[1], edge.label)):
        append_edge(edge)
    for factor in factors:
        for edge in sorted(factor.input_edges, key=lambda edge: (edge.source, edge.source_key[1])):
            append_edge(edge)
        if factor.target_edge is not None:
            append_edge(factor.target_edge)

    label_parts = [
        f'<text class="edgeLabel" x="{x}" y="{y}" text-anchor="middle" font-size="{EDGE_LABEL_FONT_SIZE}">'
        f"<tspan>{html.escape(label)}</tspan></text>"
        for label, x, y in _spread_labels(labels)
    ]

    node_parts: list[str] = []
    for node in nodes:
        x, y = positions[("node", node.raw_id)]
        fill, stroke = node.colors
        label = _label_tspans(node.label, x + node_width // 2, y + node_height // 2 - 4)
        dash = ' stroke-dasharray="5 4"' if node.render_class == "not_run" else ""
        node_parts.append(
            f'<a href="#{html.escape(node.anchor, quote=True)}"><g id="{html.escape(node.render_id, quote=True)}" class="node" data-node-id="{html.escape(node.raw_id, quote=True)}">'
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"{dash}/>'
            f'<text x="{x + node_width // 2}" y="{y + node_height // 2}" text-anchor="middle" dominant-baseline="middle" font-size="13">{label}</text>'
            "</g></a>"
        )

    for factor in factors:
        x, y = positions[("factor", factor.raw_id)]
        fill, stroke = factor.colors
        label = _label_tspans(factor.label, x + node_width // 2, y + node_height // 2 - 4)
        diamond = f"{x + node_width // 2},{y} {x + node_width},{y + node_height // 2} {x + node_width // 2},{y + node_height} {x},{y + node_height // 2}"
        node_parts.append(
            f'<g id="{html.escape(factor.render_id, quote=True)}" class="node factor" data-factor-id="{html.escape(factor.raw_id, quote=True)}" data-node-type="factor">'
            f'<polygon points="{diamond}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            f'<text x="{x + node_width // 2}" y="{y + node_height // 2}" text-anchor="middle" dominant-baseline="middle" font-size="13">{label}</text>'
            "</g>"
        )

    return f'''<svg class="offline-graph" viewBox="0 0 {width} {height}" role="img" aria-label="Reasoning graph" xmlns="http://www.w3.org/2000/svg">
  <defs><marker id="{marker_id}" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M 0 0 L 10 4 L 0 8 z" fill="#64748b"/></marker></defs>
  <g class="edges">{''.join(edge_parts)}</g>
  <g class="edgeLabels">{''.join(label_parts)}</g>
  <g class="nodes">{''.join(node_parts)}</g>
</svg>'''
