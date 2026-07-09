"""Shared visual-factor selection for graph renderers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Collection


VISUAL_FACTOR_RELATIONS = frozenset({"leads_to", "supports", "contradicts"})


@dataclass(frozen=True)
class VisualFactor:
    """Validated factor data needed by every graph renderer."""

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
    """Select renderable factors whose target and every input are available."""
    available = set(available_node_ids)
    selected: list[VisualFactor] = []
    factors = state.get("factors", [])
    for factor in factors if isinstance(factors, list) else []:
        if not isinstance(factor, dict):
            continue
        raw_id = factor.get("id")
        relation = factor.get("relation")
        target = factor.get("target")
        inputs = factor.get("inputs")
        if not isinstance(raw_id, str) or not raw_id:
            continue
        if relation not in VISUAL_FACTOR_RELATIONS:
            continue
        if not isinstance(target, str) or target not in available:
            continue
        if not isinstance(inputs, list) or not inputs or not all(isinstance(item, str) for item in inputs):
            continue
        if any(item not in available for item in inputs):
            continue
        selected.append(
            VisualFactor(
                record=factor,
                raw_id=raw_id,
                relation=relation,
                inputs=tuple(inputs),
                target=target,
            )
        )

    member_edges = frozenset(
        (input_id, factor.target, factor.relation)
        for factor in selected
        for input_id in factor.inputs
    )
    return VisualFactorSelection(tuple(selected), member_edges)


def compact_factor_label(factor: dict[str, Any]) -> str:
    """Return shared compact label for Mermaid and offline SVG factor nodes."""
    factor_id = str(factor.get("id") or "factor")
    relation = str(factor.get("relation") or "factor")
    aggregation = factor.get("aggregation") if isinstance(factor.get("aggregation"), dict) else {}
    kind = str(aggregation.get("kind") or "aggregation")
    if kind == "joint_probability" and "probability" in aggregation:
        return f"{factor_id}\n{relation} joint P={aggregation.get('probability')}"
    if kind == "likelihood":
        return f"{factor_id}\n{relation} joint likelihood"
    return f"{factor_id}\n{relation} {kind}"
