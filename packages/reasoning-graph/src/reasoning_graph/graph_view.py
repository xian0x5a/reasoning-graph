"""One normalized drawing of the graph, shared by the Mermaid and offline SVG renderers.

Everything a renderer draws is decided here: which nodes and edges appear, their
render ids, labels, groups, colours and line styles. A renderer only lays them out
in its own syntax, so the two outputs cannot drift apart (#18).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .costs import node_belief_label, node_effective_truth_costs, probability_from_cost
from .identities import RenderIdentityMap, render_identity_map
from .models import BELIEF_NODE_TYPES, node_render_class, node_type_label
from .policy import answer_labels
from .visual_factors import VisualFactor, compact_factor_label, select_visual_factors

# Render class -> (fill, stroke). Both renderers paint from this one table.
NODE_COLORS = {
    "goal": ("#fef3c7", "#d97706"),
    "observation": ("#ecfeff", "#0891b2"),
    "constraint": ("#fff7ed", "#ea580c"),
    "hypothesis": ("#f5f3ff", "#7c3aed"),
    "test": ("#e0f2fe", "#0284c7"),
    "not_run": ("#f8fafc", "#94a3b8"),
    "candidate": ("#dbeafe", "#2563eb"),
    "factor": ("#f1f5f9", "#475569"),
}

# (group id, title, node types). Mermaid draws each as a subgraph box.
GRAPH_GROUPS = (
    ("cluster_goal", "Goal", {"goal"}),
    ("cluster_observations", "Observations", {"observation", "constraint"}),
    ("cluster_hypotheses", "Hypotheses", {"hypothesis", "test"}),
    ("cluster_candidates", "Candidates", {"candidate_solution"}),
)
OTHER_GROUP = ("cluster_other", "Other")

# Edges that are not a derivation step are drawn dashed; follow-up work also gets a warm colour.
DASHED_EDGE_TYPES = {"contradicts", "prompts", "tested_by", "tests"}
FOLLOW_UP_EDGE_TYPES = {"prompts", "tested_by", "tests"}


def compact_node_label(node: dict[str, Any], effective_truth_cost: float, answer_label: str = "") -> str:
    # Keep graph labels stable and tiny. Full text lives in modal/detail cards;
    # long labels are hard to navigate and can expose HTML entity noise.
    node_id = str(node.get("id") or "node")
    # The answer is labelled, not highlighted: the focus control lights a path when the reader asks.
    id_line = f"{node_id} · {answer_label}" if answer_label else node_id
    parts = (id_line, node_type_label(node), node_belief_label(node, effective_truth_cost))
    return "\n".join(part for part in parts if part)


def edge_type(edge: dict[str, Any]) -> str:
    return str(edge.get("type") or edge.get("label") or "leads_to")


def _group_of(node_type: str) -> str:
    return next((group_id for group_id, _, types in GRAPH_GROUPS if node_type in types), OTHER_GROUP[0])


@dataclass(frozen=True)
class ViewNode:
    raw_id: str
    render_id: str
    anchor: str
    node_type: str
    render_class: str
    group: str
    label: str
    # Computed belief of a claim; None for goals, constraints and tests.
    belief: float | None
    answer_label: str
    record: dict[str, Any]

    @property
    def colors(self) -> tuple[str, str]:
        return NODE_COLORS[self.render_class]


@dataclass(frozen=True)
class ViewEdge:
    # Ends are ("node", raw id) or ("factor", raw id), so a node cannot collide with a factor.
    source_key: tuple[str, str]
    target_key: tuple[str, str]
    source: str
    target: str
    label: str

    @property
    def dashed(self) -> bool:
        return self.label in DASHED_EDGE_TYPES or self.label.startswith("grouped ")

    @property
    def follow_up(self) -> bool:
        return self.label in FOLLOW_UP_EDGE_TYPES


@dataclass(frozen=True)
class ViewFactor:
    raw_id: str
    render_id: str
    label: str
    factor: VisualFactor
    # In declared input order; a renderer that needs a stable order sorts them itself.
    input_edges: tuple[ViewEdge, ...]
    target_edge: ViewEdge | None

    @property
    def colors(self) -> tuple[str, str]:
        return NODE_COLORS["factor"]


@dataclass(frozen=True)
class GraphView:
    identities: RenderIdentityMap
    # In state order.
    nodes: tuple[ViewNode, ...]
    # Drawn raw edges in state order; edges a factor replaces are left out.
    edges: tuple[ViewEdge, ...]
    factors: tuple[ViewFactor, ...]

    def drawn_edges(self) -> list[ViewEdge]:
        """Every edge in drawing order: raw edges, then each factor's inputs and its target edge."""
        drawn = list(self.edges)
        for factor in self.factors:
            drawn.extend(factor.input_edges)
            if factor.target_edge is not None:
                drawn.append(factor.target_edge)
        return drawn


def graph_view(state: dict[str, Any], identities: RenderIdentityMap | None = None) -> GraphView:
    identities = identities or render_identity_map(state)
    truth_costs = node_effective_truth_costs(state)
    answers = answer_labels(state)

    nodes: list[ViewNode] = []
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_id = str(node.get("id"))
        render_id = identities.node(raw_id)
        if render_id is None:
            continue
        node_type = str(node.get("type", ""))
        nodes.append(
            ViewNode(
                raw_id=raw_id,
                render_id=render_id,
                anchor=identities.node_anchor(raw_id),
                node_type=node_type,
                render_class=node_render_class(node),
                group=_group_of(node_type),
                label=compact_node_label(node, truth_costs[raw_id], answers.get(raw_id, "")),
                belief=probability_from_cost(truth_costs[raw_id]) if node_type in BELIEF_NODE_TYPES else None,
                answer_label=answers.get(raw_id, ""),
                record=node,
            )
        )
    render_ids = {node.raw_id: node.render_id for node in nodes}

    def node_edge(source: str, target: str, label: str) -> ViewEdge:
        return ViewEdge(("node", source), ("node", target), render_ids[source], render_ids[target], label)

    selection = select_visual_factors(state, render_ids)
    factors: list[ViewFactor] = []
    for factor in selection.factors:
        factor_id = identities.factor(factor.raw_id)
        if factor_id is None:
            continue
        factor_key = ("factor", factor.raw_id)
        factors.append(
            ViewFactor(
                raw_id=factor.raw_id,
                render_id=factor_id,
                label=compact_factor_label(factor),
                factor=factor,
                input_edges=tuple(
                    ViewEdge(("node", source), factor_key, render_ids[source], factor_id, f"grouped {factor.relation}")
                    for source in factor.inputs
                    if source in render_ids
                ),
                target_edge=(
                    ViewEdge(factor_key, ("node", factor.target), factor_id, render_ids[factor.target], f"{factor.relation} factor")
                    if factor.target in render_ids
                    else None
                ),
            )
        )

    edges = [
        node_edge(str(edge.get("from")), str(edge.get("to")), edge_type(edge))
        for edge in state.get("edges", [])
        if isinstance(edge, dict)
        and str(edge.get("from")) in render_ids
        and str(edge.get("to")) in render_ids
        and (str(edge.get("from")), str(edge.get("to")), edge_type(edge)) not in selection.member_edges
    ]
    return GraphView(identities, tuple(nodes), tuple(edges), tuple(factors))
