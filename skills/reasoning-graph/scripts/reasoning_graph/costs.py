"""Truth/search cost and contradiction penalty helpers."""

from __future__ import annotations

import math
from typing import Any

from .models import LEGACY_COST_COMPONENT_ALIASES, PROBE_LIKE_MARKERS, SEARCH_COST_COMPONENTS
from .state import by_id
from .utils import finite_float


def probability_cost(value: Any, field: str = "probability") -> float:
    try:
        p = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric, got {value!r}")
    if not 0 < p <= 1:
        raise ValueError(f"{field} must be in (0, 1], got {p}")
    return -math.log(p)


def uncertainty_cost_from_prior(prior: Any) -> float:
    return probability_cost(prior, "prior")


def text_looks_probe_like(*values: Any) -> bool:
    text = " ".join(str(value or "").lower() for value in values)
    return any(marker in text for marker in PROBE_LIKE_MARKERS)


def item_has_explicit_effort_budget(item: dict[str, Any]) -> bool:
    components = item.get("cost_components") if isinstance(item.get("cost_components"), dict) else {}
    has_cost_component = any(
        key in components
        for key in ("effort_budget", "resource_budget", "compute_budget")
    )
    budget = item.get("budget")
    has_budget_metadata = isinstance(budget, dict) and any(
        key in budget
        for key in ("max_attempts", "max_seconds", "max_items", "max_sources", "stop_after")
    )
    return has_cost_component and has_budget_metadata


def node_truth_cost(node: dict[str, Any] | None) -> float:
    """Local truth cost for a frontier node.

    `prior` is for assumptions/candidates. `confidence` is for evidence,
    derived claims, and noisy test observations. Missing confidence on accepted
    evidence/tests means "no truth penalty", not certainty proof; users can add
    confidence when source reliability matters.
    """

    if not node:
        return 0.0
    for field in ("posterior", "confidence", "probability", "prior"):
        if field in node:
            return probability_cost(node[field], field)
    return 0.0


def cost_components_for_item(item: dict[str, Any], nodes: dict[str, dict[str, Any]]) -> dict[str, float]:
    explicit = item.get("cost_components") or item.get("cost") or {}
    if explicit is None:
        explicit = {}
    if not isinstance(explicit, dict):
        raise ValueError(f"frontier item {item.get('id')} cost_components must be object")

    components: dict[str, float] = {}
    for raw_key, raw_value in explicit.items():
        key = LEGACY_COST_COMPONENT_ALIASES.get(str(raw_key), str(raw_key))
        if key not in SEARCH_COST_COMPONENTS:
            continue
        if raw_value is None or raw_value == "auto":
            continue
        try:
            components[key] = float(raw_value)
        except (TypeError, ValueError):
            raise ValueError(f"frontier item {item.get('id')} component {raw_key} must be numeric")

    node = nodes.get(str(item.get("node")))
    if "truth" not in components:
        components["truth"] = node_truth_cost(node)

    for key in SEARCH_COST_COMPONENTS:
        components.setdefault(key, 0.0)
    return components


def probability_from_value(value: Any) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= probability <= 1:
        return probability
    return None


def contradiction_probability(state: dict[str, Any], edge: dict[str, Any]) -> float:
    """Return probability that a contradiction edge should be believed.

    Contradictions never delete/disqualify their target; higher probability means
    higher truth-cost penalty. Explicit edge strength wins; otherwise source node certainty
    is inferred from posterior/prior/type.
    """

    if edge.get("hard") is True or edge.get("mode") == "hard":
        return 1.0
    strength = probability_from_value(edge.get("strength"))
    if strength is not None:
        return strength
    nodes = by_id(state.get("nodes", []), "node")
    source = nodes.get(str(edge.get("from")), {})
    for field in ("posterior", "confidence", "probability", "prior"):
        value = probability_from_value(source.get(field))
        if value is not None:
            return value
    if edge.get("hard") is False or edge.get("mode") == "soft":
        return 0.5
    if source.get("type") in {"evidence", "constraint"}:
        return 1.0
    if source.get("type") == "test" and source.get("status") == "performed":
        return 1.0
    return 0.5


def contradiction_is_hard(state: dict[str, Any], edge: dict[str, Any]) -> bool:
    if edge.get("hard") is False or edge.get("mode") == "soft":
        return False
    return contradiction_probability(state, edge) >= 1.0


