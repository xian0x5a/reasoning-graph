"""Truth/search cost and evidence-update helpers."""

from __future__ import annotations

import math
from typing import Any, Iterable

from .models import LEGACY_COST_COMPONENT_ALIASES, PROBE_LIKE_MARKERS, SEARCH_COST_COMPONENTS
from .state import by_id
from .utils import finite_float


NEUTRAL_UPDATE_PRIOR = 0.5


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


def probability_from_value(value: Any) -> float | None:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if 0 <= probability <= 1:
        return probability
    return None


def likelihood_ratio_from_value(value: Any, field: str = "likelihood_ratio") -> float:
    try:
        likelihood_ratio = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric, got {value!r}")
    if likelihood_ratio <= 0:
        raise ValueError(f"{field} must be > 0, got {likelihood_ratio}")
    return likelihood_ratio


def probability_from_log_odds(log_odds: float) -> float:
    if log_odds >= 0:
        if log_odds > 745:
            return 1.0
        denominator = 1.0 + math.exp(-log_odds)
        return 1.0 / denominator
    if log_odds < -745:
        return 0.0
    odds = math.exp(log_odds)
    return odds / (1.0 + odds)


def log_odds_from_probability(probability: float) -> float:
    if probability >= 1.0:
        return math.inf
    if probability <= 0.0:
        return -math.inf
    return math.log(probability / (1.0 - probability))


def probability_from_cost(cost: float) -> float:
    if cost <= 0:
        return 1.0
    if cost > 745:
        return 0.0
    return math.exp(-cost)


def node_has_probability(node: dict[str, Any] | None) -> bool:
    return bool(node) and any(field in node for field in ("posterior", "confidence", "probability", "prior"))


def node_local_truth_cost(node: dict[str, Any] | None, *, include_posterior: bool = True) -> float:
    """Local node truth cost before graph-premise propagation."""

    if not node:
        return 0.0
    fields = ("posterior", "confidence", "probability", "prior") if include_posterior else ("confidence", "probability", "prior")
    for field in fields:
        if field in node:
            return probability_cost(node[field], field)
    return 0.0


def node_truth_cost(node: dict[str, Any] | None) -> float:
    """Local truth cost for a node, preserving the historical public helper.

    `prior` is for assumptions/candidates. `confidence` is for evidence,
    derived claims, and noisy test observations. Missing confidence on accepted
    evidence/tests means "no local truth penalty", not certainty proof; users can
    add confidence when source reliability matters.
    """

    return node_local_truth_cost(node)



def node_effective_truth_costs(state: dict[str, Any]) -> dict[str, float]:
    """Compute effective node truth costs from premises and LR evidence updates.

    Incoming `leads_to` edges are required premises and contribute source truth
    cost to the target's base belief. Incoming `supports`/`contradicts` edges
    with `likelihood_ratio` update that base belief in odds space. Explicit node
    `posterior` is treated as already-calibrated and wins over graph-derived
    updates to avoid double counting.
    """

    nodes = by_id(state.get("nodes", []), "node")
    premise_sources: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    likelihood_edges: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes}

    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge_type = edge.get("type") or edge.get("label")
        src = edge.get("from")
        dst = edge.get("to")
        if not isinstance(src, str) or not isinstance(dst, str) or src not in nodes or dst not in nodes:
            continue
        if edge_type == "leads_to":
            premise_sources.setdefault(dst, []).append(src)
        elif edge_type in {"supports", "contradicts"} and "likelihood_ratio" in edge:
            likelihood_edges.setdefault(dst, []).append(edge)

    memo: dict[str, float] = {}
    visiting: set[str] = set()

    def effective_cost(node_id: str) -> float:
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            raise ValueError(f"cycle in truth dependency graph at {node_id}")
        node = nodes.get(node_id)
        if not node:
            return 0.0
        if "posterior" in node:
            cost = node_local_truth_cost(node)
            memo[node_id] = cost
            return cost

        visiting.add(node_id)
        local_cost = node_local_truth_cost(node, include_posterior=False)
        premise_cost = sum(effective_cost(source_id) for source_id in premise_sources.get(node_id, []))
        base_cost = local_cost + premise_cost
        lrs = likelihood_edges.get(node_id, [])
        if lrs:
            # Missing local/premise probability is not certainty; use neutral odds so LR can move belief.
            base_probability = NEUTRAL_UPDATE_PRIOR if base_cost == 0.0 and not node_has_probability(node) else probability_from_cost(base_cost)
            log_odds = log_odds_from_probability(base_probability)
            for edge in lrs:
                log_odds += math.log(likelihood_ratio_from_value(edge.get("likelihood_ratio")))
            updated_probability = probability_from_log_odds(log_odds)
            if updated_probability <= 0.0:
                cost = math.inf
            else:
                cost = -math.log(updated_probability)
        else:
            cost = base_cost
        visiting.remove(node_id)
        memo[node_id] = cost
        return cost

    for node_id in nodes:
        effective_cost(node_id)
    return memo


def cost_components_for_item(
    item: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    node_truth_costs: dict[str, float],
) -> dict[str, float]:
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

    node_id = str(item.get("node"))
    node = nodes.get(node_id)
    if "truth" not in components:
        components["truth"] = node_truth_costs.get(node_id, node_truth_cost(node))

    for key in SEARCH_COST_COMPONENTS:
        components.setdefault(key, 0.0)
    return components


def compute_costs(state: dict[str, Any]) -> dict[str, Any]:
    nodes = by_id(state.get("nodes", []), "node")
    node_truth_costs = node_effective_truth_costs(state)
    frontier = state.get("frontier", [])

    for item in frontier:
        if not isinstance(item, dict):
            continue
        if "cost_components" not in item and "cost" not in item and "step_cost" in item:
            node_id = str(item.get("node"))
            truth_cost = finite_float(item.get("step_truth_cost"))
            if truth_cost is None:
                truth_cost = node_truth_costs.get(node_id, node_truth_cost(nodes.get(node_id)))
            legacy_search_cost = float(item["step_cost"])
            work_cost = max(0.0, legacy_search_cost - truth_cost)
            search_cost = truth_cost + work_cost
            item["cost_components"] = {
                "truth": round(truth_cost, 6),
                "verification": round(work_cost, 6),
                "effort_budget": 0.0,
                "reasoning_complexity": 0.0,
                "constraint_tension": 0.0,
            }
        else:
            components = cost_components_for_item(item, nodes, node_truth_costs)
            truth_cost = components["truth"]
            work_cost = sum(value for key, value in components.items() if key != "truth")
            search_cost = truth_cost + work_cost
            item["cost_components"] = {key: round(value, 6) for key, value in components.items()}

        item["truth_cost"] = round(truth_cost, 6)
        item["work_cost"] = round(work_cost, 6)
        item["step_truth_cost"] = round(truth_cost, 6)
        item["step_cost"] = round(search_cost, 6)
        item["search_cost"] = round(search_cost, 6)
        item["path_cost"] = round(search_cost, 6)  # legacy alias; prefer search_cost.
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
