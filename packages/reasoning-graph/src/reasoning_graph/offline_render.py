"""Offline SVG rendering fallback for reasoning graph HTML reports."""

from __future__ import annotations

import html
from typing import Any

from .graph_view import ViewEdge, graph_view
from .identities import RenderIdentityMap, html_anchor


def _spacing_metrics(spacing: str) -> dict[str, int]:
    presets = {
        "default": {"rank_gap": 260, "row_gap": 120, "node_width": 190, "node_height": 62},
        "relaxed": {"rank_gap": 300, "row_gap": 145, "node_width": 210, "node_height": 70},
        "wide": {"rank_gap": 350, "row_gap": 165, "node_width": 230, "node_height": 74},
        "compact": {"rank_gap": 220, "row_gap": 96, "node_width": 170, "node_height": 58},
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
    for index, line in enumerate(lines[:3]):
        weight = "600" if index == 0 else "400"
        line_y = start_y if index == 0 else start_y + index * 18
        tspans.append(f'<tspan x="{x}" y="{line_y}" font-weight="{weight}">{html.escape(line)}</tspan>')
    return "".join(tspans)


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
    label_parts: list[str] = []

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
        label_parts.append(
            f'<text class="edgeLabel" x="{mid_x}" y="{mid_y}" text-anchor="middle">'
            f"<tspan>{html.escape(edge.label)}</tspan></text>"
        )

    for edge in sorted(view.edges, key=lambda edge: (edge.source_key[1], edge.target_key[1], edge.label)):
        append_edge(edge)
    for factor in factors:
        for edge in sorted(factor.input_edges, key=lambda edge: (edge.source, edge.source_key[1])):
            append_edge(edge)
        if factor.target_edge is not None:
            append_edge(factor.target_edge)

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
