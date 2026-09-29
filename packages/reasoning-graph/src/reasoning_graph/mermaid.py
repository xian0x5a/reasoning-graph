"""Mermaid flowchart source for a reasoning graph state."""

from __future__ import annotations

import html
from typing import Any

from .graph_view import GRAPH_GROUPS, NODE_COLORS, OTHER_GROUP, ViewEdge, graph_view
from .identities import RenderIdentityMap


def mermaid_label(text: str) -> str:
    # Mermaid node labels are HTML-ish; keep labels compact and safe.
    escaped = html.escape(text, quote=True)
    return escaped.replace("\n", "<br/>")


# Left to right: observations, the widest rank of a real graph, stack in a column the
# page canvas grows down to fit. Top down lays them in one row wider than any screen.
LAYOUT_DIRECTION = "LR"

GROUP_STYLES = {
    "cluster_goal": "fill:#fffbeb,stroke:#fde68a,stroke-width:1px",
    "cluster_observations": "fill:#f8fafc,stroke:#bae6fd,stroke-width:1px",
    "cluster_hypotheses": "fill:#faf5ff,stroke:#ddd6fe,stroke-width:1px",
    "cluster_candidates": "fill:#eff6ff,stroke:#bfdbfe,stroke-width:1px",
    "cluster_factors": "fill:#f8fafc,stroke:#cbd5e1,stroke-dasharray:3 3",
    "cluster_other": "fill:#fafafa,stroke:#e5e7eb,stroke-width:1px",
}

# Mermaid-only touches on top of the shared colours.
CLASS_EXTRAS = {
    "goal": ",stroke-width:2px",
    "not_run": ",stroke-dasharray:5 4,color:#64748b",
    "candidate": ",stroke-width:2px",
    "factor": ",stroke-dasharray: 3 3",
}


def mermaid_edge(edge: ViewEdge) -> str:
    if edge.dashed:
        return f"  {edge.source} -. {edge.label} .-> {edge.target}"
    return f"  {edge.source} -- {edge.label} --> {edge.target}"


def to_mermaid(
    state: dict[str, Any],
    *,
    identities: RenderIdentityMap | None = None,
) -> str:
    view = graph_view(state, identities)
    lines = [f"flowchart {LAYOUT_DIRECTION}"]

    drawn_groups: list[str] = []
    for group_id, title in (*((group_id, title) for group_id, title, _ in GRAPH_GROUPS), OTHER_GROUP):
        group_nodes = [node for node in view.nodes if node.group == group_id]
        if not group_nodes:
            continue
        drawn_groups.append(group_id)
        lines.append(f"  subgraph {group_id}[{title}]")
        lines.extend(f'    {node.render_id}["{mermaid_label(node.label)}"]' for node in group_nodes)
        lines.append("  end")

    if view.factors:
        drawn_groups.append("cluster_factors")
        lines.append("  subgraph cluster_factors[Factors]")
        lines.extend(f'    {factor.render_id}{{{{"{mermaid_label(factor.label)}"}}}}' for factor in view.factors)
        lines.append("  end")

    drawn_edges = view.drawn_edges()
    lines.extend(mermaid_edge(edge) for edge in drawn_edges)

    lines.append("")
    lines.extend(
        f"  classDef {cls} fill:{fill},stroke:{stroke}{CLASS_EXTRAS.get(cls, '')};" for cls, (fill, stroke) in NODE_COLORS.items()
    )
    lines.append("")
    # Mermaid draws a node for a styled group that does not exist, so only drawn groups are styled.
    lines.extend(f"  style {group_id} {GROUP_STYLES[group_id]};" for group_id in drawn_groups)
    lines.append("")

    lines.extend(
        f"  linkStyle {index} stroke:#d97706,stroke-dasharray:5 5;" for index, edge in enumerate(drawn_edges) if edge.follow_up
    )

    if view.factors:
        lines.append(f"  class {','.join(factor.render_id for factor in view.factors)} factor;")

    for cls in sorted({node.render_class for node in view.nodes}):
        members = sorted((node for node in view.nodes if node.render_class == cls), key=lambda node: node.raw_id)
        lines.append(f"  class {','.join(node.render_id for node in members)} {cls};")

    for node in sorted(view.nodes, key=lambda node: node.raw_id):
        tooltip = mermaid_label(f"Open details for {node.raw_id}")
        lines.append(f'  click {node.render_id} "#{node.anchor}" "{tooltip}"')
    return "\n".join(lines) + "\n"
