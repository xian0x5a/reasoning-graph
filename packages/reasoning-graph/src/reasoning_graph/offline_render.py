"""Offline SVG rendering fallback for reasoning graph HTML reports."""

from __future__ import annotations

import html
from typing import Any

from .costs import node_score_label


def _clip_text(text: str, limit: int = 72) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def _mermaid_id(raw: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in raw)
    if not cleaned:
        cleaned = "N"
    if cleaned[0].isdigit():
        cleaned = "N_" + cleaned
    return cleaned


def _html_anchor(raw: str, prefix: str = "details") -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(raw))
    cleaned = cleaned.strip("-") or "node"
    return f"{prefix}-{cleaned}"


def _compact_node_label(node: dict[str, Any]) -> str:
    node_id = str(node.get("id") or "node")
    node_type = str(node.get("type", "node"))
    type_label = "candidate" if node_type == "candidate_solution" else node_type
    parts = (node_id, type_label, node_score_label(node))
    return "\n".join(part for part in parts if part)


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
        "evidence": 0,
        "constraint": 0,
        "assumption": 1,
        "test": 2,
        "derived": 2,
        "candidate_solution": 3,
        "goal": 4,
    }.get(node_type, 2)


def _node_colors(node: dict[str, Any]) -> tuple[str, str]:
    node_type = str(node.get("type") or "")
    return {
        "goal": ("#fef3c7", "#d97706"),
        "evidence": ("#dcfce7", "#16a34a"),
        "constraint": ("#fef2f2", "#dc2626"),
        "assumption": ("#ede9fe", "#7c3aed"),
        "test": ("#e0f2fe", "#0284c7"),
        "derived": ("#f1f5f9", "#64748b"),
        "candidate_solution": ("#dbeafe", "#2563eb"),
    }.get(node_type, ("#f8fafc", "#94a3b8"))


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
    include_nodes: set[str] | None = None,
    spacing: str = "default",
    graph_id: str = "graph",
) -> str:
    """Render a deterministic inline SVG fallback without network or browser-side layout."""
    metrics = _spacing_metrics(spacing)
    node_width = metrics["node_width"]
    node_height = metrics["node_height"]
    rank_gap = metrics["rank_gap"]
    row_gap = metrics["row_gap"]
    margin_x = 70
    margin_y = 70
    selected_nodes: list[dict[str, Any]] = []
    ranks: dict[int, list[dict[str, Any]]] = {}
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_id = str(node.get("id"))
        if include_nodes is not None and raw_id not in include_nodes:
            continue
        rank = _node_rank(node)
        ranks.setdefault(rank, []).append(node)
        selected_nodes.append(node)

    if not selected_nodes:
        return '<svg class="offline-graph" viewBox="0 0 640 240" role="img" aria-label="Empty graph"><text x="40" y="120">No graph nodes selected.</text></svg>'

    sorted_ranks = sorted(ranks)
    rank_x = {rank: margin_x + index * rank_gap for index, rank in enumerate(sorted_ranks)}
    positions: dict[str, tuple[int, int]] = {}
    max_rows = 1
    for rank in sorted_ranks:
        rank_nodes = ranks[rank]
        max_rows = max(max_rows, len(rank_nodes))
        for row, node in enumerate(rank_nodes):
            positions[str(node.get("id"))] = (rank_x[rank], margin_y + row * row_gap)

    width = max(720, margin_x * 2 + (len(sorted_ranks) - 1) * rank_gap + node_width)
    height = max(360, margin_y * 2 + (max_rows - 1) * row_gap + node_height)
    node_ids = set(positions)
    marker_id = html.escape(_html_anchor(graph_id, "arrowhead"), quote=True)

    edge_parts: list[str] = []
    label_parts: list[str] = []
    for index, edge in enumerate(state.get("edges", [])):
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("from"))
        dst = str(edge.get("to"))
        if src not in node_ids or dst not in node_ids:
            continue
        sx, sy = positions[src]
        dx, dy = positions[dst]
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
        label = str(edge.get("type") or edge.get("label") or "leads_to")
        mid_x = (start_x + end_x) // 2
        mid_y = (start_y + end_y) // 2 - 8
        source_key = _mermaid_id(src)
        target_key = _mermaid_id(dst)
        edge_parts.append(
            f'<path id="edge-{index}" class="flowchart-link LS-{html.escape(source_key)} LE-{html.escape(target_key)}" '
            f'd="M {start_x} {start_y} C {c1x} {start_y}, {c2x} {end_y}, {end_x} {end_y}" '
            f'fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#{marker_id})"/>'
        )
        label_parts.append(
            f'<text class="edgeLabel" x="{mid_x}" y="{mid_y}" text-anchor="middle">'
            f'<tspan>{html.escape(_clip_text(label, 24))}</tspan></text>'
        )

    node_parts: list[str] = []
    for node in selected_nodes:
        raw_id = str(node.get("id"))
        x, y = positions[raw_id]
        fill, stroke = _node_colors(node)
        mid = html.escape(_mermaid_id(raw_id), quote=True)
        anchor = html.escape(f"#{_html_anchor(raw_id)}", quote=True)
        label = _label_tspans(_compact_node_label(node), x + node_width // 2, y + node_height // 2 - 4)
        node_parts.append(
            f'<a href="{anchor}"><g id="{mid}" class="node" data-node-id="{html.escape(raw_id, quote=True)}">'
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
            f'<text x="{x + node_width // 2}" y="{y + node_height // 2}" text-anchor="middle" dominant-baseline="middle" font-size="13">{label}</text>'
            '</g></a>'
        )

    return f'''<svg class="offline-graph" viewBox="0 0 {width} {height}" role="img" aria-label="Reasoning graph" xmlns="http://www.w3.org/2000/svg">
  <defs><marker id="{marker_id}" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M 0 0 L 10 4 L 0 8 z" fill="#64748b"/></marker></defs>
  <g class="edges">{''.join(edge_parts)}</g>
  <g class="edgeLabels">{''.join(label_parts)}</g>
  <g class="nodes">{''.join(node_parts)}</g>
</svg>'''
