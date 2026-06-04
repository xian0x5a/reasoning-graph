"""Goal, candidate, and stop-policy helper predicates."""

from __future__ import annotations

import math
from typing import Any

from .costs import compute_costs, node_contradiction_penalties, node_truth_cost, probability_from_value
from .models import EPISTEMIC_GOAL_MARKERS, EXHAUSTION_STOP_MARKERS, GOAL_TEXT_CLUE_MARKERS, GOAL_TEXT_EXACT_ANSWER_MARKERS
from .state import by_id
from .utils import finite_float


def goal_accepts_answer_kind(goal: dict[str, Any], answer_kind: str) -> bool:
    goal_text = str(goal.get("text") or "").lower()
    clue_goal = any(marker in goal_text for marker in GOAL_TEXT_CLUE_MARKERS) and any(
        marker in goal_text for marker in ("identify", "find", "missing", "next", "path", "family")
    )
    exact_goal = any(marker in goal_text for marker in GOAL_TEXT_EXACT_ANSWER_MARKERS) and not (
        "without trying to recover" in goal_text or "not trying to recover" in goal_text
    )
    if any(marker in goal_text for marker in EPISTEMIC_GOAL_MARKERS):
        return answer_kind in {"blocker", "exact_answer", "exact_method", "method_hypothesis", "clue_path"}
    if clue_goal and not exact_goal:
        return answer_kind in {"clue_path", "method_hypothesis", "exact_method", "exact_answer"}
    if exact_goal:
        return answer_kind in {"exact_answer", "exact_method"}
    return answer_kind in {"exact_answer", "exact_method"}


def goal_ids(state: dict[str, Any]) -> set[str]:
    nodes = by_id(state.get("nodes", []), "node")
    return {node_id for node_id, node in nodes.items() if node.get("type") == "goal"}


def accepted_goal_ids(state: dict[str, Any]) -> set[str]:
    goals = goal_ids(state)
    policy = state.get("goal_policy") if isinstance(state.get("goal_policy"), dict) else {}
    configured = policy.get("accepted_goals")
    if isinstance(configured, list) and configured:
        return {str(goal_id) for goal_id in configured if str(goal_id) in goals}
    return goals


def preferred_goal_ids(state: dict[str, Any]) -> set[str]:
    goals = goal_ids(state)
    policy = state.get("goal_policy") if isinstance(state.get("goal_policy"), dict) else {}
    configured = policy.get("preferred_goals")
    if isinstance(configured, list) and configured:
        return {str(goal_id) for goal_id in configured if str(goal_id) in goals}
    return set()


def candidate_goal_targets(state: dict[str, Any]) -> dict[str, set[str]]:
    goals = goal_ids(state)
    nodes = by_id(state.get("nodes", []), "node")
    candidate_ids = {node_id for node_id, node in nodes.items() if node.get("type") == "candidate_solution"}
    targets: dict[str, set[str]] = {candidate_id: set() for candidate_id in candidate_ids}
    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        edge_type = edge.get("type") or edge.get("label")
        src = edge.get("from")
        dst = edge.get("to")
        if src in candidate_ids and dst in goals and edge_type == "answers":
            targets.setdefault(str(src), set()).add(str(dst))
    return targets


def candidate_goal_answer_ids(state: dict[str, Any]) -> set[str]:
    return {candidate_id for candidate_id, targets in candidate_goal_targets(state).items() if targets}


def epistemic_goal_ids(state: dict[str, Any]) -> set[str]:
    nodes = by_id(state.get("nodes", []), "node")
    return {
        node_id
        for node_id, node in nodes.items()
        if node.get("type") == "goal"
        and any(marker in str(node.get("text") or "").lower() for marker in EPISTEMIC_GOAL_MARKERS)
    }


def selected_candidate_ids_from_events(state: dict[str, Any]) -> set[str]:
    events = state.get("events")
    if not isinstance(events, list):
        return set()
    return {
        str(event.get("node"))
        for event in events
        if isinstance(event, dict)
        and event.get("action") in {"select", "solution"}
        and isinstance(event.get("node"), str)
    }


def selected_epistemic_candidate_ids(state: dict[str, Any]) -> set[str]:
    epistemic_goals = epistemic_goal_ids(state)
    if not epistemic_goals:
        return set()
    targets = candidate_goal_targets(state)
    return {
        candidate_id
        for candidate_id in selected_candidate_ids_from_events(state)
        if targets.get(candidate_id, set()) & epistemic_goals
    }


def candidate_pruned_ids(state: dict[str, Any]) -> set[str]:
    """Legacy compatibility: contradictions no longer disqualify candidate nodes."""

    return set()


def candidate_soft_contradiction_penalties(state: dict[str, Any]) -> dict[str, float]:
    nodes = by_id(state.get("nodes", []), "node")
    candidate_ids = {node_id for node_id, node in nodes.items() if node.get("type") == "candidate_solution"}
    node_penalties = node_contradiction_penalties(state)
    return {candidate_id: node_penalties.get(candidate_id, 0.0) for candidate_id in candidate_ids}


