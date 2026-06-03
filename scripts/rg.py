#!/usr/bin/env python3
"""Reasoning graph helper.

No third-party dependencies. Operates on a JSON state file with nodes, edges,
and frontier. Designed for agent use: deterministic sorting, rough cost
computation, active-frontier driving, path reconstruction, and Mermaid/HTML output.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

NODE_TYPES = {
    "goal",
    "fact",
    "constraint",
    "derived",
    "assumption",
    "test",
    "contradiction",
    "candidate_solution",
}

EDGE_TYPES = {
    "requires",
    "supports",
    "assumes",
    "contradicts",
    "tests",
    "leads_to",
}

AUDIT_EVENT_ACTIONS = {
    "init",
    "pop",
    "expand",
    "select",
    "solution",  # legacy alias; new traces should use select
    "stop",
}

STOP_OUTCOMES = {
    "solved",
    "candidate_threshold_met",
    "candidate_count_met",
    "frontier_exhausted",
    "budget_exhausted",
    "blocked",
    "user_stopped",
    "inconclusive",
}

TEST_STATUSES = {
    "proposed",
    "performed",
    "inconclusive",
}

ANSWER_KINDS = {
    "exact_answer",
    "exact_method",
    "method_hypothesis",
    "clue_path",
    "blocker",
}

GOAL_TEXT_EXACT_ANSWER_MARKERS = (
    "exact",
    "plaintext",
    "recover",
    "solve",
    "answer",
)

GOAL_TEXT_CLUE_MARKERS = (
    "clue",
    "method",
    "intended path",
    "next path",
    "hypothesis",
)

EPISTEMIC_GOAL_MARKERS = (
    "unresolved",
    "blocker",
    "insufficient",
    "unknown",
    "not established",
    "cannot establish",
    "missing dependency",
)

EXHAUSTION_STOP_MARKERS = (
    "exhaust",
    "fully explored",
    "all branches",
    "all meaningful",
    "no more",
    "nothing left",
    "frontier empty",
    "frontier exhausted",
    "complete",
    "done",
)

SEARCH_COST_COMPONENTS = (
    "truth",
    "verification",
    "effort_budget",
    "reasoning_complexity",
    "constraint_tension",
)

LEGACY_COST_COMPONENT_ALIASES = {
    "uncertainty": "truth",
    "resource_budget": "effort_budget",
    "compute_budget": "effort_budget",
}

PROBE_LIKE_MARKERS = (
    "brute force",
    "bruteforce",
    "probe",
    "sweep",
    "enumerate",
    "try variants",
    "attempt variants",
    "batch test",
)

CLASS_BY_NODE_TYPE = {
    "goal": "goal",
    "fact": "fact",
    "constraint": "constraint",
    "derived": "derived",
    "assumption": "assumption",
    "test": "test",
    "contradiction": "bad",
    "candidate_solution": "candidate",
}


@dataclass
class ValidationResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def load_state(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def dump_state(state: dict[str, Any], path: str | None, in_place_source: str | None = None) -> None:
    text = json.dumps(state, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    target = path or (in_place_source if in_place_source != "-" else None)
    if target:
        Path(target).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)


def by_id(items: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(items):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        if item_id in result:
            # Keep first; validation reports duplicate.
            continue
        result[item_id] = item
    return result


def node_label(node: dict[str, Any]) -> str:
    parts = [str(node.get("type", "node"))]
    text = str(node.get("text", node.get("id", ""))).strip()
    if text:
        parts.append(text)
    if node.get("type") == "assumption" and "prior" in node:
        parts.append(f"prior {float(node['prior']):.2f}")
    if "posterior" in node:
        parts.append(f"posterior {float(node['posterior']):.2f}")
    return ": ".join(parts[:2]) + (f"\n{parts[2]}" if len(parts) > 2 else "")


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

    `prior` is for assumptions/candidates. `confidence` is for facts,
    derived claims, contradictions, and noisy test observations. Missing
    confidence on accepted facts/tests means "no truth penalty", not certainty
    proof; users can add confidence when source reliability matters.
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


def next_event_step(state: dict[str, Any]) -> int:
    events = state.get("events")
    if not isinstance(events, list):
        return 1
    steps = [event.get("step") for event in events if isinstance(event, dict) and isinstance(event.get("step"), int)]
    return max(steps, default=0) + 1


def search_cursor(state: dict[str, Any]) -> dict[str, Any]:
    """Derive the active virtual frontier from compact events.

    If no strict events exist yet, every frontier item is considered active so
    older/loose states remain usable with `frontier` and `next`.
    """

    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    events = state.get("events")
    if not isinstance(events, list) or not events:
        return {
            "active_ids": {item_id for item_id in items},
            "pending_item": None,
            "initialized": False,
            "stopped": False,
        }

    active_ids: set[str] = set()
    popped_ids: set[str] = set()
    pending_item: str | None = None
    initialized = False
    stopped = False

    for event in events:
        if not isinstance(event, dict):
            continue
        action = event.get("action")
        if action == "init":
            init_frontier = event.get("frontier") if isinstance(event.get("frontier"), list) else []
            for item_id in init_frontier:
                if isinstance(item_id, str) and item_id in items and item_id not in popped_ids:
                    active_ids.add(item_id)
            initialized = True
        elif action == "pop":
            item_id = event.get("item")
            if isinstance(item_id, str) and item_id in items:
                active_ids.discard(item_id)
                popped_ids.add(item_id)
                pending_item = item_id
        elif action == "expand":
            item_id = event.get("item")
            if item_id == pending_item:
                pending_item = None
            added_frontier = event.get("add_frontier") if isinstance(event.get("add_frontier"), list) else []
            for child_id in added_frontier:
                if isinstance(child_id, str) and child_id in items and child_id not in popped_ids:
                    active_ids.add(child_id)
        elif action in {"select", "solution"}:
            item_id = event.get("item")
            if item_id == pending_item:
                pending_item = None
        elif action == "stop":
            stopped = True
            pending_item = None
            active_ids.clear()

    if not initialized:
        active_ids = {item_id for item_id in items}

    return {
        "active_ids": active_ids,
        "pending_item": pending_item,
        "initialized": initialized,
        "stopped": stopped,
    }


def related_brief(item: dict[str, Any]) -> str:
    related = item.get("related")
    if not isinstance(related, list) or not related:
        return ""
    return ",".join(str(node_id) for node_id in related[:8])


def scratch_brief(item: dict[str, Any]) -> str:
    scratch = item.get("scratch")
    if not isinstance(scratch, list) or not scratch:
        return ""
    return "; ".join(str(note) for note in scratch[:2])


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


def item_view(state: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    nodes = by_id(state.get("nodes", []), "node")
    node = nodes.get(str(item.get("node")), {})
    return {
        "id": item.get("id"),
        "node": item.get("node"),
        "node_type": node.get("type"),
        "search_cost": item.get("search_cost", item.get("path_cost")),
        "path_cost": item.get("path_cost"),
        "truth_cost": item.get("truth_cost"),
        "step_cost": item.get("step_cost"),
        "step_truth_cost": item.get("step_truth_cost"),
        "parent": item.get("parent"),
        "active_assumptions": item.get("active_assumptions", []),
        "related": item.get("related", []),
        "related_brief": related_brief(item),
        "scratch": item.get("scratch", []),
        "scratch_brief": scratch_brief(item),
        "text": node.get("text", ""),
    }


def validate_state(state: dict[str, Any]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    nodes_raw = state.get("nodes", [])
    edges_raw = state.get("edges", [])
    frontier_raw = state.get("frontier", [])
    solutions_raw = state.get("solutions", [])

    if not isinstance(nodes_raw, list):
        errors.append("nodes must be a list")
        nodes_raw = []
    if not isinstance(edges_raw, list):
        errors.append("edges must be a list")
        edges_raw = []
    if not isinstance(frontier_raw, list):
        errors.append("frontier must be a list")
        frontier_raw = []
    if not isinstance(solutions_raw, list):
        errors.append("solutions must be a list")
        solutions_raw = []
    elif solutions_raw:
        warnings.append("solutions list is deprecated; use candidate_solution nodes with leads_to edges to the goal")

    node_ids: set[str] = set()
    for i, node in enumerate(nodes_raw):
        if not isinstance(node, dict):
            errors.append(f"nodes[{i}] must be object")
            continue
        node_id = node.get("id")
        node_type = node.get("type")
        if not isinstance(node_id, str) or not node_id:
            errors.append(f"nodes[{i}] missing string id")
        elif node_id in node_ids:
            errors.append(f"duplicate node id {node_id}")
        else:
            node_ids.add(node_id)
        if node_type not in NODE_TYPES:
            errors.append(f"node {node_id or i} invalid type {node_type!r}")
        if node_type == "assumption":
            if "prior" not in node:
                warnings.append(f"assumption {node_id} missing prior")
            else:
                try:
                    uncertainty_cost_from_prior(node["prior"])
                except ValueError as exc:
                    errors.append(f"assumption {node_id}: {exc}")
        for probability_field in ("confidence", "probability", "posterior"):
            if probability_field in node:
                try:
                    probability_cost(node[probability_field], probability_field)
                except ValueError as exc:
                    errors.append(f"node {node_id or i}: {exc}")
        if "clue_family" in node and not isinstance(node.get("clue_family"), bool):
            errors.append(f"node {node_id or i} clue_family must be boolean when present")
        if "salience" in node:
            try:
                salience = float(node.get("salience"))
                if not 0 <= salience <= 1:
                    errors.append(f"node {node_id or i} salience must be in [0, 1]")
            except (TypeError, ValueError):
                errors.append(f"node {node_id or i} salience must be numeric when present")
        if "exhausted" in node and not isinstance(node.get("exhausted"), bool):
            errors.append(f"node {node_id or i} exhausted must be boolean when present")
        if node.get("exhausted") is True and not str(node.get("exhaustion_reason") or "").strip():
            warnings.append(f"node {node_id or i} exhausted=true should include exhaustion_reason")
        if "status" in node and node_type != "test":
            errors.append(f"node {node_id or i} has status but only test nodes may use status")
        if node_type == "test":
            status = node.get("status")
            if status is None:
                warnings.append(f"test {node_id} missing status; use proposed/performed/inconclusive")
            elif str(status) not in TEST_STATUSES:
                warnings.append(f"test {node_id} has non-standard status {status!r}")

    nodes_by_id = {str(node.get("id")): node for node in nodes_raw if isinstance(node, dict) and isinstance(node.get("id"), str)}
    goal_ids = {node.get("id") for node in nodes_raw if isinstance(node, dict) and node.get("type") == "goal"}
    goal_groups = state.get("goal_groups", [])
    if goal_groups is not None:
        if not isinstance(goal_groups, list):
            errors.append("goal_groups must be a list when present")
            goal_groups = []
        seen_goal_groups: set[str] = set()
        for i, group in enumerate(goal_groups):
            if not isinstance(group, dict):
                errors.append(f"goal_groups[{i}] must be object")
                continue
            group_id = group.get("id")
            if not isinstance(group_id, str) or not group_id:
                errors.append(f"goal_groups[{i}] missing string id")
            elif group_id in seen_goal_groups:
                errors.append(f"duplicate goal group id {group_id}")
            else:
                seen_goal_groups.add(group_id)
            if "exclusive" in group and not isinstance(group.get("exclusive"), bool):
                errors.append(f"goal_groups[{i}].exclusive must be boolean when present")
            group_goals = group.get("goals")
            if not isinstance(group_goals, list) or not group_goals:
                errors.append(f"goal_groups[{i}].goals must be a non-empty list")
            else:
                for j, goal_id in enumerate(group_goals):
                    if goal_id not in goal_ids:
                        errors.append(f"goal_groups[{i}].goals[{j}] references missing goal {goal_id!r}")
    goal_policy = state.get("goal_policy", {})
    if goal_policy is not None:
        if not isinstance(goal_policy, dict):
            errors.append("goal_policy must be object when present")
            goal_policy = {}
        for key in ("accepted_goals", "preferred_goals"):
            if key in goal_policy:
                values = goal_policy.get(key)
                if not isinstance(values, list) or not values:
                    errors.append(f"goal_policy.{key} must be a non-empty list when present")
                    continue
                for i, goal_id in enumerate(values):
                    if goal_id not in goal_ids:
                        errors.append(f"goal_policy.{key}[{i}] references missing goal {goal_id!r}")
    stop_policy = state.get("stop_policy", {})
    if stop_policy is not None:
        if not isinstance(stop_policy, dict):
            errors.append("stop_policy must be object when present")
            stop_policy = {}
        for key in ("min_viable_candidates", "max_live_frontier_items"):
            if key in stop_policy:
                value = stop_policy.get(key)
                if not isinstance(value, int) or value < 0:
                    errors.append(f"stop_policy.{key} must be a non-negative integer")
        if "belief_threshold" in stop_policy:
            probability = probability_from_value(stop_policy.get("belief_threshold"))
            if probability is None or probability <= 0:
                errors.append("stop_policy.belief_threshold must be in (0, 1]")
        for key in ("require_frontier_exhausted_for_epistemic_stop",):
            if key in stop_policy and not isinstance(stop_policy.get(key), bool):
                errors.append(f"stop_policy.{key} must be boolean when present")
        if "severity" in stop_policy and stop_policy.get("severity") not in {"warning", "error"}:
            errors.append("stop_policy.severity must be 'warning' or 'error' when present")
    branch_policy = state.get("branch_policy", {})
    if branch_policy is not None:
        if not isinstance(branch_policy, dict):
            errors.append("branch_policy must be object when present")
            branch_policy = {}
        for key in ("high_salience_min_children",):
            if key in branch_policy:
                value = branch_policy.get(key)
                if not isinstance(value, int) or value < 0:
                    errors.append(f"branch_policy.{key} must be a non-negative integer")
        if "low_prior_wildcard_required" in branch_policy and not isinstance(branch_policy.get("low_prior_wildcard_required"), bool):
            errors.append("branch_policy.low_prior_wildcard_required must be boolean when present")
        if "severity" in branch_policy and branch_policy.get("severity") not in {"warning", "error"}:
            errors.append("branch_policy.severity must be 'warning' or 'error' when present")
        if "enforce_on" in branch_policy and branch_policy.get("enforce_on") not in {"exhaustion_stop", "always"}:
            errors.append("branch_policy.enforce_on must be 'exhaustion_stop' or 'always' when present")
    accepted_goal_values = goal_policy.get("accepted_goals") if isinstance(goal_policy, dict) else None
    accepted_goal_ids = {str(goal_id) for goal_id in accepted_goal_values} if isinstance(accepted_goal_values, list) else set(goal_ids)
    goals_by_id = {node.get("id"): node for node in nodes_raw if isinstance(node, dict) and node.get("type") == "goal"}
    candidate_nodes = [node for node in nodes_raw if isinstance(node, dict) and node.get("type") == "candidate_solution"]
    candidate_ids = {node.get("id") for node in candidate_nodes}
    candidate_goal_edges: set[str] = set()
    candidate_accepted_goal_edges: set[str] = set()
    candidate_goal_targets: dict[str, set[str]] = {}
    for i, edge in enumerate(edges_raw):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}] must be object")
            continue
        src = edge.get("from")
        dst = edge.get("to")
        edge_type = edge.get("type") or edge.get("label")
        if src not in node_ids:
            errors.append(f"edge {i} references missing from node {src!r}")
        if dst not in node_ids:
            errors.append(f"edge {i} references missing to node {dst!r}")
        if edge_type not in EDGE_TYPES:
            errors.append(f"edge {i} invalid type {edge_type!r}")
        if "hard" in edge and not isinstance(edge.get("hard"), bool):
            errors.append(f"edge {i} hard must be boolean when present")
        if "mode" in edge and edge.get("mode") not in {"hard", "soft"}:
            errors.append(f"edge {i} mode must be 'hard' or 'soft' when present")
        if "strength" in edge:
            try:
                strength = float(edge.get("strength"))
                if not 0 <= strength <= 1:
                    errors.append(f"edge {i} strength must be in [0, 1]")
            except (TypeError, ValueError):
                errors.append(f"edge {i} strength must be numeric when present")
        src_type = next((node.get("type") for node in nodes_raw if isinstance(node, dict) and node.get("id") == src), None)
        dst_type = next((node.get("type") for node in nodes_raw if isinstance(node, dict) and node.get("id") == dst), None)
        if src in candidate_ids and dst in goal_ids and edge_type == "leads_to":
            candidate_goal_edges.add(src)
            candidate_goal_targets.setdefault(str(src), set()).add(str(dst))
            if dst in accepted_goal_ids:
                candidate_accepted_goal_edges.add(src)
        if src in candidate_ids and dst in goal_ids and edge_type == "contradicts":
            errors.append(
                f"edge {i} uses candidate_solution -> goal contradicts; connect candidates to goals only with leads_to, and down-rank candidates with evidence -> candidate contradicts"
            )
        if src_type == "assumption" and dst_type == "goal":
            errors.append(
                f"edge {i} connects assumption {src} directly to goal {dst}; route assumptions through tests/derived/candidate nodes instead"
            )
        if src_type == "constraint" and dst_type == "goal" and edge_type == "requires":
            errors.append(
                f"edge {i} has constraint {src} requires goal {dst}; reverse direction to goal requires constraint"
            )
    unresolved_markers = ("not solved", "not established", "cannot establish", "insufficient evidence", "missing dependency", "undetermined", "not recoverable")
    epistemic_goal_markers = EPISTEMIC_GOAL_MARKERS
    strict_answer_kind_required = isinstance(stop_policy, dict) and stop_policy.get("severity") == "error"
    for candidate in candidate_nodes:
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str):
            continue
        candidate_text = str(candidate.get("text") or "").lower()
        answer_kind = candidate.get("answer_kind")
        if answer_kind is None:
            message = f"candidate_solution {candidate_id} missing answer_kind; use one of {sorted(ANSWER_KINDS)}"
            if strict_answer_kind_required:
                errors.append(message)
            else:
                warnings.append(message)
        elif answer_kind not in ANSWER_KINDS:
            errors.append(f"candidate_solution {candidate_id} answer_kind must be one of {sorted(ANSWER_KINDS)}, got {answer_kind!r}")
        goal_texts = [str(goals_by_id.get(goal_id, {}).get("text") or "").lower() for goal_id in candidate_goal_targets.get(candidate_id, set())]
        has_explicit_epistemic_goal = any(
            any(marker in goal_text for marker in epistemic_goal_markers)
            for goal_text in goal_texts
        )
        if any(marker in candidate_text for marker in unresolved_markers) and not has_explicit_epistemic_goal:
            warnings.append(
                f"candidate_solution {candidate_id} looks like an unresolved/stop outcome, not an answer candidate; use a derived blocker plus stop event unless the goal is explicitly epistemic"
            )
        if answer_kind in ANSWER_KINDS:
            for goal_id in candidate_goal_targets.get(candidate_id, set()):
                goal = goals_by_id.get(goal_id, {})
                if goal_id in accepted_goal_ids and not goal_accepts_answer_kind(goal, str(answer_kind)):
                    errors.append(
                        f"candidate_solution {candidate_id} answer_kind {answer_kind!r} does not answer accepted goal {goal_id!r}: {goal.get('text')!r}"
                    )
    for candidate_id in sorted(str(node_id) for node_id in candidate_ids if isinstance(node_id, str)):
        if candidate_id not in candidate_goal_edges:
            errors.append(f"candidate_solution {candidate_id} must connect to a goal with a leads_to edge")
        elif isinstance(accepted_goal_values, list) and candidate_id not in candidate_accepted_goal_edges:
            errors.append(f"candidate_solution {candidate_id} must connect to an accepted goal with a leads_to edge")

    frontier_ids: set[str] = set()
    for i, item in enumerate(frontier_raw):
        if not isinstance(item, dict):
            errors.append(f"frontier[{i}] must be object")
            continue
        item_id = item.get("id")
        node = item.get("node")
        parent = item.get("parent")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"frontier[{i}] missing string id")
        elif item_id in frontier_ids:
            errors.append(f"duplicate frontier id {item_id}")
        else:
            frontier_ids.add(item_id)
        if node not in node_ids:
            errors.append(f"frontier item {item_id or i} references missing node {node!r}")
        if parent is not None and parent != "" and parent not in frontier_ids:
            # Parent may appear later; check all ids after collection below.
            pass
        for forbidden_field in ("next_action", "expansion_hint", "context", "additional_info", "focus"):
            if forbidden_field in item:
                errors.append(f"frontier item {item_id or i} uses forbidden field {forbidden_field}; use node plus related node ids only")
        related = item.get("related", [])
        if "related" in item:
            if not isinstance(related, list):
                errors.append(f"frontier item {item_id or i} related must be a list of node ids")
            else:
                for related_index, related_node in enumerate(related):
                    if related_node not in node_ids:
                        errors.append(f"frontier item {item_id or i} related[{related_index}] references missing node {related_node!r}")
        scratch = item.get("scratch", [])
        if "scratch" in item:
            if not isinstance(scratch, list):
                errors.append(f"frontier item {item_id or i} scratch must be a list of strings")
            else:
                for scratch_index, note in enumerate(scratch):
                    if not isinstance(note, str) or not note.strip():
                        errors.append(f"frontier item {item_id or i} scratch[{scratch_index}] must be a non-empty string")
        node_obj = nodes_by_id.get(str(node), {}) if isinstance(node, str) else {}
        scratch_text = " ".join(note for note in scratch if isinstance(note, str)) if isinstance(scratch, list) else ""
        if text_looks_probe_like(node_obj.get("text"), item.get("summary"), scratch_text) and not item_has_explicit_effort_budget(item):
            warnings.append(
                f"frontier item {item_id or i} looks probe/brute-force-like; add cost_components.effort_budget and budget metadata so UCS prices bounded effort"
            )

    all_frontier_ids = {item.get("id") for item in frontier_raw if isinstance(item, dict)}
    for item in frontier_raw:
        if not isinstance(item, dict):
            continue
        parent = item.get("parent")
        if parent is not None and parent != "" and parent not in all_frontier_ids:
            errors.append(f"frontier item {item.get('id')} references missing parent {parent!r}")

    solution_node_ids = {s.get("node") if isinstance(s, dict) else s for s in solutions_raw}
    for node_id in solution_node_ids:
        if node_id not in node_ids:
            errors.append(f"solutions references missing node {node_id!r}")
        elif node_id not in candidate_ids:
            errors.append(f"solutions references non-candidate node {node_id!r}; selected answers must be candidate_solution nodes")

    try:
        compute_costs(json.loads(json.dumps(state)))
    except Exception as exc:  # validation should report instead of throwing
        errors.append(f"cost computation failed: {exc}")

    return ValidationResult(errors=errors, warnings=warnings)


def as_string_list(value: Any, field: str, errors: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return []
    result: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item:
            errors.append(f"{field}[{i}] must be a non-empty string")
            continue
        result.append(item)
    return result


def edge_id_set(state: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for edge in state.get("edges", []):
        if isinstance(edge, dict) and isinstance(edge.get("id"), str) and edge.get("id"):
            ids.add(edge["id"])
    return ids


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
    if source.get("type") in {"fact", "constraint", "contradiction"}:
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
        if src in candidate_ids and dst in goals and edge_type == "leads_to":
            targets.setdefault(str(src), set()).add(str(dst))
    return targets


def candidate_goal_leads_to_ids(state: dict[str, Any]) -> set[str]:
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


def strongest_candidate_belief(state: dict[str, Any]) -> float:
    beliefs = [finite_float(candidate.get("belief")) for candidate in sorted_report_candidates(state)]
    return max((belief for belief in beliefs if belief is not None), default=0.0)


def add_policy_violation(result: ValidationResult, message: str, severity: str) -> None:
    if severity == "error":
        result.errors.append(message)
    else:
        result.warnings.append(message)


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


def add_stop_policy_violation(result: ValidationResult, message: str, severity: str) -> None:
    add_policy_violation(result, message, severity)


def audit_stop_policy(
    state: dict[str, Any],
    live_frontier_items: list[dict[str, Any]],
    viable_count: int,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    result = ValidationResult(errors=errors, warnings=warnings)
    policy = state.get("stop_policy") if isinstance(state.get("stop_policy"), dict) else {}
    severity = str(policy.get("severity") or "warning")
    if severity not in {"warning", "error"}:
        severity = "warning"

    live_count = len(live_frontier_items)
    selected_epistemic = selected_epistemic_candidate_ids(state)
    if selected_epistemic and live_count:
        add_stop_policy_violation(
            result,
            "epistemic/unresolved candidate selected while event-reachable frontier remains live: "
            + ", ".join(item.get("id", "?") for item in live_frontier_items[:8])
            + ("..." if live_count > 8 else ""),
            severity,
        )

    if not policy:
        return result

    max_live = int(policy.get("max_live_frontier_items", 0))
    if live_count <= max_live:
        return result

    min_candidates = int(policy.get("min_viable_candidates", 0))
    threshold = probability_from_value(policy.get("belief_threshold")) or 0.0
    strongest_belief = strongest_candidate_belief(state)
    enough_candidates = min_candidates > 0 and viable_count >= min_candidates
    confident_candidate = threshold > 0 and strongest_belief >= threshold
    if not enough_candidates and not confident_candidate:
        add_stop_policy_violation(
            result,
            "stop_policy not satisfied: live_frontier={live} > max_live_frontier_items={max_live}, "
            "viable_candidates={viable} < min_viable_candidates={min_candidates}, "
            "strongest_belief={belief:.6g} < belief_threshold={threshold:.6g}".format(
                live=live_count,
                max_live=max_live,
                viable=viable_count,
                min_candidates=min_candidates,
                belief=strongest_belief,
                threshold=threshold,
            ),
            severity,
        )
    if policy.get("require_frontier_exhausted_for_epistemic_stop") is True and selected_epistemic:
        add_stop_policy_violation(
            result,
            "stop_policy requires frontier exhaustion for epistemic stop, but live frontier remains: "
            + ", ".join(item.get("id", "?") for item in live_frontier_items[:8])
            + ("..." if live_count > 8 else ""),
            severity,
        )
    return result


def audit_state(state: dict[str, Any]) -> tuple[ValidationResult, dict[str, int]]:
    """Audit compact strict-search events against graph/frontier state.

    This does not prove the model thought in UCS order, but it catches incoherent
    or purely decorative search traces: wrong pop order, orphan children, missing
    candidate-selection events, or frontier items that appear without an expansion.
    """

    base = validate_state(state)
    errors = list(base.errors)
    warnings = list(base.warnings)
    stats = {"events": 0, "pops": 0, "expansions": 0, "selections": 0}

    events = state.get("events")
    if not isinstance(events, list) or not events:
        errors.append("events must be a non-empty list for strict search audit")
        return ValidationResult(errors=errors, warnings=warnings), stats

    compute_costs(state)
    nodes = by_id(state.get("nodes", []), "node")
    items = by_id(state.get("frontier", []), "frontier item")
    edges = [edge for edge in state.get("edges", []) if isinstance(edge, dict)]
    edges_by_id = {edge.get("id"): edge for edge in edges if isinstance(edge.get("id"), str) and edge.get("id")}
    edge_ids = set(edges_by_id)
    frontier_ids_by_node: dict[str, set[str]] = {}
    for frontier_id, item in items.items():
        node_id = item.get("node")
        if isinstance(node_id, str):
            frontier_ids_by_node.setdefault(node_id, set()).add(frontier_id)
    tolerance = 1e-6

    seen_init = False
    seen_stop = False
    previous_step: int | None = None
    virtual_frontier: set[str] = set()
    popped_items: set[str] = set()
    expanded_items: set[str] = set()
    last_popped_item: str | None = None
    last_pop_cost: float | None = None
    last_evidence_version: Any = None
    event_added_nodes: set[str] = set()
    event_selected_nodes: set[str] = set()
    contradiction_added_steps_by_node: dict[str, list[int]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        try:
            event_step = int(event.get("step"))
        except (TypeError, ValueError):
            continue
        for edge_id in event.get("add_edges") if isinstance(event.get("add_edges"), list) else []:
            edge = edges_by_id.get(str(edge_id))
            if not edge or (edge.get("type") or edge.get("label")) != "contradicts":
                continue
            target = edge.get("to")
            if isinstance(target, str):
                contradiction_added_steps_by_node.setdefault(target, []).append(event_step)

    branch_policy = state.get("branch_policy") if isinstance(state.get("branch_policy"), dict) else {}
    high_salience_min_children = int(branch_policy.get("high_salience_min_children", 3))
    branch_policy_severity = str(branch_policy.get("severity") or "warning")
    if branch_policy_severity not in {"warning", "error"}:
        branch_policy_severity = "warning"
    branch_policy_enforce_on = str(branch_policy.get("enforce_on") or "exhaustion_stop")
    if branch_policy_enforce_on not in {"exhaustion_stop", "always"}:
        branch_policy_enforce_on = "exhaustion_stop"
    deferred_branch_warnings: list[str] = []
    stop_reasons: list[str] = []
    stop_outcomes: list[str] = []

    def event_label(index: int, event: dict[str, Any]) -> str:
        return f"events[{index}] step={event.get('step')} action={event.get('action')}"

    def item_cost_changed_after(item_id: str, step: int) -> bool:
        item = items.get(item_id, {})
        node_id = item.get("node")
        if not isinstance(node_id, str):
            return False
        return any(change_step > step for change_step in contradiction_added_steps_by_node.get(node_id, []))

    for index, raw_event in enumerate(events):
        stats["events"] += 1
        if not isinstance(raw_event, dict):
            errors.append(f"events[{index}] must be object")
            continue
        event = raw_event
        label = event_label(index, event)

        step = event.get("step")
        if not isinstance(step, int):
            errors.append(f"{label}: step must be an integer")
        elif previous_step is not None and step <= previous_step:
            errors.append(f"{label}: step must strictly increase")
        if isinstance(step, int):
            previous_step = step

        action = event.get("action")
        if action not in AUDIT_EVENT_ACTIONS:
            errors.append(f"{label}: invalid action {action!r}")
            continue
        if seen_stop and action != "stop":
            errors.append(f"{label}: no events allowed after stop")

        if action == "init":
            if seen_init:
                errors.append(f"{label}: duplicate init event")
            init_frontier = as_string_list(event.get("frontier"), f"{label}.frontier", errors)
            for item_id in init_frontier:
                if item_id not in items:
                    errors.append(f"{label}: init references missing frontier item {item_id}")
                elif item_id in virtual_frontier:
                    errors.append(f"{label}: duplicate init frontier item {item_id}")
                else:
                    virtual_frontier.add(item_id)
            seen_init = True
            continue

        if not seen_init:
            errors.append(f"{label}: init event must appear before {action}")
            continue

        if action == "pop":
            item_id = event.get("item")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{label}: item must be a non-empty string")
                continue
            if item_id not in items:
                errors.append(f"{label}: references missing frontier item {item_id}")
                continue
            if item_id not in virtual_frontier:
                errors.append(f"{label}: item {item_id} is not in current virtual frontier")

            item = items[item_id]
            expected_cost = float(item.get("search_cost", item.get("path_cost", math.inf)))
            try:
                event_cost = float(event.get("cost"))
            except (TypeError, ValueError):
                errors.append(f"{label}: cost must be numeric")
                event_cost = expected_cost
            current_step = step if isinstance(step, int) else -1
            popped_cost_changed_later = item_cost_changed_after(item_id, current_step)
            if abs(event_cost - expected_cost) > tolerance and not popped_cost_changed_later:
                errors.append(f"{label}: cost {event_cost} != item search_cost {expected_cost}")

            if virtual_frontier:
                frontier_costs_changed_later = any(item_cost_changed_after(q, current_step) for q in virtual_frontier if q in items)
                lowest_cost = min(float(items[q].get("search_cost", items[q].get("path_cost", math.inf))) for q in virtual_frontier if q in items)
                if expected_cost > lowest_cost + tolerance and not frontier_costs_changed_later:
                    lowest_items = sorted(q for q in virtual_frontier if q in items and abs(float(items[q].get("search_cost", items[q].get("path_cost", math.inf))) - lowest_cost) <= tolerance)
                    errors.append(f"{label}: popped {item_id} cost {expected_cost} but lowest frontier search_cost is {lowest_cost} at {lowest_items[:3]}")

            evidence_version = event.get("evidence_version", item.get("evidence_version", state.get("evidence_version")))
            if last_pop_cost is not None and evidence_version == last_evidence_version and event_cost + tolerance < last_pop_cost:
                errors.append(f"{label}: pop cost decreased from {last_pop_cost} to {event_cost} without evidence_version change")
            last_pop_cost = event_cost
            last_evidence_version = evidence_version

            virtual_frontier.discard(item_id)
            popped_items.add(item_id)
            last_popped_item = item_id
            stats["pops"] += 1
            continue

        if action == "expand":
            item_id = event.get("item")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{label}: item must be a non-empty string")
                continue
            if item_id not in items:
                errors.append(f"{label}: references missing frontier item {item_id}")
                continue
            if item_id != last_popped_item:
                errors.append(f"{label}: expand must follow most recent pop ({last_popped_item}), got {item_id}")
            if item_id not in popped_items:
                errors.append(f"{label}: cannot expand unpopped item {item_id}")

            added_node_ids = as_string_list(event.get("add_nodes"), f"{label}.add_nodes", errors)
            added_node_types: set[str] = set()
            for node_id in added_node_ids:
                if node_id not in nodes:
                    errors.append(f"{label}: add_nodes references missing node {node_id}")
                else:
                    event_added_nodes.add(node_id)
                    node_type = nodes[node_id].get("type")
                    if isinstance(node_type, str):
                        added_node_types.add(node_type)
            added_edge_ids = as_string_list(event.get("add_edges"), f"{label}.add_edges", errors)
            for edge_id in added_edge_ids:
                if edge_ids and edge_id not in edge_ids:
                    errors.append(f"{label}: add_edges references missing edge id {edge_id}")
                elif not edge_ids:
                    warnings.append(f"{label}: add_edges cannot be cross-checked because edges have no ids")
            item_node_id = str(items[item_id].get("node") or "")
            added_node_set = set(added_node_ids)
            added_edges = [edges_by_id[edge_id] for edge_id in added_edge_ids if edge_id in edges_by_id]
            if item_node_id and added_node_set:
                has_outgoing_expansion_edge = any(
                    edge.get("from") == item_node_id and edge.get("to") in added_node_set
                    for edge in added_edges
                )
                if not has_outgoing_expansion_edge:
                    warnings.append(
                        f"{label}: expanded node {item_node_id} has no outgoing edge to added nodes; graph may hide that this assumption was explored"
                    )
            added_frontier_ids = as_string_list(event.get("add_frontier"), f"{label}.add_frontier", errors)
            for child_id in added_frontier_ids:
                child = items.get(child_id)
                if child is None:
                    errors.append(f"{label}: add_frontier references missing frontier item {child_id}")
                    continue
                if child_id in popped_items:
                    errors.append(f"{label}: add_frontier item {child_id} was already popped")
                    continue
                parent_id = child.get("parent")
                if parent_id is None or parent_id == "":
                    warnings.append(f"{label}: added frontier item {child_id} has no parent")
                elif parent_id != item_id:
                    warnings.append(f"{label}: added frontier item {child_id} parent is {parent_id}, expected {item_id}")
                virtual_frontier.add(child_id)

            contradiction_targets = {
                str(edge.get("to"))
                for edge in added_edges
                if (edge.get("type") or edge.get("label")) == "contradicts" and isinstance(edge.get("to"), str)
            }
            added_frontier_nodes = {
                str(items[child_id].get("node"))
                for child_id in added_frontier_ids
                if child_id in items and isinstance(items[child_id].get("node"), str)
            }
            no_reopen_reason = str(event.get("no_reopen_reason") or event.get("exhaustion_reason") or "").strip()
            updated_node_specs = event.get("updated_nodes", [])
            if updated_node_specs is None:
                updated_node_specs = []
            if not isinstance(updated_node_specs, list):
                errors.append(f"{label}.updated_nodes must be a list when present")
                updated_node_specs = []
            updated_node_ids: set[str] = set()
            for update_index, update_spec in enumerate(updated_node_specs):
                if isinstance(update_spec, str):
                    update_node_id = update_spec
                elif isinstance(update_spec, dict) and isinstance(update_spec.get("id"), str):
                    update_node_id = str(update_spec["id"])
                    fields = update_spec.get("fields")
                    if fields is not None and (not isinstance(fields, list) or not all(isinstance(field, str) for field in fields)):
                        errors.append(f"{label}.updated_nodes[{update_index}].fields must be a list of strings when present")
                else:
                    errors.append(f"{label}.updated_nodes[{update_index}] must be a node id string or object with id")
                    continue
                if update_node_id not in nodes:
                    errors.append(f"{label}.updated_nodes[{update_index}] references missing node {update_node_id}")
                updated_node_ids.add(update_node_id)
            reranked_visited_nodes = contradiction_targets | updated_node_ids
            for target_node_id in sorted(reranked_visited_nodes):
                target_frontier_ids = frontier_ids_by_node.get(target_node_id, set())
                if not target_frontier_ids:
                    continue
                popped_target_items = target_frontier_ids & popped_items
                if popped_target_items and target_node_id not in added_frontier_nodes and not no_reopen_reason:
                    warnings.append(
                        f"{label}: evidence updated visited node {target_node_id}; costs will recompute, but add frontier for new work or record no_reopen_reason/exhaustion_reason"
                    )

            terminal_or_contradicted = bool(added_node_types & {"contradiction", "candidate_solution"})
            item_node = nodes.get(item_node_id, {})
            has_under_branching_escape = bool(str(event.get("under_branching_reason") or "").strip())
            existing_siblings = as_string_list(event.get("existing_sibling_frontier"), f"{label}.existing_sibling_frontier", errors)
            for sibling_id in existing_siblings:
                if sibling_id not in items:
                    errors.append(f"{label}: existing_sibling_frontier references missing frontier item {sibling_id}")
            has_under_branching_escape = has_under_branching_escape or bool(existing_siblings)
            has_under_branching_escape = has_under_branching_escape or bool(
                item_node.get("exhausted") is True and str(item_node.get("exhaustion_reason") or "").strip()
            )
            if len(added_frontier_ids) == 1 and not terminal_or_contradicted and not has_under_branching_escape:
                deferred_branch_warnings.append(
                    f"{label}: one-child expansion may be under-branching; consider coarse sibling branches if any are meaningful"
                )
            is_high_salience = item_node_id in salient_clue_family_ids(state) or (
                (probability_from_value(item_node.get("salience")) or 0.0) >= 0.7
            )
            if is_high_salience and len(added_frontier_ids) < high_salience_min_children and not has_under_branching_escape:
                branch_result = ValidationResult(errors=[], warnings=[])
                add_policy_violation(
                    branch_result,
                    f"{label}: high-salience expansion added {len(added_frontier_ids)} child frontier item(s), below branch_policy.high_salience_min_children={high_salience_min_children}; add meaningful siblings, under_branching_reason, existing_sibling_frontier, or exhaustion_reason",
                    branch_policy_severity,
                )
                errors.extend(branch_result.errors)
                deferred_branch_warnings.extend(branch_result.warnings)
            try:
                popped_prior = float(nodes.get(item_node_id, {}).get("prior"))
            except (TypeError, ValueError):
                popped_prior = 0.0
            branch_penalized_by_contradiction = any(
                (edge.get("type") or edge.get("label")) == "contradicts"
                and edge.get("to") in ({item_node_id} | added_node_set)
                for edge in added_edges
            )
            if popped_prior >= 0.65 and branch_penalized_by_contradiction and not added_frontier_ids and not no_reopen_reason:
                warnings.append(
                    f"{label}: high-prior branch {item_node_id} received a contradiction penalty with no follow-up frontier; ensure the negative result exhausts the whole clue family, not only one bounded interpretation"
                )

            expanded_items.add(item_id)
            last_popped_item = None
            stats["expansions"] += 1
            continue

        if action in {"select", "solution"}:
            if action == "solution":
                warnings.append(f"{label}: action 'solution' is deprecated; use 'select'")
            item_id = event.get("item")
            node_id = event.get("node")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{label}: item must be a non-empty string")
                continue
            if item_id not in items:
                errors.append(f"{label}: references missing frontier item {item_id}")
                continue
            item = items[item_id]
            if not isinstance(node_id, str) or not node_id:
                errors.append(f"{label}: node must be a non-empty string")
            elif node_id not in nodes:
                errors.append(f"{label}: references missing candidate_solution node {node_id}")
            else:
                node_type = nodes[node_id].get("type")
                if node_type != "candidate_solution":
                    errors.append(f"{label}: node {node_id} must be candidate_solution, got {node_type!r}")
                event_selected_nodes.add(node_id)
            try:
                event_cost = float(event.get("cost"))
            except (TypeError, ValueError):
                errors.append(f"{label}: cost must be numeric")
                event_cost = float(item.get("search_cost", item.get("path_cost", math.inf)))
            expected_cost = float(item.get("search_cost", item.get("path_cost", math.inf)))
            if abs(event_cost - expected_cost) > tolerance:
                errors.append(f"{label}: cost {event_cost} != item search_cost {expected_cost}")
            if item_id not in popped_items:
                warnings.append(f"{label}: selected item {item_id} was recorded before a pop event")
            stats["selections"] += 1
            continue

        if action == "stop":
            reason = event.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"{label}: stop reason must be non-empty")
            else:
                stop_reasons.append(reason)
            outcome = event.get("outcome")
            if outcome is None:
                warnings.append(f"{label}: stop outcome missing; using legacy reason-text fallback for exhaustion/coverage checks")
            elif not isinstance(outcome, str) or outcome not in STOP_OUTCOMES:
                errors.append(f"{label}: stop outcome must be one of {sorted(STOP_OUTCOMES)}, got {outcome!r}")
            else:
                stop_outcomes.append(outcome)
            seen_stop = True

    if not seen_stop:
        errors.append("strict search audit requires a stop event")
    if stop_outcomes:
        stop_claims_exhaustion = "frontier_exhausted" in stop_outcomes
    else:
        stop_claims_exhaustion = any(stop_reason_claims_exhaustion(reason) for reason in stop_reasons)
    has_selected_epistemic_candidate = bool(selected_epistemic_candidate_ids(state))
    emit_completion_coverage_warnings = branch_policy_enforce_on == "always" or stop_claims_exhaustion or has_selected_epistemic_candidate
    if deferred_branch_warnings and emit_completion_coverage_warnings:
        warnings.extend(deferred_branch_warnings)
    if stats["pops"] == 0:
        warnings.append("strict search audit saw no pop events")

    reachable_unpopped_frontier_items = [
        items[item_id]
        for item_id in sorted(virtual_frontier)
        if item_id in items and item_id not in popped_items
    ]
    for clue_id in sorted(salient_clue_family_ids(state)):
        clue_node = nodes.get(clue_id, {})
        if clue_node.get("exhausted") is True:
            if not str(clue_node.get("exhaustion_reason") or "").strip():
                warnings.append(f"salient clue family {clue_id} is marked exhausted but lacks exhaustion_reason")
            continue
        has_live_continuation = any(
            item.get("node") == clue_id or clue_id in (item.get("related") or [])
            for item in reachable_unpopped_frontier_items
        )
        if not has_live_continuation and emit_completion_coverage_warnings:
            warnings.append(
                f"salient clue family {clue_id} has no event-reachable unpopped frontier continuation and is not marked exhausted; bounded negative tests must not silently drop high-value clues"
            )

    report = state.get("report", {}) if isinstance(state.get("report"), dict) else {}
    report_candidates = report.get("candidates") if isinstance(report.get("candidates"), list) else []
    viable_candidates = viable_candidate_ids(state)
    report_viable_count = sum(
        1
        for candidate in report_candidates
        if isinstance(candidate, dict)
        and str(candidate.get("id") or "") in viable_candidates
    )
    candidate_count = max(len(viable_candidates), report_viable_count)
    stop_policy_result = audit_stop_policy(state, reachable_unpopped_frontier_items, candidate_count)
    errors.extend(stop_policy_result.errors)
    warnings.extend(stop_policy_result.warnings)
    if stats["selections"] == 0 and candidate_count > 0:
        warnings.append("strict search audit saw no candidate-selection events")
    if candidate_count >= 3:
        expected_branch_count = min(3, candidate_count)
        unvisited_candidates = sorted(
            node_id
            for node_id, node in nodes.items()
            if node.get("type") == "candidate_solution"
            and node_id in viable_candidates
            and node_id not in event_added_nodes
            and node_id not in event_selected_nodes
        )
        if unvisited_candidates:
            warnings.append(
                "candidate_solution nodes not added or selected by strict events: "
                + ", ".join(unvisited_candidates[:8])
                + ("..." if len(unvisited_candidates) > 8 else "")
            )
        if stats["expansions"] < expected_branch_count:
            warnings.append(
                f"strict search has {candidate_count} viable candidates but only {stats['expansions']} expansions; "
                f"expand/penalize at least {expected_branch_count} meaningful live branches when comparing candidates"
            )
        if stats["pops"] < expected_branch_count:
            warnings.append(
                f"strict search has {candidate_count} viable candidates but only {stats['pops']} pops; "
                f"early stop may be under-exploring competing branches"
            )

    return ValidationResult(errors=errors, warnings=warnings), stats


def reconstruct_path(state: dict[str, Any], item_id: str) -> list[dict[str, Any]]:
    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    nodes = by_id(state.get("nodes", []), "node")
    if item_id not in items:
        raise SystemExit(f"frontier item not found: {item_id}")
    path: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = item_id
    while current:
        if current in seen:
            raise SystemExit(f"cycle in parent chain at {current}")
        seen.add(current)
        item = items[current]
        node = nodes.get(str(item.get("node")), {})
        path.append({"item": item, "node": node})
        current = item.get("parent") or ""
    path.reverse()
    return path


def escape_mermaid_label(text: str) -> str:
    # Mermaid node labels are HTML-ish; keep labels compact and safe.
    escaped = html.escape(text, quote=True)
    return escaped.replace("\n", "<br/>")


def clip_text(text: str, limit: int = 72) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)].rstrip() + "…"


def mermaid_id(raw: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in raw)
    if not cleaned:
        cleaned = "N"
    if cleaned[0].isdigit():
        cleaned = "N_" + cleaned
    return cleaned


def html_anchor(raw: str, prefix: str = "details") -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(raw))
    cleaned = cleaned.strip("-") or "node"
    return f"{prefix}-{cleaned}"


def compact_node_label(node: dict[str, Any]) -> str:
    # Keep graph labels stable and tiny. Full text lives in modal/detail cards;
    # long Mermaid labels are hard to navigate and can expose HTML entity noise.
    node_id = str(node.get("id") or "node")
    node_type = str(node.get("type", "node"))
    type_label = "candidate" if node_type == "candidate_solution" else node_type
    status = str(node.get("status") or "").strip()
    if node_type == "test" and status:
        type_label = status
    return f"{node_id}\n{type_label}"


def class_assignments(state: dict[str, Any]) -> dict[str, set[str]]:
    classes: dict[str, set[str]] = {}
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_type = str(node.get("type"))
        cls = CLASS_BY_NODE_TYPE.get(raw_type, "derived")
        node_id = str(node.get("id"))
        classes.setdefault(cls, set()).add(node_id)
        if raw_type == "test":
            status = str(node.get("status") or "").strip()
            if status:
                classes.setdefault(f"test_{status}", set()).add(node_id)

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
    fact_ids = [
        str(node.get("id"))
        for node in state.get("nodes", [])
        if isinstance(node, dict) and node.get("type") in {"fact", "constraint", "derived"}
    ][:10]
    return {node_id for node_id in set(fact_ids) | candidate_ids if node_id in nodes}


GRAPH_GROUPS = (
    ("cluster_goal", "Goal", {"goal"}),
    ("cluster_evidence", "Evidence", {"fact", "constraint"}),
    ("cluster_assumptions", "Assumptions", {"assumption"}),
    ("cluster_inference", "Inference", {"derived", "test"}),
    ("cluster_candidates", "Candidates", {"candidate_solution"}),
    ("cluster_contradictions", "Contradictions", {"contradiction"}),
)


def mermaid_node_definition(mid: str, node: dict[str, Any]) -> str:
    label = escape_mermaid_label(compact_node_label(node))
    return f'{mid}["{label}"]'


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
) -> str:
    safe_direction = direction if direction in {"TD", "TB", "BT", "LR", "RL"} else "TD"
    lines = [f"flowchart {safe_direction}"]
    node_id_map: dict[str, str] = {}
    allowed = include_nodes
    selected_nodes: list[dict[str, Any]] = []
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_id = str(node.get("id"))
        if allowed is not None and raw_id not in allowed:
            continue
        mid = mermaid_id(raw_id)
        node_id_map[raw_id] = mid
        selected_nodes.append(node)

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
                lines.append(f"    {mermaid_node_definition(node_id_map[raw_id], node)}")
            lines.append("  end")
    else:
        for node in selected_nodes:
            raw_id = str(node.get("id"))
            lines.append(f"  {mermaid_node_definition(node_id_map[raw_id], node)}")

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
        if edge_type in {"contradicts", "tests"}:
            lines.append(f"  {src} -. {edge_type} .-> {dst}")
        else:
            lines.append(f"  {src} -- {edge_type} --> {dst}")
        if edge_type == "tests":
            styled_edge_indexes.append(rendered_edge_index)
        rendered_edge_index += 1

    lines.extend(
        [
            "",
            "  classDef goal fill:#fef3c7,stroke:#d97706,stroke-width:2px;",
            "  classDef fact fill:#ecfeff,stroke:#0891b2;",
            "  classDef constraint fill:#fff7ed,stroke:#ea580c;",
            "  classDef derived fill:#f8fafc,stroke:#64748b;",
            "  classDef assumption fill:#f5f3ff,stroke:#7c3aed;",
            "  classDef test fill:#e0f2fe,stroke:#0284c7;",
            "  classDef test_proposed fill:#fef3c7,stroke:#d97706,stroke-dasharray:5 5;",
            "  classDef test_performed fill:#dcfce7,stroke:#16a34a;",
            "  classDef test_inconclusive fill:#f3f4f6,stroke:#71717a,stroke-dasharray:5 5;",
            "  classDef candidate fill:#dbeafe,stroke:#2563eb,stroke-width:2px;",
            "  classDef winning fill:#dcfce7,stroke:#16a34a,stroke-width:3px;",
            "  classDef dim fill:#f3f4f6,stroke:#9ca3af,color:#9ca3af;",
            "  classDef bad fill:#fee2e2,stroke:#dc2626,stroke-width:2px;",
            "  classDef frontier fill:#fafafa,stroke:#71717a,stroke-dasharray: 5 5;",
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
                "  style cluster_contradictions fill:#fef2f2,stroke:#fecaca,stroke-width:1px;",
                "  style cluster_other fill:#fafafa,stroke:#e5e7eb,stroke-width:1px;",
                "",
            ]
        )

    for edge_index in styled_edge_indexes:
        lines.append(f"  linkStyle {edge_index} stroke:#d97706,stroke-dasharray:5 5;")

    classes = class_assignments(state)
    for cls, ids in sorted(classes.items()):
        mids = [node_id_map[node_id] for node_id in sorted(ids) if node_id in node_id_map]
        if mids:
            lines.append(f"  class {','.join(mids)} {cls};")

    for raw_id, mid in sorted(node_id_map.items()):
        anchor = html_anchor(raw_id)
        tooltip = escape_mermaid_label(f"Open details for {raw_id}")
        lines.append(f'  click {mid} "#{anchor}" "{tooltip}"')
    return "\n".join(lines) + "\n"


def ledger_rows(state: dict[str, Any], node_type: str) -> str:
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
            f'<tr id="{html_anchor(raw_id, "ledger")}"><th scope="row">{node_id}</th><td>{text}</td><td>{source_html}</td></tr>'
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


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number):
        return number
    return None


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
            belief_html = f"{belief_html} <small>(truth cost {html.escape(str(truth_value))}; +{html.escape(str(penalty))} soft contradiction)</small>"
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


def node_detail_cards(state: dict[str, Any]) -> str:
    cards: list[str] = []
    for node in state.get("nodes", []):
        if not isinstance(node, dict):
            continue
        raw_id = str(node.get("id", ""))
        raw_type = str(node.get("type", "node"))
        raw_status = str(node.get("status") or "").strip()
        node_type = html.escape(raw_type)
        pill_text = f"{raw_type} · {raw_status}" if raw_status else raw_type
        text = html.escape(str(node.get("text") or node.get("short_text") or ""))
        source = node.get("source") or node.get("sources") or ""
        source_text = ", ".join(str(item) for item in source) if isinstance(source, list) else str(source)
        extras: list[str] = []
        for key in ("prior", "confidence", "probability", "posterior"):
            if key in node:
                extras.append(f"<span>{html.escape(key)}: {html.escape(str(node[key]))}</span>")
        type_class = html.escape(raw_type)
        cards.append(
            f'<article class="detail-card {type_class}" data-node-type="{type_class}" id="{html_anchor(raw_id)}">'
            f'<header><code>{html.escape(raw_id)}</code><span class="pill">{html.escape(pill_text)}</span></header>'
            f'<p>{text}</p>'
            f'{"<p class=\"source\">Source: " + html.escape(source_text) + "</p>" if source_text else ""}'
            f'{"<p class=\"extras\">" + " ".join(extras) + "</p>" if extras else ""}'
            '</article>'
        )
    return "".join(cards) or '<p class="empty">No node details recorded.</p>'


def candidate_focus_options(state: dict[str, Any]) -> str:
    options = ['<option value="">None</option>']
    for index, candidate in enumerate(sorted_report_candidates(state), 1):
        raw_cid = str(candidate.get("id", index))
        key = html.escape(mermaid_id(raw_cid), quote=True)
        text = html.escape(raw_cid)
        options.append(f'<option value="{key}">{text}</option>')
    return "".join(options)


def graph_panel(title: str, mermaid_source: str, graph_id: str, canvas_kind: str = "audit", focus_options: str = "") -> str:
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
    return f"""
