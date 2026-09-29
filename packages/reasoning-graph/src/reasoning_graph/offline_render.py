"""Offline SVG rendering fallback for reasoning graph HTML reports."""

from __future__ import annotations

import html
from typing import Any

from .costs import node_belief_label, node_effective_truth_costs
from .identities import RenderIdentityMap, render_identity_map
from .models import node_render_class, node_type_label
from .policy import answer_labels
from .visual_factors import VisualFactor, compact_factor_label, select_visual_factors


def _clip_text(text: str, limit: int = 72) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def _html_anchor(raw: str, prefix: str = "details") -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(raw))
    cleaned = cleaned.strip("-") or "node"
    return f"{prefix}-{cleaned}"


def _compact_node_label(node: dict[str, Any], effective_truth_cost: float, answer_label: str = "") -> str:
    node_id = str(node.get("id") or "node")
    # The answer is labelled, not highlighted: the focus control lights a path when the reader asks.
    id_line = f"{node_id} · {answer_label}" if answer_label else node_id
    parts = (id_line, node_type_label(node), node_belief_label(node, effective_truth_cost))
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
        "observation": 0,
        "constraint": 0,
        "hypothesis": 1,
        "test": 2,
        "candidate_solution": 3,
        "goal": 4,
    }.get(node_type, 2)


def _node_colors(node: dict[str, Any]) -> tuple[str, str]:
    if node_render_class(node) == "not_run":
        return ("#f8fafc", "#94a3b8")
    node_type = str(node.get("type") or "")
    return {
        "goal": ("#fef3c7", "#d97706"),
        "observation": ("#dcfce7", "#16a34a"),
        "constraint": ("#fef2f2", "#dc2626"),
        "hypothesis": ("#ede9fe", "#7c3aed"),
        "test": ("#e0f2fe", "#0284c7"),
        "candidate_solution": ("#dbeafe", "#2563eb"),
    }.get(node_type, ("#f8fafc", "#94a3b8"))


