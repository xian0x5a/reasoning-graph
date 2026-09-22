"""Mermaid and HTML rendering for reasoning graph states."""

from __future__ import annotations

import html
import json
import math
from typing import Any

from .costs import (
    compute_costs,
    node_belief_label,
    node_effective_truth_costs,
    node_truth_cost,
    probability_from_cost,
)
from .identities import RenderIdentityMap, render_identity_map
from .models import BELIEF_NODE_TYPES, CLASS_BY_NODE_TYPE
from .offline_render import offline_graph_svg
from .policy import accepted_goal_ids, candidate_goal_targets, preferred_goal_ids, sorted_report_candidates
from .state import by_id
from .utils import finite_float
from .visual_factors import VisualFactor, compact_factor_label, select_visual_factors


def escape_mermaid_label(text: str) -> str:
    # Mermaid node labels are HTML-ish; keep labels compact and safe.
    escaped = html.escape(text, quote=True)
    return escaped.replace("\n", "<br/>")


def clip_text(text: str, limit: int = 72) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"



def html_anchor(raw: str, prefix: str = "details") -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(raw))
    cleaned = cleaned.strip("-") or "node"
    return f"{prefix}-{cleaned}"


def compact_node_label(node: dict[str, Any], effective_truth_cost: float) -> str:
    # Keep graph labels stable and tiny. Full text lives in modal/detail cards;
    # long Mermaid labels are hard to navigate and can expose HTML entity noise.
    node_id = str(node.get("id") or "node")
    node_type = str(node.get("type", "node"))
    type_label = "candidate" if node_type == "candidate_solution" else node_type
    parts = (node_id, type_label, node_belief_label(node, effective_truth_cost))
    return "\n".join(part for part in parts if part)


def class_assignments(state: dict[str, Any]) -> dict[str, set[str]]:
    classes: dict[str, set[str]] = {}
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_type = str(node.get("type"))
        cls = CLASS_BY_NODE_TYPE.get(raw_type, "derived")
        node_id = str(node.get("id"))
        classes.setdefault(cls, set()).add(node_id)
    view = state.get("view", {}) if isinstance(state.get("view"), dict) else {}
    presentation = state.get("presentation", {}) if isinstance(state.get("presentation"), dict) else {}
    for cls_name, key in (("winning", "winning_path"), ("dim", "dimmed_branches"), ("frontier", "frontier")):
        for node_id in view.get(key, []) if isinstance(view.get(key, []), list) else []:
            classes.setdefault(cls_name, set()).add(str(node_id))
    for node_id in presentation.get("highlight_nodes", []) if isinstance(presentation.get("highlight_nodes", []), list) else []:
        classes.setdefault("winning", set()).add(str(node_id))
    for node_id in presentation.get("dim_nodes", []) if isinstance(presentation.get("dim_nodes", []), list) else []:
        classes.setdefault("dim", set()).add(str(node_id))
    return classes


def presentation_node_ids(state: dict[str, Any]) -> set[str]:
    nodes = by_id(state.get("nodes", []), "node")
    presentation = state.get("presentation", {}) if isinstance(state.get("presentation"), dict) else {}
    explicit = presentation.get("include_nodes")
    if isinstance(explicit, list) and explicit:
        return {str(node_id) for node_id in explicit if str(node_id) in nodes}

    view = state.get("view", {}) if isinstance(state.get("view"), dict) else {}
    winning = view.get("winning_path")
    if isinstance(winning, list) and winning:
        ids = {str(node_id) for node_id in winning if str(node_id) in nodes}
        for edge in state.get("edges", []):
            if not isinstance(edge, dict):
                continue
            if str(edge.get("from")) in ids or str(edge.get("to")) in ids:
                ids.add(str(edge.get("from")))
                ids.add(str(edge.get("to")))
        if ids:
            return ids

    candidate_ids = {
        str(node.get("id"))
        for node in state.get("nodes", [])
        if isinstance(node, dict) and node.get("type") in {"candidate_solution", "goal"}
    }
    evidence_ids = [
        str(node.get("id"))
        for node in state.get("nodes", [])
        if isinstance(node, dict) and node.get("type") in {"evidence", "constraint", "derived"}
    ][:10]
    return {node_id for node_id in set(evidence_ids) | candidate_ids if node_id in nodes}


GRAPH_GROUPS = (
    ("cluster_goal", "Goal", {"goal"}),
    ("cluster_evidence", "Evidence", {"evidence", "constraint"}),
    ("cluster_assumptions", "Assumptions", {"assumption"}),
    ("cluster_inference", "Inference", {"derived", "test"}),
    ("cluster_candidates", "Candidates", {"candidate_solution"}),
)


def mermaid_node_definition(mid: str, node: dict[str, Any], effective_truth_cost: float) -> str:
    label = escape_mermaid_label(compact_node_label(node, effective_truth_cost))
    return f'{mid}["{label}"]'


def mermaid_factor_definition(mid: str, factor: dict[str, Any]) -> str:
    label = escape_mermaid_label(compact_factor_label(factor))
    return f'{mid}{{{{"{label}"}}}}'