def viable_candidate_ids(state: dict[str, Any]) -> set[str]:
    accepted = accepted_goal_ids(state)
    targets = candidate_goal_targets(state)
    return {candidate_id for candidate_id, goal_targets in targets.items() if goal_targets & accepted}


def salient_clue_family_ids(state: dict[str, Any]) -> set[str]:
    nodes = by_id(state.get("nodes", []), "node")
    clue_ids: set[str] = set()
    for node_id, node in nodes.items():
        salience = probability_from_value(node.get("salience"))
        if node.get("clue_family") is True or node.get("role") == "clue_family" or (salience is not None and salience >= 0.7):
            clue_ids.add(node_id)
    return clue_ids


def candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, float, str]:
    try:
        truth_cost = float(candidate.get("effective_truth_cost", candidate.get("truth_cost")))
    except (TypeError, ValueError):
        truth_cost = math.inf
    try:
        search_cost = float(candidate.get("search_cost", candidate.get("path_cost")))
    except (TypeError, ValueError):
        search_cost = math.inf
    return (truth_cost, search_cost, str(candidate.get("id") or candidate.get("name") or ""))


def selected_candidate_frontier_items(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    selected: dict[str, dict[str, Any]] = {}
    events = state.get("events")
    if not isinstance(events, list):
        return selected
    for event in events:
        if not isinstance(event, dict) or event.get("action") not in {"select", "solution"}:
            continue
        candidate_id = event.get("node")
        item_id = event.get("item")
        if isinstance(candidate_id, str) and isinstance(item_id, str) and item_id in items:
            selected[candidate_id] = items[item_id]
    return selected


def sorted_report_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    compute_costs(state)
    report = state.get("report", {}) if isinstance(state.get("report"), dict) else {}
    candidates = report.get("candidates")
    if not isinstance(candidates, list):
        return []
    nodes = by_id(state.get("nodes", []), "node")
    graph_candidate_ids = viable_candidate_ids(state)
    selected_items = selected_candidate_frontier_items(state)
    # Report metadata can lag behind schema cleanup; render only live graph candidates.
    soft_penalties = candidate_soft_contradiction_penalties(state)
    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_id = str(candidate.get("id") or "")
        if candidate_id not in graph_candidate_ids:
            continue
        node = nodes.get(candidate_id, {})
        selected_item = selected_items.get(candidate_id, {})
        enriched = dict(candidate)
        search_cost = finite_float(enriched.get("search_cost"))
        if search_cost is None:
            search_cost = finite_float(enriched.get("path_cost"))
        if search_cost is None:
            search_cost = finite_float(selected_item.get("search_cost", selected_item.get("path_cost")))
        if search_cost is not None:
            enriched["search_cost"] = round(search_cost, 6)
        truth_cost = finite_float(enriched.get("truth_cost"))
        if truth_cost is None:
            truth_cost = finite_float(selected_item.get("truth_cost"))
        if truth_cost is None:
            truth_cost = node_truth_cost(node)
        penalty = soft_penalties.get(candidate_id, 0.0)
        if penalty:
            enriched["contradiction_penalty"] = round(penalty, 6)
        penalty_in_selected_path = bool(selected_item) and selected_item.get("node") == candidate_id
        effective_truth_cost = truth_cost if penalty_in_selected_path else truth_cost + penalty
        effective_belief = math.exp(-effective_truth_cost)
        enriched["truth_cost"] = round(truth_cost, 6)
        enriched["effective_truth_cost"] = round(effective_truth_cost, 6)
        if "posterior" in node:
            enriched["posterior"] = node["posterior"]
        enriched["belief"] = round(effective_belief, 6)
        filtered.append(enriched)

    total_belief = sum(float(candidate.get("belief", 0.0)) for candidate in filtered if finite_float(candidate.get("belief")) is not None)
    if total_belief > 0:
        for candidate in filtered:
            belief = finite_float(candidate.get("belief")) or 0.0
            candidate["weight"] = round(belief / total_belief, 6)
    return sorted(filtered, key=candidate_sort_key)


def strongest_candidate_belief(state: dict[str, Any]) -> float:
    beliefs = [finite_float(candidate.get("belief")) for candidate in sorted_report_candidates(state)]
    return max((belief for belief in beliefs if belief is not None), default=0.0)


def stop_reason_claims_exhaustion(reason: str) -> bool:
    normalized = reason.lower()
    negations = (
        "not exhaust",
        "not fully explored",
        "not complete",
        "not done",
        "unfinished",
        "budget reached",
        "budget exhausted",
        "time exhausted",
    )
    if any(negation in normalized for negation in negations):
        return False
    return any(marker in normalized for marker in EXHAUSTION_STOP_MARKERS)