def contradiction_truth_penalty(state: dict[str, Any], edge: dict[str, Any]) -> float:
    """Incoming contradiction penalty. Even hard contradictions rank as near-zero belief instead of deleting nodes."""

    probability = min(max(contradiction_probability(state, edge), 0.0), 1.0 - 1e-12)
    return -math.log(1.0 - probability)


def node_contradiction_penalties(state: dict[str, Any]) -> dict[str, float]:
    nodes = by_id(state.get("nodes", []), "node")
    penalties: dict[str, float] = {node_id: 0.0 for node_id in nodes}
    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge_type = edge.get("type") or edge.get("label")
        dst = edge.get("to")
        if edge_type != "contradicts" or dst not in nodes:
            continue
        penalties[str(dst)] += contradiction_truth_penalty(state, edge)
    return penalties


def compute_costs(state: dict[str, Any]) -> dict[str, Any]:
    nodes = by_id(state.get("nodes", []), "node")
    contradiction_penalties = node_contradiction_penalties(state)
    frontier = state.get("frontier", [])
    items = by_id(frontier, "frontier item")
    search_memo: dict[str, float] = {}
    truth_memo: dict[str, float] = {}
    visiting: set[str] = set()

    def item_step_costs(item: dict[str, Any]) -> tuple[float, float]:
        if "cost_components" not in item and "cost" not in item and "step_cost" in item:
            search_step = float(item["step_cost"])
            truth_step = finite_float(item.get("step_truth_cost"))
            if truth_step is None:
                node_id = str(item.get("node"))
                truth_step = node_truth_cost(nodes.get(node_id)) + contradiction_penalties.get(node_id, 0.0)
            effort_step = max(0.0, search_step - truth_step)
            item["cost_components"] = {
                "truth": round(truth_step, 6),
                "verification": round(effort_step, 6),
                "reasoning_complexity": 0.0,
                "constraint_tension": 0.0,
            }
        else:
            components = cost_components_for_item(item, nodes)
            node_id = str(item.get("node"))
            components["truth"] = components.get("truth", 0.0) + contradiction_penalties.get(node_id, 0.0)
            item["cost_components"] = {key: round(value, 6) for key, value in components.items()}
            truth_step = components["truth"]
            search_step = sum(components.values())
        item["step_truth_cost"] = round(truth_step, 6)
        item["step_cost"] = round(search_step, 6)
        return search_step, truth_step

    def item_search_cost(item_id: str) -> float:
        if item_id in search_memo:
            return search_memo[item_id]
        if item_id in visiting:
            raise ValueError(f"cycle in frontier parent chain at {item_id}")
        item = items.get(item_id)
        if not item:
            raise ValueError(f"missing frontier item {item_id}")
        visiting.add(item_id)
        parent_id = item.get("parent")
        parent_cost = 0.0
        if parent_id:
            if parent_id not in items:
                raise ValueError(f"frontier item {item_id} references missing parent {parent_id}")
            parent_cost = item_search_cost(str(parent_id))
        search_step, truth_step = item_step_costs(item)
        truth_parent = 0.0
        if parent_id:
            truth_parent = truth_memo[str(parent_id)]
        search_total = parent_cost + search_step
        truth_total = truth_parent + truth_step
        item["truth_cost"] = round(truth_total, 6)
        item["search_cost"] = round(search_total, 6)
        item["path_cost"] = round(search_total, 6)  # legacy alias; prefer search_cost.
        search_memo[item_id] = search_total
        truth_memo[item_id] = truth_total
        visiting.remove(item_id)
        return search_total

    for item in frontier:
        item_id = item.get("id")
        if isinstance(item_id, str):
            item_search_cost(item_id)
    return state


def sorted_frontier(state: dict[str, Any]) -> dict[str, Any]:
    compute_costs(state)
    state["frontier"] = sorted(
        state.get("frontier", []),
        key=lambda item: (float(item.get("search_cost", item.get("path_cost", math.inf))), str(item.get("id", ""))),
    )
    return state


def sorted_frontier_items(state: dict[str, Any], item_ids: Iterable[str] | None = None) -> list[dict[str, Any]]:
    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    selected = items.values() if item_ids is None else (items[item_id] for item_id in item_ids if item_id in items)
    return sorted(selected, key=lambda item: (float(item.get("search_cost", item.get("path_cost", math.inf))), str(item.get("id", ""))))