<section id="{section_id}" class="graph-section">
  <div class="section-head">
    <h2>{html.escape(title)}</h2>
    <div class="graph-controls">
      <button type="button" data-canvas-mode="{graph_id}" aria-pressed="false">Canvas mode</button>
      <button type="button" data-reset="{graph_id}">Reset view</button>
      {focus_control}
      <span>Ctrl/⌘+wheel zooms. Ctrl/⌘+drag pans. Canvas mode enables direct drag/zoom.</span>
    </div>
  </div>
  <div id="{graph_id}" class="mermaid-wrap graph-canvas {kind_class}">
    <pre class="mermaid">{mermaid_escaped}</pre>
  </div>
</section>
"""


def detail_filter_buttons() -> str:
    filters = [
        ("all", "All"),
        ("fact", "Facts"),
        ("constraint", "Constraints"),
        ("assumption", "Assumptions"),
        ("derived", "Derived"),
        ("candidate_solution", "Candidates"),
        ("contradiction", "Contradictions"),
        ("test", "Tests"),
    ]
    buttons = [
        f'<button type="button" data-filter="{html.escape(value)}">{html.escape(label)}</button>'
        for value, label in filters
    ]
    return '<div class="detail-filters" aria-label="Filter node details">' + "".join(buttons) + "</div>"


def mermaid_flowchart_config(spacing: str) -> str:
    base = 'htmlLabels: true, useMaxWidth: false'
    presets = {
        "default": base,
        "relaxed": base + ', nodeSpacing: 70, rankSpacing: 90, curve: "basis"',
        "wide": base + ', nodeSpacing: 100, rankSpacing: 130, curve: "basis"',
        "compact": base + ', nodeSpacing: 35, rankSpacing: 45, curve: "linear"',
    }
    return presets.get(spacing, base)


def graph_edge_connections(state: dict[str, Any], include_nodes: set[str] | None = None) -> list[dict[str, str]]:
    connections: list[dict[str, str]] = []
    allowed = include_nodes
    for edge in state.get("edges", []):
        if not isinstance(edge, dict):
            continue
        src = str(edge.get("from"))
        dst = str(edge.get("to"))
        if allowed is not None and (src not in allowed or dst not in allowed):
            continue
        connections.append(
            {
                "from": mermaid_id(src),
                "to": mermaid_id(dst),
                "label": str(edge.get("type") or edge.get("label") or "leads_to"),
            }
        )
    return connections


def candidate_focus_nodes(state: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    raw_id = str(candidate.get("id") or "")
    node_ids: list[str] = [raw_id] if raw_id else []
    explicit = False
    for key in ("path_nodes", "support_nodes", "supporting_nodes", "nodes"):
        values = candidate.get(key)
        if isinstance(values, list) and values:
            explicit = True
            node_ids.extend(str(value) for value in values)

    nodes_by_id = by_id(state.get("nodes", []), "node")
    supportive_edges = {"supports", "requires", "assumes"}
    non_expanding_seed_types = {"contradiction", "test"}
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
        mid = mermaid_id(node_id)
        if mid and mid not in seen:
            seen.add(mid)
            result.append(mid)
    return result


def candidate_focus_map(state: dict[str, Any]) -> dict[str, list[str]]:
    focus: dict[str, list[str]] = {}
    for candidate in sorted_report_candidates(state):
        if "id" not in candidate:
            continue
        focus[mermaid_id(str(candidate["id"]))] = candidate_focus_nodes(state, candidate)
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


def html_document(state: dict[str, Any], mermaid_source: str, spacing: str = "default") -> str:
    summary = state.get("summary", {}) if isinstance(state.get("summary"), dict) else {}
    report = state.get("report", {}) if isinstance(state.get("report"), dict) else {}
    title = html.escape(str(summary.get("title") or report.get("title") or "Reasoning Graph"))
    answer = html.escape(str(summary.get("answer") or report.get("answer") or "See report sections."))
    presentation_ids = presentation_node_ids(state)
    presentation_source = to_mermaid(state, presentation_ids, group_by_type=False) if presentation_ids else "flowchart TD\n"
    candidates_html = candidate_rows(state)
    focus_options = candidate_focus_options(state)
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

    details_html = node_detail_cards(state)
    filters_html = detail_filter_buttons()
    presentation_title = "Best explanation graph"
    edge_maps_json = json.dumps(
        {
            "presentation-graph": graph_edge_connections(state, presentation_ids),
            "audit-graph": graph_edge_connections(state),
        },
        ensure_ascii=False,
    ).replace("</", "<\\/")
    candidate_focus_json = json.dumps(candidate_focus_map(state), ensure_ascii=False).replace("</", "<\\/")

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
    .graph-canvas.canvas-mode {{ cursor: grab; touch-action: none; }}
    .graph-canvas svg, .graph-canvas svg * {{ user-select: none; -webkit-user-select: none; }}
    .graph-canvas.panning {{ cursor: grabbing; }}
    [data-canvas-mode][aria-pressed="true"] {{ background: #dbeafe; border-color: #93c5fd; color: #1e3a8a; }}
    .graph-canvas-presentation {{ height: min(58vh, 560px); min-height: 380px; }}
    .graph-canvas-audit {{ height: min(78vh, 860px); min-height: 560px; }}
    .graph-canvas .mermaid {{ width: 100%; height: 100%; margin: 0; display: block; overflow: visible; }}
    .graph-canvas svg {{ width: 100% !important; height: 100% !important; max-width: none !important; display: block; }}
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
    .extras span {{ display: inline-block; margin-right: .5rem; color: var(--muted); }}
    .floating-nav {{ position: fixed; right: 1rem; bottom: 1rem; z-index: 20; font-size: .86rem; }}
    .nav-toggle {{ width: 2.45rem; height: 2.45rem; border-radius: 999px; display: grid; place-items: center; background: rgba(255,255,255,.96); box-shadow: 0 10px 28px rgba(15,23,42,.18); }}
    .floating-nav .nav-menu {{ position: absolute; right: 0; bottom: calc(100% + .45rem); display: none; flex-direction: column; gap: .35rem; min-width: 9rem; padding: .5rem; background: rgba(255,255,255,.96); border: 1px solid var(--line); border-radius: 14px; box-shadow: 0 10px 28px rgba(15,23,42,.16); }}
    .floating-nav.open .nav-menu {{ display: flex; }}
    .floating-nav a {{ text-decoration: none; padding: .35rem .55rem; border-radius: 999px; background: #eff6ff; white-space: nowrap; }}
    .node-modal {{ width: min(720px, calc(100vw - 2rem)); max-height: min(82vh, 760px); border: 0; border-radius: 18px; padding: 0; box-shadow: 0 30px 80px rgba(15,23,42,.35); overflow: hidden; overscroll-behavior: contain; }}
    .node-modal::backdrop {{ background: rgba(15,23,42,.48); backdrop-filter: blur(2px); }}
    .modal-shell {{ padding: 1rem; max-height: calc(min(82vh, 760px) - 64px); overflow: auto; overscroll-behavior: contain; }}
    .modal-bar {{ display: flex; justify-content: space-between; align-items: center; gap: 1rem; border-bottom: 1px solid var(--line); padding: .75rem 1rem; background: var(--soft); }}
    .modal-title {{ display: flex; align-items: center; gap: .55rem; margin: 0; font-size: 1rem; }}
    .modal-title code {{ font-size: .95rem; }}
    .modal-close {{ font-size: 1.2rem; line-height: 1; padding: .35rem .65rem; }}
    .node-modal .detail-card {{ border: 1px solid var(--line); background: var(--soft); padding: .85rem; border-radius: 14px; box-shadow: inset 0 1px 0 rgba(255,255,255,.7); }}
    .node-modal .detail-card p:first-child {{ margin-top: 0; }}
    .node-modal .detail-card p:last-child {{ margin-bottom: 0; }}
    @media (max-width: 720px) {{ main {{ padding: 1rem; }} .graph-canvas-presentation {{ min-height: 340px; }} .graph-canvas-audit {{ min-height: 460px; }} .floating-nav {{ right: .75rem; bottom: .75rem; }} }}
  </style>
</head>
<body>
<nav class="floating-nav" aria-label="Graph navigation">
  <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="floating-nav-menu" title="Open navigation">☰</button>
  <div id="floating-nav-menu" class="nav-menu">
    <a href="#section-presentation-graph">Presentation</a>
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

  {graph_panel(presentation_title, presentation_source, "presentation-graph", "presentation", focus_options)}
  {graph_panel("Full audit graph", mermaid_source, "audit-graph", "audit", focus_options)}

  <section id="node-details-section">
    <h2>Node details</h2>
    <p class="hint">Includes facts, constraints, assumptions, and candidate answers. Use filters or click graph nodes for popup cards.</p>
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
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  mermaid.initialize({{ startOnLoad: false, securityLevel: "loose", flowchart: {{ {mermaid_flowchart_config(spacing)} }} }});
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
    content.replaceChildren(clone);
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
    const initial = {{ ...box }};
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
      if (!canUseCanvasDirectly() && !modifierPressed(event)) return;
      event.preventDefault();
      const focus = clientPointInSvg(event);
      const factor = event.deltaY > 0 ? 1.14 : 0.88;
      const nextWidth = Math.max(80, box.width * factor);
      const nextHeight = Math.max(80, box.height * factor);
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
      if (event.target.closest && (event.target.closest("a") || edgeContainerFor(event.target))) return;
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

  mermaid.run({{ querySelector: ".mermaid" }}).then(setupGraphs).catch((error) => {{
    console.error("Mermaid render failed", error);
    setupGraphs();
  }});
</script>
</body>
</html>
"""