def grouped_nodes(nodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {group_id: [] for group_id, _, _ in GRAPH_GROUPS}
    groups["cluster_other"] = []
    for node in nodes:
        node_type = str(node.get("type", ""))
        for group_id, _, types in GRAPH_GROUPS:
            if node_type in types:
                groups[group_id].append(node)
                break
        else:
            groups["cluster_other"].append(node)
    return groups


def to_mermaid(
    state: dict[str, Any],
    include_nodes: set[str] | None = None,
    *,
    group_by_type: bool = False,
    direction: str = "TD",
    identities: RenderIdentityMap | None = None,
) -> str:
    # Presentation filtering hides premises, not their contribution to belief.
    node_truth_costs = node_effective_truth_costs(state)
    safe_direction = direction if direction in {"TD", "TB", "BT", "LR", "RL"} else "TD"
    lines = [f"flowchart {safe_direction}"]
    identities = identities or render_identity_map(state)
    node_id_map: dict[str, str] = {}
    factor_id_map: dict[str, str] = {}
    allowed = include_nodes
    selected_nodes: list[dict[str, Any]] = []
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_id = str(node.get("id"))
        if allowed is not None and raw_id not in allowed:
            continue
        mid = identities.node(raw_id)
        if mid is None:
            continue
        node_id_map[raw_id] = mid
        selected_nodes.append(node)

    factor_selection = select_visual_factors(state, node_id_map)
    factor_member_edges = factor_selection.member_edges
    selected_factors: list[tuple[VisualFactor, str]] = []
    for factor in factor_selection.factors:
        factor_mid = identities.factor(factor.raw_id)
        if factor_mid is None:
            continue
        factor_id_map[factor.raw_id] = factor_mid
        selected_factors.append((factor, factor.raw_id))

    if group_by_type:
        groups = grouped_nodes(selected_nodes)
        group_titles = {group_id: title for group_id, title, _ in GRAPH_GROUPS}
        group_titles["cluster_other"] = "Other"
        for group_id, title, _ in (*GRAPH_GROUPS, ("cluster_other", "Other", set())):
            group_nodes = groups.get(group_id, [])
            if not group_nodes:
                continue
            lines.append(f"  subgraph {group_id}[{title}]")
            for node in group_nodes:
                raw_id = str(node.get("id"))
                lines.append(f"    {mermaid_node_definition(node_id_map[raw_id], node, node_truth_costs[raw_id])}")
            lines.append("  end")
    else:
        for node in selected_nodes:
            raw_id = str(node.get("id"))
            lines.append(f"  {mermaid_node_definition(node_id_map[raw_id], node, node_truth_costs[raw_id])}")

    if selected_factors:
        if group_by_type:
            lines.append("  subgraph cluster_factors[Factors]")
            for factor, raw_factor_id in selected_factors:
                lines.append(f"    {mermaid_factor_definition(factor_id_map[raw_factor_id], factor.record)}")
            lines.append("  end")
        else:
            for factor, raw_factor_id in selected_factors:
                lines.append(f"  {mermaid_factor_definition(factor_id_map[raw_factor_id], factor.record)}")

    styled_edge_indexes: list[int] = []
    rendered_edge_index = 0
    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        src_raw = str(edge.get("from"))
        dst_raw = str(edge.get("to"))
        if allowed is not None and (src_raw not in allowed or dst_raw not in allowed):
            continue
        src = node_id_map.get(src_raw)
        dst = node_id_map.get(dst_raw)
        if not src or not dst:
            continue
        edge_type = str(edge.get("type") or edge.get("label") or "leads_to")
        if (src_raw, dst_raw, edge_type) in factor_member_edges:
            continue
        if edge_type in {"contradicts", "prompts", "tested_by", "tests"}:
            lines.append(f"  {src} -. {edge_type} .-> {dst}")
        else:
            lines.append(f"  {src} -- {edge_type} --> {dst}")
        if edge_type in {"prompts", "tested_by", "tests"}:
            styled_edge_indexes.append(rendered_edge_index)
        rendered_edge_index += 1

    for factor, raw_factor_id in selected_factors:
        factor_mid = factor_id_map[raw_factor_id]
        for input_id in factor.inputs:
            input_mid = node_id_map.get(input_id)
            if input_mid:
                lines.append(f"  {input_mid} -. grouped {factor.relation} .-> {factor_mid}")
                rendered_edge_index += 1
        target_mid = node_id_map.get(factor.target)
        if target_mid:
            lines.append(f"  {factor_mid} -- {factor.relation} factor --> {target_mid}")
            rendered_edge_index += 1

    lines.extend(
        [
            "",
            "  classDef goal fill:#fef3c7,stroke:#d97706,stroke-width:2px;",
            "  classDef evidence fill:#ecfeff,stroke:#0891b2;",
            "  classDef constraint fill:#fff7ed,stroke:#ea580c;",
            "  classDef derived fill:#f8fafc,stroke:#64748b;",
            "  classDef assumption fill:#f5f3ff,stroke:#7c3aed;",
            "  classDef test fill:#e0f2fe,stroke:#0284c7;",
            "  classDef candidate fill:#dbeafe,stroke:#2563eb,stroke-width:2px;",
            "  classDef winning fill:#dcfce7,stroke:#16a34a,stroke-width:3px;",
            "  classDef dim fill:#f3f4f6,stroke:#9ca3af,color:#9ca3af;",
            "  classDef bad fill:#fee2e2,stroke:#dc2626,stroke-width:2px;",
            "  classDef frontier fill:#fafafa,stroke:#71717a,stroke-dasharray: 5 5;",
            "  classDef factor fill:#f1f5f9,stroke:#475569,stroke-dasharray: 3 3;",
            "",
        ]
    )

    if group_by_type:
        lines.extend(
            [
                "  style cluster_goal fill:#fffbeb,stroke:#fde68a,stroke-width:1px;",
                "  style cluster_evidence fill:#f8fafc,stroke:#bae6fd,stroke-width:1px;",
                "  style cluster_assumptions fill:#faf5ff,stroke:#ddd6fe,stroke-width:1px;",
                "  style cluster_inference fill:#f8fafc,stroke:#cbd5e1,stroke-width:1px;",
                "  style cluster_candidates fill:#eff6ff,stroke:#bfdbfe,stroke-width:1px;",
                "  style cluster_factors fill:#f8fafc,stroke:#cbd5e1,stroke-dasharray:3 3;",
                "  style cluster_other fill:#fafafa,stroke:#e5e7eb,stroke-width:1px;",
                "",
            ]
        )

    for edge_index in styled_edge_indexes:
        lines.append(f"  linkStyle {edge_index} stroke:#d97706,stroke-dasharray:5 5;")

    factor_mids = [factor_id_map[raw_factor_id] for _, raw_factor_id in selected_factors]
    if factor_mids:
        lines.append(f"  class {','.join(factor_mids)} factor;")

    classes = class_assignments(state)
    for cls, ids in sorted(classes.items()):
        mids = [node_id_map[node_id] for node_id in sorted(ids) if node_id in node_id_map]
        if mids:
            lines.append(f"  class {','.join(mids)} {cls};")

    for raw_id, mid in sorted(node_id_map.items()):
        anchor = identities.node_anchor(raw_id)
        tooltip = escape_mermaid_label(f"Open details for {raw_id}")
        lines.append(f'  click {mid} "#{anchor}" "{tooltip}"')
    return "\n".join(lines) + "\n"


def ledger_rows(state: dict[str, Any], node_type: str) -> str:
    identities = render_identity_map(state)
    rows: list[str] = []
    for node in state.get("nodes", []):
        if not isinstance(node, dict) or node.get("type") != node_type:
            continue
        raw_id = str(node.get("id", ""))
        node_id = html.escape(raw_id)
        text = html.escape(str(node.get("text", "")))
        source = node.get("source") or node.get("sources") or ""
        if isinstance(source, list):
            source_text = ", ".join(str(item) for item in source)
        else:
            source_text = str(source)
        source_html = html.escape(source_text)
        rows.append(
            f'<tr id="{identities.node_anchor(raw_id, "ledger")}"><th scope="row">{node_id}</th><td>{text}</td><td>{source_html}</td></tr>'
        )
    if not rows:
        return "<p class=\"empty\">None recorded.</p>"
    return (
        "<table>"
        "<thead><tr><th>ID</th><th>Statement</th><th>Source</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def html_list(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return '<p class="empty">None recorded.</p>'
    lis = "".join(f"<li>{html.escape(str(item))}</li>" for item in items)
    return f"<ul>{lis}</ul>"


def candidate_rows(state: dict[str, Any]) -> str:
    sorted_candidates = sorted_report_candidates(state)
    if not sorted_candidates:
        return '<p class="empty">No viable answer candidates recorded.</p>'
    nodes = by_id(state.get("nodes", []), "node")
    targets_by_candidate = candidate_goal_targets(state)
    accepted = accepted_goal_ids(state)
    preferred = preferred_goal_ids(state)
    rows: list[str] = []
    for index, candidate in enumerate(sorted_candidates, 1):
        raw_cid = str(candidate.get("id", index))
        node = nodes.get(raw_cid, {})
        cid = html.escape(raw_cid)
        name = html.escape(str(candidate.get("name") or candidate.get("candidate") or "Candidate"))
        target_parts: list[str] = []
        for goal_id in sorted(targets_by_candidate.get(raw_cid, set())):
            labels = []
            if goal_id in accepted:
                labels.append("accepted")
            if goal_id in preferred:
                labels.append("preferred")
            suffix = f" ({', '.join(labels)})" if labels else ""
            target_parts.append(f"<code>{html.escape(goal_id)}</code>{html.escape(suffix)}")
        targets_html = ", ".join(target_parts)
        search_value = candidate.get("search_cost", "n/a")
        search_html = html.escape(str(search_value))
        truth_value = candidate.get("effective_truth_cost", candidate.get("truth_cost", "n/a"))
        penalty = candidate.get("contradiction_penalty")
        belief_value = candidate.get("belief", "n/a")
        posterior_value = candidate.get("posterior")
        belief_html = html.escape(str(belief_value))
        if posterior_value is not None:
            belief_html = f"{belief_html} <small>(explicit posterior {html.escape(str(posterior_value))})</small>"
        if penalty is not None:
            belief_html = f"{belief_html} <small>(truth cost {html.escape(str(truth_value))}; +{html.escape(str(penalty))} contradicting evidence)</small>"
        weight = candidate.get("weight", candidate.get("relative_weight", candidate.get("relative_weight_among_explored", "n/a")))
        weight_html = html.escape(str(weight))
        why = html.escape(str(candidate.get("why", "")))
        next_test = html.escape(str(candidate.get("next_test", "")))
        rows.append(
            "<tr>"
            f"<th scope=\"row\">#{index}</th>"
            f"<td><code>{cid}</code></td><td>{name}</td><td>{targets_html}</td><td>{search_html}</td>"
            f"<td>{belief_html}</td><td>{weight_html}</td><td>{why}</td><td>{next_test}</td>"
            "</tr>"
        )
    return (
        "<table>"
        "<thead><tr><th>Rank</th><th>ID</th><th>Candidate</th><th>Goal(s)</th><th>Search</th><th>Belief</th><th>Weight</th><th>Why</th><th>Next test</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def node_detail_cards(state: dict[str, Any], identities: RenderIdentityMap | None = None) -> str:
    node_truth_costs = node_effective_truth_costs(state)
    identities = identities or render_identity_map(state)
    cards: list[str] = []
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_id = str(node.get("id", ""))
        raw_type = str(node.get("type", "node"))
        node_type = html.escape(raw_type)
        pill_text = raw_type
        text = html.escape(str(node.get("text") or node.get("short_text") or ""))
        source = node.get("source") or node.get("sources") or ""
        source_text = ", ".join(str(item) for item in source) if isinstance(source, list) else str(source)
        extras: list[str] = []
        if raw_type in BELIEF_NODE_TYPES:
            belief = round(probability_from_cost(node_truth_costs[raw_id]), 6)
            extras.append(f"<span>Effective belief: {belief}</span>")
            for key, label in (("prior", "Local prior"), ("posterior", "Posterior override")):
                if key in node:
                    extras.append(f"<span>{label}: {html.escape(str(node[key]))}</span>")
        edge_reasons = []
        for edge in state.get("edges", []):
            if isinstance(edge, dict) and raw_id in (edge.get("from"), edge.get("to")):
                relationship = f"{edge.get('from')} → {edge.get('to')} ({edge.get('type')})"
                edge_reasons.append(
                    f"<li><strong>{html.escape(relationship)}</strong>: "
                    f"{html.escape(str(edge.get('reasoning', '')))}</li>"
                )
        reasoning_html = ('<div class="edge-block"><ul>' + "".join(edge_reasons) + "</ul></div>") if edge_reasons else ""
        type_class = html.escape(raw_type)
        cards.append(
            f'<article class="detail-card {type_class}" data-node-type="{type_class}" id="{identities.node_anchor(raw_id)}">'
            f'<header><code>{html.escape(raw_id)}</code><span class="pill">{html.escape(pill_text)}</span></header>'
            f'<p>{text}</p>'
            f'{"<p class=\"source\">Source: " + html.escape(source_text) + "</p>" if source_text else ""}'
            f'{"<p class=\"extras\">" + " ".join(extras) + "</p>" if extras else ""}'
            f'{reasoning_html}'
            '</article>'
        )
    return "".join(cards) or '<p class="empty">No node details recorded.</p>'


def candidate_focus_options(state: dict[str, Any], identities: RenderIdentityMap | None = None) -> str:
    identities = identities or render_identity_map(state)
    options = ['<option value="">None</option>']
    for index, candidate in enumerate(sorted_report_candidates(state), 1):
        raw_cid = str(candidate.get("id", index))
        key = html.escape(identities.node(raw_cid) or "", quote=True)
        text = html.escape(raw_cid)
        options.append(f'<option value="{key}">{text}</option>')
    return "".join(options)



def mermaid_flowchart_config(spacing: str) -> str:
    base = 'htmlLabels: true, useMaxWidth: false'
    presets = {
        "default": base,
        "relaxed": base + ', nodeSpacing: 70, rankSpacing: 90, curve: "basis"',
        "wide": base + ', nodeSpacing: 100, rankSpacing: 130, curve: "basis"',
        "compact": base + ', nodeSpacing: 35, rankSpacing: 45, curve: "linear"',
    }
    return presets.get(spacing, base)

def graph_panel(
    title: str,
    mermaid_source: str,
    graph_id: str,
    canvas_kind: str = "audit",
    focus_options: str = "",
    svg_graph: str | None = None,
) -> str:
    mermaid_escaped = html.escape(mermaid_source)
    section_id = html_anchor(graph_id, "section")
    kind_class = "graph-canvas-presentation" if canvas_kind == "presentation" else "graph-canvas-audit"
    focus_control = ""
    if focus_options:
        focus_control = (
            '<div class="focus-control">'
            '<span>Focus:</span>'
            f'<select data-candidate-focus-select aria-label="Focus candidate">{focus_options}</select>'
            '</div>'
        )
    graph_markup = svg_graph if svg_graph is not None else f'<pre class="mermaid">{mermaid_escaped}</pre>'
    source_details = ""
    if svg_graph is not None:
        source_details = f'<details class="graph-source"><summary>Mermaid source</summary><pre>{mermaid_escaped}</pre></details>'
    return f"""
<section id="{section_id}" class="graph-section">
  <div class="section-head">
    <h2>{html.escape(title)}</h2>
    <div class="graph-controls">
      <button type="button" data-canvas-mode="{graph_id}" aria-pressed="false">Canvas mode</button>
      <button type="button" data-reset="{graph_id}">Reset view</button>
      {focus_control}
      <span>Click the canvas to capture the wheel, then Ctrl/⌘+wheel zooms. Ctrl/⌘+drag pans. Canvas mode enables direct drag/zoom.</span>
    </div>
  </div>
  <div id="{graph_id}" class="mermaid-wrap graph-canvas {kind_class}" tabindex="0" role="region" aria-label="{html.escape(title)} canvas">
    {graph_markup}
  </div>
  {source_details}
</section>
"""


def detail_filter_buttons() -> str:
    filters = [
        ("all", "All"),
        ("evidence", "Evidence"),
        ("constraint", "Constraints"),
        ("assumption", "Assumptions"),
        ("derived", "Derived"),
        ("candidate_solution", "Candidates"),
        ("test", "Tests"),
    ]
    buttons = [
        f'<button type="button" data-filter="{html.escape(value)}">{html.escape(label)}</button>'
        for value, label in filters
    ]
    return '<div class="detail-filters" aria-label="Filter node details">' + "".join(buttons) + "</div>"


def graph_edge_connections(
    state: dict[str, Any],
    include_nodes: set[str] | None = None,
    identities: RenderIdentityMap | None = None,
) -> list[dict[str, str]]:
    identities = identities or render_identity_map(state)
    connections: list[dict[str, str]] = []
    allowed = include_nodes
    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("from"))
        dst = str(edge.get("to"))
        if allowed is not None and (src not in allowed or dst not in allowed):
            continue
        source_id = identities.node(src)
        target_id = identities.node(dst)
        if source_id is None or target_id is None:
            continue
        connections.append(
            {
                "from": source_id,
                "to": target_id,
                "label": str(edge.get("type") or edge.get("label") or "leads_to"),
            }
        )
    return connections


def candidate_focus_nodes(
    state: dict[str, Any],
    candidate: dict[str, Any],
    identities: RenderIdentityMap | None = None,
) -> list[str]:
    identities = identities or render_identity_map(state)
    raw_id = str(candidate.get("id") or "")
    node_ids: list[str] = [raw_id] if raw_id else []
    explicit = False
    for key in ("path_nodes", "support_nodes", "supporting_nodes", "nodes"):
        values = candidate.get(key)
        if isinstance(values, list) and values:
            explicit = True
            node_ids.extend(str(value) for value in values)

    nodes_by_id = by_id(state.get("nodes", []), "node")
    supportive_edges = {"supports", "requires", "leads_to"}
    non_expanding_seed_types = {"evidence", "constraint", "test"}
    parents_by_child: dict[str, list[str]] = {}
    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge_type = str(edge.get("type") or edge.get("label") or "")
        if edge_type and edge_type not in supportive_edges:
            continue
        parents_by_child.setdefault(str(edge.get("to")), []).append(str(edge.get("from")))

    if not explicit:
        view = state.get("view", {}) if isinstance(state.get("view"), dict) else {}
        winning_path = [str(value) for value in view.get("winning_path", [])] if isinstance(view.get("winning_path"), list) else []
        if raw_id and raw_id in winning_path:
            node_ids.extend(winning_path)

    # Focus should include entry evidence that feeds highlighted derived/path nodes.
    # Use deterministic upstream depth, not arbitrary node-count caps, so dense graphs behave predictably.
    max_upstream_hops = 2
    frontier = [(node_id, 0) for node_id in node_ids]
    seen_raw = set(node_ids)
    while frontier:
        child, depth = frontier.pop(0)
        if depth >= max_upstream_hops:
            continue
        node_type = str(nodes_by_id.get(child, {}).get("type") or "")
        if node_type in non_expanding_seed_types:
            continue
        for parent in parents_by_child.get(child, []):
            if parent in seen_raw:
                continue
            seen_raw.add(parent)
            node_ids.append(parent)
            frontier.append((parent, depth + 1))
    seen: set[str] = set()
    result: list[str] = []
    for node_id in node_ids:
        if node_id not in nodes_by_id:
            continue
        mid = identities.node(node_id)
        if mid is None:
            continue
        if mid and mid not in seen:
            seen.add(mid)
            result.append(mid)
    return result


def candidate_focus_map(state: dict[str, Any], identities: RenderIdentityMap | None = None) -> dict[str, list[str]]:
    identities = identities or render_identity_map(state)
    focus: dict[str, list[str]] = {}
    for candidate in sorted_report_candidates(state):
        if "id" not in candidate:
            continue
        candidate_id = identities.node(str(candidate["id"]))
        if candidate_id is not None:
            focus[candidate_id] = candidate_focus_nodes(state, candidate, identities)
    return focus


def goal_policy_html(state: dict[str, Any]) -> str:
    groups = state.get("goal_groups") if isinstance(state.get("goal_groups"), list) else []
    policy = state.get("goal_policy") if isinstance(state.get("goal_policy"), dict) else {}
    if not groups and not policy:
        return ""
    accepted = ", ".join(f"<code>{html.escape(goal_id)}</code>" for goal_id in sorted(accepted_goal_ids(state))) or "all goals"
    preferred = ", ".join(f"<code>{html.escape(goal_id)}</code>" for goal_id in sorted(preferred_goal_ids(state))) or "none"
    group_items: list[str] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = html.escape(str(group.get("id", "")))
        goals = group.get("goals") if isinstance(group.get("goals"), list) else []
        goals_html = ", ".join(f"<code>{html.escape(str(goal_id))}</code>" for goal_id in goals)
        exclusivity = "exclusive" if group.get("exclusive") else "non-exclusive"
        group_items.append(f"<li><code>{group_id}</code>: {html.escape(exclusivity)} [{goals_html}]</li>")
    groups_html = f"<ul>{''.join(group_items)}</ul>" if group_items else '<p class="empty">No goal groups recorded.</p>'
    return f"""
  <section>
    <h2>Goal policy</h2>
    <p>Accepted goals: {accepted}. Preferred goals: {preferred}.</p>
    {groups_html}
  </section>"""


def html_document(
    state: dict[str, Any],
    mermaid_source: str,
    spacing: str = "default",
    render_mode: str = "mermaid",
) -> str:
    summary = state.get("summary", {}) if isinstance(state.get("summary"), dict) else {}
    report = state.get("report", {}) if isinstance(state.get("report"), dict) else {}
    title = html.escape(str(summary.get("title") or report.get("title") or "Reasoning Graph"))
    answer = html.escape(str(summary.get("answer") or report.get("answer") or "See report sections."))
    identities = render_identity_map(state)
    offline_mode = render_mode == "offline"
    audit_svg = offline_graph_svg(state, None, spacing, "audit-graph", identities=identities) if offline_mode else None
    candidates_html = candidate_rows(state)
    focus_options = candidate_focus_options(state, identities)
    goal_policy_section = goal_policy_html(state)

    def nonempty_list(value: Any) -> bool:
        return isinstance(value, list) and any(str(item).strip() for item in value)

    insight_cards: list[str] = []
    for heading, key in (
        ("Strongly supported", "strongly_supported"),
        ("Speculative", "speculative"),
        ("Unresolved", "unresolved"),
    ):
        items = report.get(key)
        if nonempty_list(items):
            insight_cards.append(f"<div><h2>{heading}</h2>{html_list(items)}</div>")
    insights_section = f'<section class="two-col">{"".join(insight_cards)}</section>' if insight_cards else ""

    next_verification_value = report.get("best_next_verification") or report.get("next_verification")
    next_verification_section = ""
    if isinstance(next_verification_value, str) and next_verification_value.strip():
        next_verification = html.escape(next_verification_value.strip())
        next_verification_section = f"""
  <section>
    <h2>Best next verification</h2>
    <p>{next_verification}</p>
  </section>"""

    details_html = node_detail_cards(state, identities)
    filters_html = detail_filter_buttons()
    edge_maps_json = json.dumps(
        {
            "audit-graph": graph_edge_connections(state, identities=identities),
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    candidate_focus_json = json.dumps(candidate_focus_map(state, identities), ensure_ascii=False).replace("</", "<\\/")
    script_open = "<script>"
    script_setup = '  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", setupGraphs);\n  else setupGraphs();'
    if not offline_mode:
        script_open = f'''<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  mermaid.initialize({{ startOnLoad: false, securityLevel: "loose", flowchart: {{ {mermaid_flowchart_config(spacing)} }} }});'''
        script_setup = '''  mermaid.run({ querySelector: ".mermaid" }).then(setupGraphs).catch((error) => {
    console.error("Mermaid render failed", error);
    setupGraphs();
  });'''

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{title}</title>
  <style>
    :root {{ color-scheme: light; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0; --panel:#ffffff; --soft:#f8fafc; --brand:#2563eb; }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.5; color: var(--ink); background: #f1f5f9; }}
    main {{ max-width: 1320px; margin: 0 auto; padding: 2rem; }}
    h1, h2, h3 {{ line-height: 1.15; }}
    .hero, section {{ background: var(--panel); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 12px 32px rgba(15, 23, 42, .06); scroll-margin-top: 5rem; }}
    .hero {{ padding: 1.4rem 1.6rem; margin-bottom: 1rem; }}
    .answer {{ padding: 1rem; background: #eff6ff; border-left: 4px solid var(--brand); border-radius: 12px; }}
    section {{ padding: 1.2rem; margin: 1rem 0; }}
    .two-col {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); }}
    table {{ width: 100%; border-collapse: collapse; font-size: .92rem; table-layout: fixed; }}
    th, td {{ padding: .55rem .65rem; border: 1px solid var(--line); vertical-align: top; overflow-wrap: anywhere; word-break: break-word; }}
    th {{ background: var(--soft); text-align: left; }}
    th[scope="row"] {{ width: 5rem; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .empty, .hint, .source {{ color: var(--muted); }}
    a {{ color: #1d4ed8; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 1rem; align-items: center; flex-wrap: wrap; }}
    .graph-controls {{ display: flex; gap: .75rem; align-items: center; color: var(--muted); font-size: .9rem; }}
    button {{ border: 1px solid var(--line); background: var(--soft); color: var(--ink); border-radius: 999px; padding: .4rem .8rem; cursor: pointer; }}
    .focus-control {{ display: inline-flex; align-items: center; gap: .35rem; color: var(--muted); }}
    .focus-control span {{ white-space: nowrap; }}
    .focus-control select {{ max-width: min(9rem, 32vw); color: var(--ink); cursor: pointer; }}
    .mermaid-wrap {{ border: 1px solid var(--line); border-radius: 14px; background: #fff; padding: .75rem; }}
    .graph-canvas {{ overflow: hidden; cursor: default; touch-action: pan-y; position: relative; user-select: none; -webkit-user-select: none; }}
    /* Dotted canvas sheet. The graph svg is transparent, so the dots read as the
       surface the drawing sits on instead of a plain white card. */
    .graph-canvas {{ background-color: #fbfcfe; background-image: radial-gradient(circle, #a9b8cc 1.4px, transparent 1.4px); background-size: 18px 18px; }}
    /* Focus is functional here: the wheel only zooms while the canvas owns focus,
       so the ring tells the user which surface will consume the scroll. The negative
       offset registers the ring with the canvas border instead of ringing around it. */
    .graph-canvas:focus {{ outline: 2px solid #60a5fa; outline-offset: -2px; border-color: #60a5fa; }}
    .graph-canvas.canvas-mode {{ cursor: grab; touch-action: none; }}
    .graph-canvas svg, .graph-canvas svg * {{ user-select: none; -webkit-user-select: none; }}
    .graph-canvas.panning {{ cursor: grabbing; }}
    [data-canvas-mode][aria-pressed="true"] {{ background: #dbeafe; border-color: #93c5fd; color: #1e3a8a; }}
    .graph-canvas-audit {{ height: min(78vh, 860px); min-height: 560px; }}
    .graph-canvas .offline-graph {{ width: 100%; height: 100%; margin: 0; display: block; overflow: visible; }}
    /* Mermaid renders inside its own <pre class="mermaid"> wrapper, so that wrapper
       has to carry the canvas height. Otherwise the svg's height:100% resolves
       against an auto height and the graph collapses to its intrinsic aspect strip,
       leaving the panel half empty and clipping any panned view inside that strip. */
    .graph-canvas .mermaid {{ height: 100%; margin: 0; display: block; }}
    .graph-canvas svg {{ width: 100% !important; height: 100% !important; max-width: none !important; display: block; }}
    .graph-source {{ margin-top: .6rem; color: var(--muted); }}
    .graph-source pre {{ white-space: pre-wrap; overflow: auto; background: var(--soft); border: 1px solid var(--line); border-radius: 12px; padding: .75rem; color: var(--ink); }}
    .graph-canvas a {{ cursor: pointer; }}
    .graph-canvas svg .edgePath, .graph-canvas svg .edge-path, .graph-canvas svg .flowchart-link {{ cursor: crosshair; pointer-events: stroke; outline: none; }}
    .graph-canvas svg .edge-hitbox {{ stroke: transparent !important; stroke-width: 14px !important; fill: none !important; pointer-events: stroke; cursor: crosshair; outline: none; }}
    .graph-canvas svg .edgePath.edge-hover path:not(.edge-hitbox),
    .graph-canvas svg .edge-path.edge-hover path:not(.edge-hitbox),
    .graph-canvas svg path.flowchart-link.edge-hover:not(.edge-hitbox),
    .graph-canvas svg path.edge-hover:not(.edge-hitbox) {{ stroke: #fb923c !important; stroke-width: 4px !important; filter: drop-shadow(0 0 5px rgba(249,115,22,.55)); }}
    .graph-canvas svg .edgePath.edge-pinned path:not(.edge-hitbox),
    .graph-canvas svg .edge-path.edge-pinned path:not(.edge-hitbox),
    .graph-canvas svg path.flowchart-link.edge-pinned:not(.edge-hitbox),
    .graph-canvas svg path.edge-pinned:not(.edge-hitbox) {{ stroke: #ea580c !important; stroke-width: 5px !important; filter: drop-shadow(0 0 7px rgba(234,88,12,.7)); }}
    .graph-canvas svg .node.node-connected rect,
    .graph-canvas svg .node.node-connected circle,
    .graph-canvas svg .node.node-connected ellipse,
    .graph-canvas svg .node.node-connected polygon,
    .graph-canvas svg .node.node-connected path {{ stroke: #f97316 !important; stroke-width: 3px !important; filter: drop-shadow(0 0 3px rgba(249,115,22,.35)); }}
    .graph-canvas svg .edgeLabel.edge-connected {{ color: #9a3412 !important; font-weight: 600; }}
    .graph-canvas.focus-active {{ border-color: #60a5fa; box-shadow: 0 0 0 3px rgba(96,165,250,.25); }}
    .graph-canvas.focus-active svg .node:not(.node-focused) {{ opacity: .36 !important; }}
    .graph-canvas.focus-active svg .edgePath:not(.edge-focused),
    .graph-canvas.focus-active svg .edge-path:not(.edge-focused),
    .graph-canvas.focus-active svg path.flowchart-link:not(.edge-focused):not(.edge-hitbox) {{ opacity: .22 !important; }}
    .graph-canvas.focus-active svg .edgeLabels > .edgeLabel:not(.edge-focused) {{ opacity: .18 !important; }}
    .graph-canvas.focus-active svg .edgeLabels > .edgeLabel.edge-focused {{ opacity: 1 !important; }}
    .graph-canvas svg .node.node-focused,
    .graph-canvas svg .node.node-focused * {{ opacity: 1 !important; }}
    .graph-canvas svg .node.node-focused text,
    .graph-canvas svg .node.node-focused tspan,
    .graph-canvas svg .node.node-focused .nodeLabel,
    .graph-canvas svg .node.node-focused .label,
    .graph-canvas svg .node.node-focused foreignObject,
    .graph-canvas svg .node.node-focused foreignObject * {{ fill: var(--ink) !important; color: var(--ink) !important; opacity: 1 !important; }}
    .graph-canvas svg .node.node-focused rect,
    .graph-canvas svg .node.node-focused circle,
    .graph-canvas svg .node.node-focused ellipse,
    .graph-canvas svg .node.node-focused polygon,
    .graph-canvas svg .node.node-focused path {{ stroke: #2563eb !important; stroke-width: 4px !important; filter: drop-shadow(0 0 6px rgba(37,99,235,.45)); }}
    .graph-canvas svg .edgePath.edge-focused path:not(.edge-hitbox),
    .graph-canvas svg .edge-path.edge-focused path:not(.edge-hitbox),
    .graph-canvas svg path.flowchart-link.edge-focused:not(.edge-hitbox),
    .graph-canvas svg path.edge-focused:not(.edge-hitbox) {{ stroke: #2563eb !important; stroke-width: 4px !important; filter: drop-shadow(0 0 5px rgba(37,99,235,.5)); opacity: 1 !important; }}
    .detail-filters {{ display: flex; gap: .5rem; flex-wrap: wrap; margin: .75rem 0 1rem; }}
    .detail-filters button.active {{ background: #dbeafe; border-color: #93c5fd; color: #1e3a8a; }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(min(260px, 100%), 1fr)); gap: .75rem; }}
    .detail-card {{ min-width: 0; border: 1px solid var(--line); border-radius: 14px; padding: .75rem; background: var(--soft); scroll-margin-top: 5rem; overflow-wrap: anywhere; word-break: break-word; }}
    .detail-card p, .detail-card header, .detail-card .source, .detail-card .extras {{ min-width: 0; overflow-wrap: anywhere; word-break: break-word; }}
    .detail-card[hidden] {{ display: none; }}
    .detail-card:target {{ outline: 3px solid #60a5fa; background: #eff6ff; }}
    .detail-card header {{ display: flex; justify-content: space-between; align-items: center; gap: .5rem; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; overflow-wrap: anywhere; word-break: break-word; }}
    .pill {{ border-radius: 999px; padding: .15rem .5rem; background: #e2e8f0; color: #334155; font-size: .78rem; font-weight: 400; }}
    .extras {{ display: flex; flex-direction: column; gap: .15rem; }}
    .extras span {{ color: var(--muted); }}
    .floating-nav {{ position: fixed; right: 1rem; bottom: 1rem; z-index: 20; font-size: .86rem; }}
    .nav-toggle {{ width: 2.45rem; height: 2.45rem; border-radius: 999px; display: grid; place-items: center; background: rgba(255,255,255,.96); box-shadow: 0 10px 28px rgba(15,23,42,.18); }}
    .floating-nav .nav-menu {{ position: absolute; right: 0; bottom: calc(100% + .45rem); display: none; flex-direction: column; gap: .35rem; min-width: 9rem; padding: .5rem; background: rgba(255,255,255,.96); border: 1px solid var(--line); border-radius: 14px; box-shadow: 0 10px 28px rgba(15,23,42,.16); }}
    .floating-nav.open .nav-menu {{ display: flex; }}
    .floating-nav a {{ text-decoration: none; padding: .35rem .55rem; border-radius: 999px; background: #eff6ff; white-space: nowrap; }}
    .node-modal {{ width: min(720px, calc(100vw - 2rem)); max-height: min(82vh, 760px); border: 0; border-radius: 18px; padding: 0; box-shadow: 0 30px 80px rgba(15,23,42,.35); overflow: hidden; overscroll-behavior: contain; }}
    .node-modal::backdrop {{ background: rgba(15,23,42,.48); backdrop-filter: blur(2px); }}
    .modal-shell {{ padding: 1rem; max-height: calc(min(82vh, 760px) - 64px); overflow: auto; overscroll-behavior: contain; }}
    .modal-bar {{ display: flex; justify-content: flex-start; align-items: center; gap: 1rem; flex-wrap: wrap; border-bottom: 1px solid var(--line); padding: .75rem 1rem; background: var(--soft); }}
    .modal-title {{ display: flex; align-items: center; gap: .55rem; margin: 0; font-size: 1rem; }}
    .modal-title code {{ font-size: .95rem; }}
    .modal-close {{ font-size: 1.2rem; line-height: 1; padding: .35rem .65rem; margin-left: auto; }}
    .node-modal .detail-card {{ border: 1px solid var(--line); background: var(--soft); padding: .85rem; border-radius: 14px; box-shadow: inset 0 1px 0 rgba(255,255,255,.7); }}
    .node-modal .detail-card p:first-child {{ margin-top: 0; }}
    .node-modal .detail-card p:last-child {{ margin-bottom: 0; }}
    .node-modal .detail-card .edge-block ul {{ margin: 0; padding-left: 0; list-style: none; }}
    .node-modal .detail-card .edge-block li {{ margin-bottom: .4rem; }}
    .node-modal .detail-card .edge-block li:last-child {{ margin-bottom: 0; }}
    .detail-grid .edge-block {{ display: none; }}
    .modal-bar .modal-tabs {{ display: flex; gap: .5rem; flex-wrap: wrap; margin: 0; }}
    .modal-tabs button.active {{ background: #dbeafe; border-color: #93c5fd; color: #1e3a8a; }}
    .modal-tabpanel[hidden] {{ display: none; }}
    @media (max-width: 720px) {{ main {{ padding: 1rem; }} .graph-canvas-audit {{ min-height: 460px; }} .floating-nav {{ right: .75rem; bottom: .75rem; }} }}
  </style>
</head>
<body>
<nav class="floating-nav" aria-label="Graph navigation">
  <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="floating-nav-menu" title="Open navigation">☰</button>
  <div id="floating-nav-menu" class="nav-menu">
    <a href="#section-audit-graph">Audit canvas</a>
    <a href="#node-details-section">Details</a>
  </div>
</nav>
<main>
  <header class="hero">
    <h1>{title}</h1>
    <p class="answer"><strong>Answer:</strong> {answer}</p>
  </header>

  {goal_policy_section}

  <section>
    <h2>Candidate ranking</h2>
    {candidates_html}
  </section>

  {insights_section}

  {next_verification_section}

  {graph_panel("Full audit graph", mermaid_source, "audit-graph", "audit", focus_options, audit_svg)}

  <section id="node-details-section">
    <h2>Node details</h2>
    <p class="hint">Includes evidence, constraints, assumptions, and candidate answers. Use filters or click graph nodes for popup cards.</p>
    {filters_html}
    <div class="detail-grid">{details_html}</div>
  </section>
</main>
<dialog id="node-modal" class="node-modal" aria-labelledby="node-modal-title">
  <div class="modal-bar">
    <h2 id="node-modal-title" class="modal-title">Node details</h2>
    <button type="button" class="modal-close" data-close-modal aria-label="Close node details">×</button>
  </div>
  <div id="node-modal-content" class="modal-shell"></div>
</dialog>
{script_open}
  const graphEdgeMaps = {edge_maps_json};
  const candidateFocusMap = {candidate_focus_json};

  function validBox(box) {{
    return box && Number.isFinite(box.x) && Number.isFinite(box.y) && Number.isFinite(box.width) && Number.isFinite(box.height) && box.width > 1 && box.height > 1;
  }}

  function paddedBox(box, pad = 40) {{
    return {{ x: box.x - pad, y: box.y - pad, width: box.width + pad * 2, height: box.height + pad * 2 }};
  }}

  function readViewBox(svg) {{
    const raw = svg.getAttribute("viewBox");
    if (!raw) return null;
    const [x, y, width, height] = raw.trim().split(/\\s+/).map(Number);
    const box = {{ x, y, width, height }};
    return validBox(box) ? box : null;
  }}

  function contentBox(svg) {{
    const boxes = [];
    [svg, ...svg.querySelectorAll("g")].forEach((element) => {{
      try {{
        const box = element.getBBox();
        if (validBox(box)) boxes.push(box);
      }} catch (_) {{}}
    }});
    if (boxes.length) {{
      const largest = boxes.sort((a, b) => (b.width * b.height) - (a.width * a.height))[0];
      return paddedBox(largest);
    }}
    return readViewBox(svg) || {{ x: 0, y: 0, width: 1000, height: 700 }};
  }}

  function hrefFor(anchor) {{
    return anchor.getAttribute("href") || anchor.getAttribute("xlink:href") || anchor.getAttributeNS("http://www.w3.org/1999/xlink", "href") || "";
  }}

  function showNodeModal(detailId) {{
    const modal = document.getElementById("node-modal");
    const content = document.getElementById("node-modal-content");
    const title = document.getElementById("node-modal-title");
    const card = document.getElementById(detailId);
    if (!modal || !content || !card) return;
    const clone = card.cloneNode(true);
    clone.removeAttribute("id");
    const header = clone.querySelector("header");
    const code = header?.querySelector("code")?.textContent?.trim();
    const type = header?.querySelector(".pill")?.textContent?.trim();
    if (header) header.remove();
    const bar = modal.querySelector(".modal-bar");
    const closeButton = modal.querySelector("[data-close-modal]");
    bar?.querySelector(".modal-tabs")?.remove();
    const edgeBlock = clone.querySelector(".edge-block");
    if (edgeBlock) {{
      const edgeCount = edgeBlock.querySelectorAll("li").length;
      edgeBlock.remove();
      const detailsCard = clone;
      detailsCard.setAttribute("role", "tabpanel");
      detailsCard.dataset.panel = "details";
      const edgesCard = document.createElement("article");
      edgesCard.className = detailsCard.className;
      const nodeType = detailsCard.getAttribute("data-node-type");
      if (nodeType) edgesCard.setAttribute("data-node-type", nodeType);
      edgesCard.setAttribute("role", "tabpanel");
      edgesCard.dataset.panel = "edges";
      edgesCard.hidden = true;
      edgesCard.appendChild(edgeBlock);
      const tabs = document.createElement("div");
      tabs.className = "modal-tabs";
      tabs.setAttribute("role", "tablist");
      tabs.setAttribute("aria-label", "Node card views");
      const detailsTab = document.createElement("button");
      detailsTab.type = "button";
      detailsTab.textContent = "Details";
      detailsTab.setAttribute("role", "tab");
      detailsTab.setAttribute("aria-selected", "true");
      detailsTab.classList.add("active");
      const edgesTab = document.createElement("button");
      edgesTab.type = "button";
      edgesTab.textContent = edgeCount > 0 ? "Edges (" + edgeCount + ")" : "Edges";
      edgesTab.setAttribute("role", "tab");
      edgesTab.setAttribute("aria-selected", "false");
      const selectTab = (name) => {{
        const showDetails = name === "details";
        detailsCard.hidden = !showDetails;
        edgesCard.hidden = showDetails;
        detailsTab.classList.toggle("active", showDetails);
        edgesTab.classList.toggle("active", !showDetails);
        detailsTab.setAttribute("aria-selected", String(showDetails));
        edgesTab.setAttribute("aria-selected", String(!showDetails));
      }};
      detailsTab.addEventListener("click", () => selectTab("details"));
      edgesTab.addEventListener("click", () => selectTab("edges"));
      tabs.replaceChildren(detailsTab, edgesTab);
      if (bar) {{
        if (closeButton) bar.insertBefore(tabs, closeButton);
        else bar.appendChild(tabs);
      }}
      content.replaceChildren(detailsCard, edgesCard);
    }} else {{
      content.replaceChildren(clone);
    }}
    title.replaceChildren();
    if (code) {{
      const codeEl = document.createElement("code");
      codeEl.textContent = code;
      title.appendChild(codeEl);
    }}
    if (type) {{
      const typeEl = document.createElement("span");
      typeEl.className = "pill";
      typeEl.textContent = type;
      title.appendChild(typeEl);
    }}
    if (!code && !type) title.textContent = "Node details";
    if (typeof modal.showModal === "function") modal.showModal();
    else modal.setAttribute("open", "");
  }}

  function installDetailClicks(section) {{
    section.querySelectorAll("a").forEach((anchor) => {{
      const href = hrefFor(anchor);
      if (!href.startsWith("#details-")) return;
      anchor.addEventListener("click", (event) => {{
        event.preventDefault();
        showNodeModal(href.slice(1));
      }});
    }});
  }}

  function normalizeMermaidKey(value) {{
    return String(value || "").replace(/^flowchart-/, "").replace(/-\\d+$/, "");
  }}

  function connectedNodeKeys(edge, fallback) {{
    const classes = Array.from(edge.classList || []);
    const source = classes.find((item) => item.startsWith("LS-"))?.slice(3);
    const target = classes.find((item) => item.startsWith("LE-"))?.slice(3);
    if (source && target) return [normalizeMermaidKey(source), normalizeMermaidKey(target)];
    const id = edge.getAttribute("id") || "";
    const match = id.match(/^L[-_](.+)[-_]([^_-]+)[-_]\\d+$/);
    if (match) return [normalizeMermaidKey(match[1]), normalizeMermaidKey(match[2])];
    return fallback ? [normalizeMermaidKey(fallback.from), normalizeMermaidKey(fallback.to)] : [];
  }}

  function edgeContainerFor(target) {{
    if (!target || !target.closest) return null;
    return target.closest("path.flowchart-link, path.edge-hitbox, path[class*='LS-'][class*='LE-'], path[id^='L-'], g.edgePath, .edgePath, g.edge-path, .edge-path");
  }}

  function uniqueElements(items) {{
    return Array.from(new Set(items.filter(Boolean)));
  }}

  function edgeElements(svg) {{
    return uniqueElements(
      Array.from(svg.querySelectorAll("path.flowchart-link, path[class*='LS-'][class*='LE-'], path[id^='L-'], g.edgePath, .edgePath, g.edge-path, .edge-path"))
        .filter((item) => !item.classList.contains("edge-hitbox"))
        .map((item) => item.matches?.("path") ? item : (item.closest?.("g") || item))
    );
  }}

  function edgeLabels(svg) {{
    const labelGroups = Array.from(svg.querySelectorAll(".edgeLabels"));
    return labelGroups.flatMap((group) =>
      Array.from(group.children).filter((child) => child.classList?.contains("edgeLabel"))
    );
  }}

  function nodeElementFor(element) {{
    if (!element) return null;
    return element.querySelector?.("g.node") || element.closest?.("g.node") || element.closest?.("g") || element;
  }}

  function addEdgeHitbox(edge) {{
    const path = edge.matches?.("path") ? edge : edge.querySelector("path:not(.edge-hitbox)");
    if (!path) return null;
    const existing = edge.matches?.("path")
      ? path.parentNode?.querySelector(`.edge-hitbox[data-edge-for="${{path.id}}"]`)
      : edge.querySelector(".edge-hitbox");
    if (existing) return existing;
    const hitbox = path.cloneNode(false);
    hitbox.removeAttribute("marker-end");
    hitbox.removeAttribute("marker-start");
    hitbox.classList.add("edge-hitbox");
    if (path.id) hitbox.dataset.edgeFor = path.id;
    path.parentNode.insertBefore(hitbox, path);
    return hitbox;
  }}

  function graphNodes(svg) {{
    const nodes = new Map();
    const remember = (key, node) => {{
      const normalized = normalizeMermaidKey(key);
      if (normalized && node && !nodes.has(normalized)) nodes.set(normalized, node);
    }};
    svg.querySelectorAll("a").forEach((anchor) => {{
      const href = hrefFor(anchor);
      if (!href.startsWith("#details-")) return;
      const key = href.replace(/^#details-/, "");
      remember(key, nodeElementFor(anchor));
    }});
    svg.querySelectorAll("g.node").forEach((node) => {{
      if (node.id) remember(node.id, node);
      const firstLine = (node.textContent || "").trim().split(/\\s+/)[0];
      remember(firstLine, node);
    }});
    svg.querySelectorAll("g[id]").forEach((node) => remember(node.id, node));
    return nodes;
  }}

  function setupEdgeHighlights(section) {{
    const svg = section.querySelector("svg");
    const canvas = section.querySelector(".graph-canvas");
    if (!svg || !canvas) return;
    const edgeMap = graphEdgeMaps[canvas.id] || [];
    const nodes = graphNodes(svg);
    const edges = edgeElements(svg);
    let hoveredEdge = null;
    let pinnedEdge = null;

    const clearClasses = () => {{
      edges.forEach((edge) => edge.classList.remove("edge-hover", "edge-pinned"));
      nodes.forEach((node) => node.classList.remove("node-connected"));
    }};
    const render = () => {{
      clearClasses();
      const activeEdges = new Set([hoveredEdge, pinnedEdge].filter(Boolean));
      activeEdges.forEach((edge) => {{
        edge.classList.toggle("edge-hover", edge === hoveredEdge && edge !== pinnedEdge);
        edge.classList.toggle("edge-pinned", edge === pinnedEdge);
        const fallback = edgeMap[edges.indexOf(edge)];
        connectedNodeKeys(edge, fallback).forEach((key) => {{
          const node = nodes.get(key);
          if (node) node.classList.add("node-connected");
        }});
      }});
    }};
    const clearPinned = () => {{ pinnedEdge = null; render(); }};
    canvas.addEventListener("clear-graph-selection", clearPinned);

    edges.forEach((edge, index) => {{
      const hitbox = addEdgeHitbox(edge);
      const fallback = edgeMap[index];
      if (fallback) edge.setAttribute("aria-label", `${{fallback.from}} to ${{fallback.to}}`);
      const targets = uniqueElements([edge, hitbox]);
      targets.forEach((target) => {{
        target.addEventListener("mouseenter", () => {{ hoveredEdge = edge; render(); }});
        target.addEventListener("mouseleave", () => {{ if (hoveredEdge === edge) hoveredEdge = null; render(); }});
        target.addEventListener("pointerdown", (event) => event.stopPropagation());
        target.addEventListener("click", (event) => {{
          event.preventDefault();
          event.stopPropagation();
          pinnedEdge = pinnedEdge === edge ? null : edge;
          render();
        }});
      }});
    }});
    // Keep edge selection sticky while inspecting nodes/background.
    // Only edge clicks replace/toggle it; Escape remains keyboard escape hatch.
    document.addEventListener("keydown", (event) => {{ if (event.key === "Escape") clearPinned(); }});
  }}

  function graphSectionForControl(control) {{
    return control.closest(".graph-section");
  }}

  function clearCandidateFocus(section) {{
    const scope = section || document;
    scope.querySelectorAll(".graph-canvas.focus-active").forEach((canvas) => {{
      canvas.classList.remove("focus-active");
      canvas.dispatchEvent(new CustomEvent("clear-graph-selection"));
    }});
    scope.querySelectorAll(".node-focused, .edge-focused").forEach((element) => element.classList.remove("node-focused", "edge-focused"));
    scope.querySelectorAll("[data-candidate-focus-select]").forEach((select) => {{ select.value = ""; }});
  }}

  function applyCandidateFocus(section, candidateKey) {{
    const focusNodes = new Set((candidateFocusMap[candidateKey] || [candidateKey]).map(normalizeMermaidKey));
    clearCandidateFocus(section);
    section.querySelectorAll("[data-candidate-focus-select]").forEach((select) => {{ select.value = candidateKey || ""; }});
    section.querySelectorAll(".graph-canvas").forEach((canvas) => {{
      const svg = canvas.querySelector("svg");
      if (!svg) return;
      const nodes = graphNodes(svg);
      let matched = false;
      nodes.forEach((node, key) => {{
        if (focusNodes.has(key)) {{
          const targetNode = nodeElementFor(node);
          if (targetNode) targetNode.classList.add("node-focused");
          node.classList.add("node-focused");
          matched = true;
        }}
      }});
      const edges = edgeElements(svg);
      const labels = edgeLabels(svg);
      const edgeMap = graphEdgeMaps[canvas.id] || [];
      edges.forEach((edge, index) => {{
        const fallback = edgeMap[index];
        const endpoints = connectedNodeKeys(edge, fallback);
        if (endpoints.length >= 2 && endpoints.every((key) => focusNodes.has(key))) {{
          edge.classList.add("edge-focused");
          const label = labels[index];
          if (label) label.classList.add("edge-focused");
          matched = true;
        }}
      }});
      canvas.classList.toggle("focus-active", matched);
    }});
  }}

  function setupCandidateFocus() {{
    document.querySelectorAll("[data-candidate-focus-select]").forEach((select) => {{
      select.addEventListener("change", () => {{
        const section = graphSectionForControl(select);
        if (!section) return;
        const candidateKey = select.value || "";
        if (!candidateKey) clearCandidateFocus(section);
        else applyCandidateFocus(section, candidateKey);
      }});
    }});
    document.addEventListener("keydown", (event) => {{ if (event.key === "Escape") clearCandidateFocus(); }});
  }}

  function setupPanZoom(canvas) {{
    const svg = canvas.querySelector("svg");
    if (!svg) return;
    svg.removeAttribute("width");
    svg.removeAttribute("height");
    svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
    svg.style.width = "100%";
    svg.style.height = "100%";

    let box = contentBox(svg);
    // Zoom stays between the fitted content box and a fixed zoom-in limit. Panning is
    // deliberately unbounded: the graph can be dragged right off the canvas the same
    // way the window can be scrolled away from a document, and "Reset view" brings it
    // back. Do not clamp box.x/box.y here, dragging with no limit is the intended feel.
    const bounds = {{ ...box }};
    const initial = {{ ...box }};
    const maxZoom = 50;
    const minWidth = bounds.width / maxZoom;
    const minHeight = bounds.height / maxZoom;

    const apply = () => svg.setAttribute("viewBox", `${{box.x}} ${{box.y}} ${{box.width}} ${{box.height}}`);
    apply();

    function clientPointInSvg(event) {{
      const matrix = svg.getScreenCTM();
      if (matrix && svg.createSVGPoint) {{
        const point = svg.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        return point.matrixTransform(matrix.inverse());
      }}
      const rect = svg.getBoundingClientRect();
      return {{
        x: box.x + ((event.clientX - rect.left) / Math.max(rect.width, 1)) * box.width,
        y: box.y + ((event.clientY - rect.top) / Math.max(rect.height, 1)) * box.height,
      }};
    }}

    function clientDeltaInSvg(dx, dy) {{
      const matrix = svg.getScreenCTM();
      if (matrix) {{
        const scaleX = Math.hypot(matrix.a, matrix.b);
        const scaleY = Math.hypot(matrix.c, matrix.d);
        if (scaleX > 0 && scaleY > 0) return {{ x: dx / scaleX, y: dy / scaleY }};
      }}
      const rect = svg.getBoundingClientRect();
      return {{
        x: dx / Math.max(rect.width, 1) * box.width,
        y: dy / Math.max(rect.height, 1) * box.height,
      }};
    }}

    let canvasMode = false;
    const modifierPressed = (event) => event.ctrlKey || event.metaKey;
    const canUseCanvasDirectly = () => canvasMode;
    const canPan = (event) => canUseCanvasDirectly() || modifierPressed(event) || event.button === 1;
    const clearTextSelection = () => {{
      const selection = window.getSelection && window.getSelection();
      if (selection && selection.rangeCount) selection.removeAllRanges();
    }};

    canvas.addEventListener("wheel", (event) => {{
      // Focus is the opt-in for wheel zoom: anywhere else the wheel keeps scrolling
      // the page, and a scroll that merely passes over the canvas does not zoom it.
      if (!canvas.contains(document.activeElement)) return;
      if (!canUseCanvasDirectly() && !modifierPressed(event)) return;
      event.preventDefault();
      const focus = clientPointInSvg(event);
      const factor = event.deltaY > 0 ? 1.14 : 0.88;
      const nextWidth = Math.min(Math.max(box.width * factor, minWidth), bounds.width);
      const nextHeight = Math.min(Math.max(box.height * factor, minHeight), bounds.height);
      box.x = focus.x - (focus.x - box.x) * (nextWidth / box.width);
      box.y = focus.y - (focus.y - box.y) * (nextHeight / box.height);
      box.width = nextWidth;
      box.height = nextHeight;
      apply();
    }}, {{ passive: false }});

    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    function endDrag() {{
      if (!dragging) return;
      dragging = false;
      canvas.classList.remove("panning");
      clearTextSelection();
    }}
    canvas.addEventListener("pointerdown", (event) => {{
      // Node links keep their own focus; anywhere else on the canvas claims the wheel.
      if (event.target.closest && event.target.closest("a")) return;
      canvas.focus({{ preventScroll: true }});
      if (edgeContainerFor(event.target)) return;
      if (!canPan(event)) return;
      event.preventDefault();
      clearTextSelection();
      dragging = true;
      lastX = event.clientX;
      lastY = event.clientY;
      canvas.classList.add("panning");
      canvas.setPointerCapture(event.pointerId);
    }});
    canvas.addEventListener("pointermove", (event) => {{
      if (!dragging) return;
      event.preventDefault();
      const delta = clientDeltaInSvg(event.clientX - lastX, event.clientY - lastY);
      box.x -= delta.x;
      box.y -= delta.y;
      lastX = event.clientX;
      lastY = event.clientY;
      apply();
    }});
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);
    canvas.addEventListener("lostpointercapture", endDrag);

    const reset = document.querySelector(`[data-reset="${{canvas.id}}"]`);
    if (reset) reset.addEventListener("click", () => {{ box = {{ ...initial }}; apply(); }});

    const modeToggle = document.querySelector(`[data-canvas-mode="${{canvas.id}}"]`);
    if (modeToggle) modeToggle.addEventListener("click", () => {{
      canvasMode = !canvasMode;
      canvas.classList.toggle("canvas-mode", canvasMode);
      modeToggle.setAttribute("aria-pressed", String(canvasMode));
      modeToggle.textContent = canvasMode ? "Canvas mode on" : "Canvas mode";
      if (!canvasMode) endDrag();
    }});
  }}

  function setupFilters() {{
    const buttons = document.querySelectorAll("[data-filter]");
    const cards = document.querySelectorAll("#node-details-section .detail-card");
    buttons.forEach((button) => {{
      button.addEventListener("click", () => {{
        const filter = button.getAttribute("data-filter") || "all";
        buttons.forEach((item) => item.classList.toggle("active", item === button));
        cards.forEach((card) => {{
          const type = card.getAttribute("data-node-type") || "";
          card.hidden = filter !== "all" && type !== filter;
        }});
      }});
    }});
    const allButton = document.querySelector('[data-filter="all"]');
    if (allButton) allButton.classList.add("active");
  }}

  function closeModal(modal) {{
    if (modal.close) modal.close();
    else modal.removeAttribute("open");
  }}

  function setupFloatingNav() {{
    const nav = document.querySelector(".floating-nav");
    const toggle = nav?.querySelector(".nav-toggle");
    if (!nav || !toggle) return;
    toggle.addEventListener("click", () => {{
      const open = !nav.classList.contains("open");
      nav.classList.toggle("open", open);
      toggle.setAttribute("aria-expanded", String(open));
    }});
    nav.querySelectorAll("a").forEach((link) => link.addEventListener("click", () => {{
      nav.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    }}));
    document.addEventListener("click", (event) => {{
      if (!nav.contains(event.target)) {{
        nav.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      }}
    }});
  }}

  function setupModal() {{
    const modal = document.getElementById("node-modal");
    if (!modal) return;
    modal.querySelector("[data-close-modal]")?.addEventListener("click", () => closeModal(modal));
    modal.addEventListener("click", (event) => {{
      if (event.target === modal) closeModal(modal);
    }});
  }}

  function runSetup(label, callback) {{
    try {{
      callback();
    }} catch (error) {{
      console.warn(`${{label}} setup failed`, error);
    }}
  }}

  function setupGraphs() {{
    document.querySelectorAll(".graph-section").forEach((section) => {{
      const canvas = section.querySelector(".graph-canvas");
      if (canvas) runSetup("pan/zoom", () => setupPanZoom(canvas));
      runSetup("node detail clicks", () => installDetailClicks(section));
      runSetup("edge highlights", () => setupEdgeHighlights(section));
    }});
    runSetup("filters", setupFilters);
    runSetup("candidate focus", setupCandidateFocus);
    runSetup("modal", setupModal);
    runSetup("floating nav", setupFloatingNav);
  }}

{script_setup}
</script>
</body>
</html>
"""
