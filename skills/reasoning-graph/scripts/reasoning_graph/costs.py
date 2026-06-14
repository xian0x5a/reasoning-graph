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


def likelihood_probability_from_value(value: Any, field: str) -> float:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric, got {value!r}")
    if not 0 < probability <= 1:
        raise ValueError(f"{field} must be in (0, 1], got {probability}")
    return probability


def likelihood_ratio_from_edge(edge: dict[str, Any]) -> float:
    if "likelihood" in edge and "likelihood_ratio" in edge:
        raise ValueError("edge must not set both likelihood and likelihood_ratio")
    if "likelihood" in edge:
        likelihood = edge.get("likelihood")
        if not isinstance(likelihood, dict):
            raise ValueError("likelihood must be an object")
        if_target_true = likelihood_probability_from_value(
            likelihood.get("if_target_true"), "likelihood.if_target_true"
        )
        if_target_false = likelihood_probability_from_value(
            likelihood.get("if_target_false"), "likelihood.if_target_false"
        )
        return if_target_true / if_target_false
    return likelihood_ratio_from_value(edge.get("likelihood_ratio"))


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


def assert_acyclic_premise_dependencies(premise_sources: dict[str, list[str]]) -> None:
    """Reject raw `leads_to` cycles before any premise-group cost replacement."""

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visited:
            return
        if node_id in visiting:
            raise ValueError(f"cycle in truth dependency graph at {node_id}")
        visiting.add(node_id)
        for source_id in premise_sources.get(node_id, []):
            visit(source_id)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in premise_sources:
        visit(node_id)


def node_effective_truth_costs(state: dict[str, Any]) -> dict[str, float]:
    """Compute effective node truth costs from premises and likelihood updates.

    Incoming `leads_to` edges are required premises and contribute source truth
    cost to the target's base belief. Top-level premise_groups replace grouped
    member costs with a calibrated joint_probability. Incoming `supports`/
    `contradicts` edges with `likelihood` or `likelihood_ratio` update that
    base belief in odds space.
    Explicit node `posterior` is treated as already-calibrated and wins over
    graph-derived updates to avoid double counting.
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
        elif edge_type in {"supports", "contradicts"} and ("likelihood_ratio" in edge or "likelihood" in edge):
            likelihood_edges.setdefault(dst, []).append(edge)

    assert_acyclic_premise_dependencies(premise_sources)

    premise_group_costs: dict[str, list[float]] = {node_id: [] for node_id in nodes}
    grouped_premise_sources: dict[str, set[str]] = {node_id: set() for node_id in nodes}
    premise_source_sets = {node_id: set(sources) for node_id, sources in premise_sources.items()}
    premise_groups = state.get("premise_groups", [])
    if premise_groups is None:
        premise_groups = []
    if not isinstance(premise_groups, list):
        raise ValueError("premise_groups must be a list when present")
    for index, group in enumerate(premise_groups):
        if not isinstance(group, dict):
            raise ValueError(f"premise_groups[{index}] must be object")
        target = group.get("target")
        if not isinstance(target, str) or target not in nodes:
            raise ValueError(f"premise_groups[{index}].target references missing node {target!r}")
        premises = group.get("premises")
        if not isinstance(premises, list) or len(premises) < 2:
            raise ValueError(f"premise_groups[{index}].premises must be a list of at least two node ids")
        premise_ids: list[str] = []
        for premise_index, premise_id in enumerate(premises):
            if not isinstance(premise_id, str) or not premise_id:
                raise ValueError(f"premise_groups[{index}].premises[{premise_index}] must be a non-empty string")
            if premise_id not in nodes:
                raise ValueError(f"premise_groups[{index}].premises[{premise_index}] references missing node {premise_id!r}")
            if premise_id == target:
                raise ValueError(f"premise_groups[{index}] must not include target {target!r} as a premise")
            if premise_id not in premise_source_sets.get(target, set()):
                raise ValueError(
                    f"premise_groups[{index}] premise {premise_id!r} must have a leads_to edge to target {target!r}"
                )
            premise_ids.append(premise_id)
        if len(set(premise_ids)) != len(premise_ids):
            raise ValueError(f"premise_groups[{index}].premises must not contain duplicates")
        overlap = grouped_premise_sources[target].intersection(premise_ids)
        if overlap:
            joined = ", ".join(sorted(overlap))
            raise ValueError(f"premise_groups for target {target!r} overlap on premise(s) {joined}")
        if "effective_truth_cost" in group:
            raise ValueError(
                f"premise_groups[{index}] must not set effective_truth_cost; it is computed from joint_probability"
            )
        if "joint_probability" not in group:
            raise ValueError(f"premise_groups[{index}] missing joint_probability")
        premise_group_costs[target].append(
            probability_cost(group["joint_probability"], f"premise_groups[{index}].joint_probability")
        )
        grouped_premise_sources[target].update(premise_ids)

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
        grouped_sources = grouped_premise_sources.get(node_id, set())
        ungrouped_source_cost = sum(
            effective_cost(source_id)
            for source_id in premise_sources.get(node_id, [])
            if source_id not in grouped_sources
        )
        # Premise groups are explicit non-independent bundles; their calibrated
        # joint_probability replaces member costs.
        premise_cost = sum(premise_group_costs.get(node_id, [])) + ungrouped_source_cost
        base_cost = local_cost + premise_cost
        lrs = likelihood_edges.get(node_id, [])
        if lrs:
            # Missing local/premise probability is not certainty; use neutral odds so LR can move belief.
            base_probability = NEUTRAL_UPDATE_PRIOR if base_cost == 0.0 and not node_has_probability(node) else probability_from_cost(base_cost)
            log_odds = log_odds_from_probability(base_probability)
            for edge in lrs:
                log_odds += math.log(likelihood_ratio_from_edge(edge))
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
