"""Shared visual-factor selection for graph renderers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Collection

from .costs import resolve_edge_groups


@dataclass(frozen=True)
class VisualFactor:
    """Resolved group data needed by every graph renderer."""

    record: dict[str, Any]
    raw_id: str
    relation: str
    inputs: tuple[str, ...]
    target: str


@dataclass(frozen=True)
class VisualFactorSelection:
    """Eligible factors and raw edges they replace in rendered graphs."""

    factors: tuple[VisualFactor, ...]
    member_edges: frozenset[tuple[str, str, str]]


def select_visual_factors(
    state: dict[str, Any],
    available_node_ids: Collection[str],
) -> VisualFactorSelection:
    """Select renderable groups whose target and every source are available."""
    available = set(available_node_ids)
    records = {
        factor["id"]: factor
        for factor in state.get("factors") or []
        if isinstance(factor, dict) and isinstance(factor.get("id"), str)
    }
    selected = tuple(
        VisualFactor(
            record=records[group.group_id],
            raw_id=group.group_id,
            relation=group.relation,
            inputs=group.sources,
            target=group.target,
        )
        for group in resolve_edge_groups(state)[0]
        if group.group_id in records and group.target in available and all(source in available for source in group.sources)
    )
    member_edges = frozenset(
        (input_id, factor.target, factor.relation)
        for factor in selected
        for input_id in factor.inputs
    )
    return VisualFactorSelection(selected, member_edges)


def compact_factor_label(factor: VisualFactor) -> str:
    """Return shared compact label for Mermaid and offline SVG factor nodes."""
    return f"{factor.raw_id}\n{factor.relation} group, score {factor.record.get('score')}"