def cmd_validate(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    result = validate_state(state)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if result.ok:
        print("ok")
        print(f"nodes={len(state.get('nodes', []))} edges={len(state.get('edges', []))} frontier={len(state.get('frontier', []))}")
        return 0
    return 1


def cmd_costs(args: argparse.Namespace) -> int:
    state = compute_costs(load_state(args.state))
    dump_state(state, args.output, args.state if args.in_place else None)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    result, stats = audit_state(state)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if result.ok:
        print("ok")
        print(
            "events={events} pops={pops} expansions={expansions} selections={selections}".format(**stats)
        )
        return 0
    return 1


def cmd_sort(args: argparse.Namespace) -> int:
    state = sorted_frontier(load_state(args.state))
    dump_state(state, args.output, args.state if args.in_place else None)
    return 0


def cmd_frontier(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    ids = None if args.all else cursor["active_ids"]
    rows = [item_view(state, item) for item in sorted_frontier_items(state, ids)]
    if args.limit is not None:
        rows = rows[: args.limit]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        if cursor["stopped"] and not args.all:
            print("search stopped; active frontier empty unless --all is used", file=sys.stderr)
        if cursor["pending_item"] and not args.all:
            print(f"pending expansion: {cursor['pending_item']}", file=sys.stderr)
        for row in rows:
            related = f" related={row['related_brief']}" if row.get("related_brief") else ""
            scratch = f" scratch={row['scratch_brief']}" if row.get("scratch_brief") else ""
            print(
                f"{row['id']} search={row['search_cost']} truth={row['truth_cost']} node={row['node']} "
                f"type={row['node_type']} text={row['text']}{related}{scratch}"
            )
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    if cursor["stopped"]:
        print("error: search already has a stop event", file=sys.stderr)
        return 1
    if cursor["pending_item"]:
        print(f"error: pending popped item {cursor['pending_item']} must be expanded or selected before next pop", file=sys.stderr)
        return 1
    active = sorted_frontier_items(state, cursor["active_ids"])
    if not active:
        print("error: active frontier is empty", file=sys.stderr)
        return 1

    item = active[0]
    view = item_view(state, item)
    path = reconstruct_path(state, str(item["id"]))

    if args.pop:
        if not args.in_place and not args.output:
            print("error: --pop requires --in-place or --output so the pop event is persisted", file=sys.stderr)
            return 1
        events = state.setdefault("events", [])
        if not isinstance(events, list):
            print("error: events must be a list before --pop can append", file=sys.stderr)
            return 1
        if not cursor["initialized"]:
            init_ids = [frontier_item["id"] for frontier_item in sorted_frontier_items(state, cursor["active_ids"])]
            events.append({"step": next_event_step(state), "action": "init", "frontier": init_ids})
        pop_event: dict[str, Any] = {
            "step": next_event_step(state),
            "action": "pop",
            "item": item["id"],
            "cost": item.get("search_cost", item.get("path_cost")),
        }
        evidence_version = item.get("evidence_version", state.get("evidence_version"))
        if evidence_version is not None:
            pop_event["evidence_version"] = evidence_version
        events.append(pop_event)
        dump_state(state, args.output, args.state if args.in_place else None)

    if args.json:
        print(json.dumps({"item": view, "path": path}, indent=2, ensure_ascii=False))
    else:
        print(
            f"next {view['id']} search={view['search_cost']} truth={view['truth_cost']} node={view['node']} "
            f"type={view['node_type']} text={view['text']}"
        )
        if view.get("related_brief"):
            print(f"related: {view['related_brief']}")
        if view.get("scratch_brief"):
            print(f"scratch: {view['scratch_brief']}")
        print("path:")
        for step in path:
            path_item = step["item"]
            path_node = step["node"]
            print(
                f"  {path_item.get('id')} search={path_item.get('search_cost', path_item.get('path_cost'))} truth={path_item.get('truth_cost')} "
                f"node={path_node.get('id')} type={path_node.get('type')} text={path_node.get('text', '')}"
            )
    return 0


def _object_list(value: Any, field: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        result.append(item)
    return result


def _ensure_unique_new_ids(existing: set[str], additions: list[dict[str, Any]], field: str) -> None:
    seen: set[str] = set()
    for index, item in enumerate(additions):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"{field}[{index}] missing string id")
        if item_id in existing:
            raise ValueError(f"{field}[{index}] id {item_id} already exists")
        if item_id in seen:
            raise ValueError(f"{field}[{index}] duplicate new id {item_id}")
        seen.add(item_id)


def cmd_expand(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    if cursor["stopped"] and not args.force:
        print("error: search already has a stop event; use --force to append anyway", file=sys.stderr)
        return 1
    if cursor["pending_item"] != args.item and not args.force:
        print(
            f"error: expand must target pending popped item {cursor['pending_item']!r}; use `next --pop` first or pass --force",
            file=sys.stderr,
        )
        return 1

    patch = load_state(args.patch)
    if not isinstance(patch, dict):
        raise ValueError("expansion patch must be a JSON object")

    nodes_to_add = _object_list(patch.get("nodes", patch.get("add_node_objects")), "nodes")
    edges_to_add = _object_list(patch.get("edges", patch.get("add_edge_objects")), "edges")
    frontier_to_add = _object_list(patch.get("frontier", patch.get("add_frontier_objects")), "frontier")

    existing_nodes = {node.get("id") for node in state.get("nodes", []) if isinstance(node, dict)}
    existing_edges = {edge.get("id") for edge in state.get("edges", []) if isinstance(edge, dict) and edge.get("id")}
    existing_frontier = {item.get("id") for item in state.get("frontier", []) if isinstance(item, dict)}
    _ensure_unique_new_ids({str(item) for item in existing_nodes if item}, nodes_to_add, "nodes")
    _ensure_unique_new_ids({str(item) for item in existing_edges if item}, edges_to_add, "edges")
    _ensure_unique_new_ids({str(item) for item in existing_frontier if item}, frontier_to_add, "frontier")

    for child in frontier_to_add:
        if child.get("parent") in (None, ""):
            child["parent"] = args.item

    state.setdefault("nodes", []).extend(nodes_to_add)
    state.setdefault("edges", []).extend(edges_to_add)
    state.setdefault("frontier", []).extend(frontier_to_add)
    sorted_frontier(state)

    events = state.setdefault("events", [])
    if not isinstance(events, list):
        raise ValueError("events must be a list before expand can append")
    event: dict[str, Any] = {
        "step": next_event_step(state),
        "action": "expand",
        "item": args.item,
        "add_nodes": [node["id"] for node in nodes_to_add],
        "add_edges": [edge["id"] for edge in edges_to_add],
        "add_frontier": [item["id"] for item in frontier_to_add],
    }
    for key in ("mode", "summary", "reason"):
        if key in patch:
            event[key] = patch[key]
    events.append(event)

    select_spec = patch.get("select", patch.get("solution"))
    selected_node: str | None = None
    selected_item = args.item
    if isinstance(select_spec, str):
        selected_node = select_spec
    elif isinstance(select_spec, dict):
        raw_selected_node = select_spec.get("node")
        raw_selected_item = select_spec.get("item")
        if isinstance(raw_selected_node, str):
            selected_node = raw_selected_node
        if isinstance(raw_selected_item, str):
            selected_item = raw_selected_item
    elif isinstance(patch.get("solution_node"), str):
        selected_node = patch["solution_node"]
    if selected_node:
        frontier_items = by_id(state.get("frontier", []), "frontier item")
        if selected_item not in frontier_items:
            raise ValueError(f"selected item {selected_item} is not a frontier item")
        events.append(
            {
                "step": next_event_step(state),
                "action": "select",
                "item": selected_item,
                "node": selected_node,
                "cost": frontier_items[selected_item].get("search_cost", frontier_items[selected_item].get("path_cost")),
            }
        )

    stop_reason = patch.get("stop_reason")
    if stop_reason is None and isinstance(patch.get("stop"), str):
        stop_reason = patch.get("stop")
    if stop_reason is not None:
        if not isinstance(stop_reason, str) or not stop_reason.strip():
            raise ValueError("stop_reason must be a non-empty string")
        stop_outcome = patch.get("stop_outcome", patch.get("outcome"))
        if stop_outcome not in STOP_OUTCOMES:
            raise ValueError(f"stop_outcome must be one of {sorted(STOP_OUTCOMES)}, got {stop_outcome!r}")
        events.append({"step": next_event_step(state), "action": "stop", "reason": stop_reason, "outcome": stop_outcome})

    result = validate_state(state)
    if result.errors:
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    dump_state(state, args.output, args.state if args.in_place else None)
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    nodes = by_id(state.get("nodes", []), "node")
    cursor = search_cursor(state)

    item_id = args.item or cursor.get("pending_item")
    if not isinstance(item_id, str) or not item_id:
        print("error: no pending popped item; use `next --pop` first or pass --item with --force", file=sys.stderr)
        return 1
    if item_id not in items:
        print(f"error: frontier item not found: {item_id}", file=sys.stderr)
        return 1
    if cursor.get("pending_item") not in (None, item_id) and not args.force:
        print(f"error: pending popped item is {cursor.get('pending_item')}, not {item_id}; use --force to override", file=sys.stderr)
        return 1
    if cursor.get("pending_item") is None and not args.force:
        print("error: select expects a pending popped item; use --force to append anyway", file=sys.stderr)
        return 1

    node = nodes.get(args.node)
    if node is None:
        print(f"error: candidate_solution node not found: {args.node}", file=sys.stderr)
        return 1
    if node.get("type") != "candidate_solution":
        print(f"error: node {args.node} must be candidate_solution", file=sys.stderr)
        return 1

    events = state.setdefault("events", [])
    if not isinstance(events, list):
        print("error: events must be a list before select can append", file=sys.stderr)
        return 1
    events.append(
        {
            "step": next_event_step(state),
            "action": "select",
            "item": item_id,
            "node": args.node,
            "cost": items[item_id].get("search_cost", items[item_id].get("path_cost")),
        }
    )
    dump_state(state, args.output, args.state if args.in_place else None)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    reason = args.reason.strip()
    if not reason:
        print("error: stop reason must be non-empty", file=sys.stderr)
        return 1
    if args.outcome not in STOP_OUTCOMES:
        print(f"error: --outcome must be one of {sorted(STOP_OUTCOMES)}, got {args.outcome!r}", file=sys.stderr)
        return 1
    events = state.setdefault("events", [])
    if not isinstance(events, list):
        print("error: events must be a list before stop can append", file=sys.stderr)
        return 1
    events.append({"step": next_event_step(state), "action": "stop", "reason": reason, "outcome": args.outcome})
    dump_state(state, args.output, args.state if args.in_place else None)
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    path = reconstruct_path(state, args.item)
    if args.json:
        print(json.dumps(path, indent=2, ensure_ascii=False))
    else:
        for step in path:
            item = step["item"]
            node = step["node"]
            print(
                f"{item.get('id')} search={item.get('search_cost', item.get('path_cost'))} truth={item.get('truth_cost')} "
                f"node={node.get('id')} type={node.get('type')} text={node.get('text', '')}"
            )
    return 0


def cmd_mermaid(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    include_nodes = presentation_node_ids(state) if args.view == "presentation" else None
    source = to_mermaid(state, include_nodes, group_by_type=args.grouped or args.view == "audit")
    if args.output:
        Path(args.output).write_text(source, encoding="utf-8")
    else:
        sys.stdout.write(source)
    return 0


def cmd_html(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    result = validate_state(state)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if not result.ok:
        return 1
    source = to_mermaid(state, group_by_type=True)
    document = html_document(state, source, args.spacing)
    if args.output:
        Path(args.output).write_text(document, encoding="utf-8")
    else:
        sys.stdout.write(document)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reasoning graph helper")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="validate graph/search state")
    validate.add_argument("state", help="state JSON path, or - for stdin")
    validate.set_defaults(func=cmd_validate)

    costs = sub.add_parser("costs", help="compute truth_cost/search_cost; path_cost is emitted as a legacy alias")
    costs.add_argument("state", help="state JSON path, or - for stdin")
    costs.add_argument("-o", "--output", help="write result to path instead of stdout")
    costs.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
    costs.set_defaults(func=cmd_costs)

    audit = sub.add_parser("audit", help="audit strict-search compact events")
    audit.add_argument("state", help="state JSON path, or - for stdin")
    audit.set_defaults(func=cmd_audit)

    sort = sub.add_parser("sort", help="compute costs and sort frontier by search_cost")
    sort.add_argument("state", help="state JSON path, or - for stdin")
    sort.add_argument("-o", "--output", help="write result to path instead of stdout")
    sort.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
    sort.set_defaults(func=cmd_sort)

    frontier = sub.add_parser("frontier", help="show sorted active frontier derived from events")
    frontier.add_argument("state", help="state JSON path, or - for stdin")
    frontier.add_argument("--all", action="store_true", help="show all frontier items, not only active virtual frontier")
    frontier.add_argument("--json", action="store_true", help="print JSON instead of compact text")
    frontier.add_argument("--limit", type=int, help="maximum number of rows")
    frontier.set_defaults(func=cmd_frontier)

    next_cmd = sub.add_parser("next", help="show or persistently pop the lowest-cost active frontier item")
    next_cmd.add_argument("state", help="state JSON path, or - for stdin")
    next_cmd.add_argument("--pop", action="store_true", help="append init/pop events for the selected item")
    next_cmd.add_argument("-o", "--output", help="write mutated state to path when --pop is used")
    next_cmd.add_argument("-i", "--in-place", action="store_true", help="rewrite input file when --pop is used")
    next_cmd.add_argument("--json", action="store_true", help="print JSON item/path context")
    next_cmd.set_defaults(func=cmd_next)

    expand = sub.add_parser("expand", help="append nodes/edges/frontier from a JSON expansion patch and record an expand event")
    expand.add_argument("state", help="state JSON path, or - for stdin")
    expand.add_argument("--item", required=True, help="popped frontier item being expanded")
    expand.add_argument("--patch", required=True, help="JSON patch path, or - for stdin")
    expand.add_argument("-o", "--output", help="write mutated state to path")
    expand.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
    expand.add_argument("--force", action="store_true", help="skip pending-pop guard")
    expand.set_defaults(func=cmd_expand)

    select = sub.add_parser("select", help="record selected candidate_solution for the pending popped item")
    select.add_argument("state", help="state JSON path, or - for stdin")
    select.add_argument("--node", required=True, help="candidate_solution node id")
    select.add_argument("--item", help="frontier item id; defaults to pending popped item")
    select.add_argument("-o", "--output", help="write mutated state to path")
    select.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
    select.add_argument("--force", action="store_true", help="append even when there is no pending popped item")
    select.set_defaults(func=cmd_select)

    stop = sub.add_parser("stop", help="append a stop event")
    stop.add_argument("state", help="state JSON path, or - for stdin")
    stop.add_argument("--reason", required=True, help="why search is stopping")
    stop.add_argument("--outcome", required=True, choices=sorted(STOP_OUTCOMES), help="structured stop outcome")
    stop.add_argument("-o", "--output", help="write mutated state to path")
    stop.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
    stop.set_defaults(func=cmd_stop)

    path = sub.add_parser("path", help="reconstruct parent-pointer path for a frontier item")
    path.add_argument("state", help="state JSON path, or - for stdin")
    path.add_argument("item", help="frontier item id, e.g. Q7")
    path.add_argument("--json", action="store_true", help="print JSON instead of compact text")
    path.set_defaults(func=cmd_path)

    mermaid = sub.add_parser("mermaid", help="render Mermaid source")
    mermaid.add_argument("state", help="state JSON path, or - for stdin")
    mermaid.add_argument("-o", "--output", help="write Mermaid source to path")
    mermaid.add_argument("--view", choices=("audit", "presentation"), default="audit", help="render full audit graph or curated presentation graph")
    mermaid.add_argument("--grouped", action="store_true", help="group nodes into Mermaid subgraphs by node type")
    mermaid.set_defaults(func=cmd_mermaid)

    html_cmd = sub.add_parser("html", help="render CDN Mermaid HTML")
    html_cmd.add_argument("state", help="state JSON path, or - for stdin")
    html_cmd.add_argument("-o", "--output", help="write HTML to path")
    html_cmd.add_argument("--spacing", choices=("default", "relaxed", "wide", "compact"), default="default", help="Mermaid flowchart spacing preset")
    html_cmd.set_defaults(func=cmd_html)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