def _factor_colors() -> tuple[str, str]:
    return ("#f1f5f9", "#475569")


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
    node_truth_costs = node_effective_truth_costs(state)
    identities = identities or render_identity_map(state)
    metrics = _spacing_metrics(spacing)
    node_width = metrics["node_width"]
    node_height = metrics["node_height"]
    rank_gap = metrics["rank_gap"]
    row_gap = metrics["row_gap"]
    margin_x = 70
    margin_y = 70
    selected_nodes: list[dict[str, Any]] = []
    node_ranks: dict[str, int] = {}
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_id = str(node.get("id"))
        node_ranks[raw_id] = _node_rank(node)
        selected_nodes.append(node)

    # Layout must not depend on record order. Render identities are stable across
    # equivalent states, so use them first and raw IDs as a deterministic tie-breaker.
    selected_nodes.sort(key=lambda node: (identities.node(str(node.get("id"))) or "", str(node.get("id"))))
    ranks: dict[int, list[tuple[tuple[str, str], dict[str, Any]]]] = {}
    for node in selected_nodes:
        raw_id = str(node.get("id"))
        ranks.setdefault(node_ranks[raw_id], []).append((("node", raw_id), node))

    factor_selection = select_visual_factors(state, node_ranks)
    factor_member_edges = factor_selection.member_edges
    selected_factors: list[tuple[VisualFactor, str, tuple[str, str]]] = []
    for factor in factor_selection.factors:
        factor_mid = identities.factor(factor.raw_id)
        if factor_mid is None:
            continue
        factor_key = ("factor", factor_mid)
        selected_factors.append((factor, factor_mid, factor_key))

    selected_factors.sort(key=lambda item: (item[1], item[0].raw_id))
    for factor, _, factor_key in selected_factors:
        factor_rank = max(0, node_ranks[factor.target] - 1)
        ranks.setdefault(factor_rank, []).append((factor_key, factor.record))

    if not selected_nodes:
        return '<svg class="offline-graph" viewBox="0 0 640 240" role="img" aria-label="Empty graph"><text x="40" y="120">No graph nodes selected.</text></svg>'

    sorted_ranks = sorted(ranks)
    rank_x = {rank: margin_x + index * rank_gap for index, rank in enumerate(sorted_ranks)}
    positions: dict[tuple[str, str], tuple[int, int]] = {}
    max_rows = 1
    for rank in sorted_ranks:
        rank_items = ranks[rank]
        max_rows = max(max_rows, len(rank_items))
        for row, (key, _) in enumerate(rank_items):
            positions[key] = (rank_x[rank], margin_y + row * row_gap)

    width = max(720, margin_x * 2 + (len(sorted_ranks) - 1) * rank_gap + node_width)
    height = max(360, margin_y * 2 + (max_rows - 1) * row_gap + node_height)
    node_ids = set(positions)
    marker_id = html.escape(_html_anchor(graph_id, "arrowhead"), quote=True)

    edge_parts: list[str] = []
    label_parts: list[str] = []
    rendered_edge_index = 0

    def append_edge(
        position_source: tuple[str, str],
        source_key: str,
        position_target: tuple[str, str],
        target_key: str,
        label: str,
    ) -> None:
        nonlocal rendered_edge_index
        if position_source not in node_ids or position_target not in node_ids:
            return
        sx, sy = positions[position_source]
        dx, dy = positions[position_target]
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
            f'<path id="edge-{rendered_edge_index}" class="flowchart-link LS-{html.escape(source_key)} LE-{html.escape(target_key)}" '
            f'd="M {start_x} {start_y} C {c1x} {start_y}, {c2x} {end_y}, {end_x} {end_y}" '
            f'fill="none" stroke="#64748b" stroke-width="2" marker-end="url(#{marker_id})"/>'
        )
        label_parts.append(
            f'<text class="edgeLabel" x="{mid_x}" y="{mid_y}" text-anchor="middle">'
            f'<tspan>{html.escape(_clip_text(label, 24))}</tspan></text>'
        )
        rendered_edge_index += 1

    edges = [edge for edge in state.get("edges", []) if isinstance(edge, dict)]
    for edge in sorted(
        edges,
        key=lambda edge: (
            str(edge.get("from")),
            str(edge.get("to")),
            str(edge.get("type") or edge.get("label") or "leads_to"),
        ),
    ):
        src = str(edge.get("from"))
        dst = str(edge.get("to"))
        label = str(edge.get("type") or edge.get("label") or "leads_to")
        # Eligible factors replace their raw member edges in both renderers.
        if (src, dst, label) in factor_member_edges:
            continue
        source_key = identities.node(src)
        target_key = identities.node(dst)
        if source_key is None or target_key is None:
            continue
        append_edge(("node", src), source_key, ("node", dst), target_key, label)

    for factor, factor_mid, factor_key in selected_factors:
        input_ids = sorted(
            factor.inputs,
            key=lambda input_id: (identities.node(input_id) or "", input_id),
        )
        for input_id in input_ids:
            input_key = identities.node(input_id)
            if input_key is not None:
                append_edge(("node", input_id), input_key, factor_key, factor_mid, f"grouped {factor.relation}")
        target_key = identities.node(factor.target)
        if target_key is not None:
            append_edge(
                factor_key,
                factor_mid,
                ("node", factor.target),
                target_key,
                f"{factor.relation} factor",
            )

    labels = answer_labels(state)
    node_parts: list[str] = []
    for node in selected_nodes:
        raw_id = str(node.get("id"))
        x, y = positions[("node", raw_id)]
        fill, stroke = _node_colors(node)
        mid = html.escape(identities.node(raw_id) or "", quote=True)
        anchor = html.escape(f"#{identities.node_anchor(raw_id)}", quote=True)
        label = _label_tspans(
            _compact_node_label(node, node_truth_costs[raw_id], labels.get(raw_id, "")),
            x + node_width // 2,
            y + node_height // 2 - 4,
        )
        node_parts.append(
            f'<a href="{anchor}"><g id="{mid}" class="node" data-node-id="{html.escape(raw_id, quote=True)}">'
            f'<rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"{' stroke-dasharray="5 4"' if node_render_class(node) == "not_run" else ""}/>'
            f'<text x="{x + node_width // 2}" y="{y + node_height // 2}" text-anchor="middle" dominant-baseline="middle" font-size="13">{label}</text>'
            '</g></a>'
        )

    factor_fill, factor_stroke = _factor_colors()
    for factor, factor_mid, factor_key in selected_factors:
        x, y = positions[factor_key]
        escaped_mid = html.escape(factor_mid, quote=True)
        escaped_factor_id = html.escape(factor.raw_id, quote=True)
        label = _label_tspans(compact_factor_label(factor), x + node_width // 2, y + node_height // 2 - 4)
        diamond = f"{x + node_width // 2},{y} {x + node_width},{y + node_height // 2} {x + node_width // 2},{y + node_height} {x},{y + node_height // 2}"
        node_parts.append(
            f'<g id="{escaped_mid}" class="node factor" data-factor-id="{escaped_factor_id}" data-node-type="factor">'
            f'<polygon points="{diamond}" fill="{factor_fill}" stroke="{factor_stroke}" stroke-width="2"/>'
            f'<text x="{x + node_width // 2}" y="{y + node_height // 2}" text-anchor="middle" dominant-baseline="middle" font-size="13">{label}</text>'
            '</g>'
        )

    return f'''<svg class="offline-graph" viewBox="0 0 {width} {height}" role="img" aria-label="Reasoning graph" xmlns="http://www.w3.org/2000/svg">
  <defs><marker id="{marker_id}" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M 0 0 L 10 4 L 0 8 z" fill="#64748b"/></marker></defs>
  <g class="edges">{''.join(edge_parts)}</g>
  <g class="edgeLabels">{''.join(label_parts)}</g>
  <g class="nodes">{''.join(node_parts)}</g>
</svg>'''
