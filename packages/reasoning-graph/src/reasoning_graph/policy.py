"""Goal, candidate, and stop-policy helper predicates."""

from __future__ import annotations

import math
from typing import Any

from .costs import node_effective_truth_costs, node_truth_cost, evidence_grounded_node_ids, probability_from_value, truth_inputs
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


def optional_goal_ids(state: dict[str, Any]) -> set[str]:
    """Goals that a candidate-bearing stop may leave unanswered."""

    goals = goal_ids(state)
    policy = state.get("goal_policy") if isinstance(state.get("goal_policy"), dict) else {}
    configured = policy.get("optional_goals")
    if isinstance(configured, list):
        return {str(goal_id) for goal_id in configured if str(goal_id) in goals}
    return set()


def goal_requirements(state: dict[str, Any]) -> dict[str, set[str]]:
    """Sub-goal structure: `parent goal --requires--> child goal`."""

    goals = goal_ids(state)
    requirements: dict[str, set[str]] = {}
    for edge in state.get("edges", []):
        if not isinstance(edge, dict) or edge.get("type") != "requires":
            continue
        src, dst = edge.get("from"), edge.get("to")
        if src in goals and dst in goals:
            requirements.setdefault(str(src), set()).add(str(dst))
    return requirements


def directly_answered_goal_ids(state: dict[str, Any]) -> set[str]:
    return {goal_id for goal_targets in candidate_goal_targets(state).values() for goal_id in goal_targets}


def answered_goal_ids(state: dict[str, Any]) -> set[str]:
    """A goal is answered when a candidate answers it and every required sub-goal is answered."""

    directly = directly_answered_goal_ids(state)
    requirements = goal_requirements(state)
    optional = optional_goal_ids(state)
    answered: set[str] = set()

    def resolve(goal_id: str, visiting: set[str]) -> bool:
        if goal_id in answered:
            return True
        if goal_id in visiting or goal_id not in directly:
            return False
        visiting.add(goal_id)
        # An optional sub-goal may stay open without blocking its parent.
        complete = all(
            sub_goal in optional or resolve(sub_goal, visiting)
            for sub_goal in sorted(requirements.get(goal_id, set()))
        )
        visiting.discard(goal_id)
        if complete:
            answered.add(goal_id)
        return complete

    for goal_id in sorted(goal_ids(state)):
        resolve(goal_id, set())
    return answered


def _goal_brief(state: dict[str, Any], goal_id: str) -> str:
    nodes = by_id(state.get("nodes", []), "node")
    text = str(nodes.get(goal_id, {}).get("text") or "").strip()
    return f"{goal_id} ({text[:80]!r})" if text else goal_id


def unanswered_goal_messages(state: dict[str, Any]) -> list[str]:
    """Explain each accepted, non-optional goal that a candidate-bearing stop would leave open."""

    answered = answered_goal_ids(state)
    directly = directly_answered_goal_ids(state)
    requirements = goal_requirements(state)
    messages: list[str] = []
    for goal_id in sorted(accepted_goal_ids(state) - optional_goal_ids(state)):
        if goal_id in answered:
            continue
        if goal_id not in directly:
            messages.append(f"accepted goal {_goal_brief(state, goal_id)} is unanswered: no answers edge from a candidate_solution")
            continue
        open_sub_goal = next(
            (sub_goal for sub_goal in sorted(requirements.get(goal_id, set())) if sub_goal not in answered and sub_goal not in optional_goal_ids(state)),
            None,
        )
        if open_sub_goal is not None:
            messages.append(f"accepted goal {_goal_brief(state, goal_id)} requires unanswered goal {_goal_brief(state, open_sub_goal)}")
    return messages


def goal_best_candidates(state: dict[str, Any]) -> dict[str, str]:
    """Best-belief candidate per accepted goal that has at least one answering candidate."""

    nodes = by_id(state.get("nodes", []), "node")
    node_truth_costs = node_effective_truth_costs(state)
    accepted = accepted_goal_ids(state)
    best: dict[str, tuple[float, str]] = {}
    for candidate_id, goal_targets in candidate_goal_targets(state).items():
        truth_cost = node_truth_costs.get(candidate_id)
        if truth_cost is None:
            truth_cost = node_truth_cost(nodes.get(candidate_id, {}))
        for goal_id in goal_targets & accepted:
            if goal_id not in best or (truth_cost, candidate_id) < best[goal_id]:
                best[goal_id] = (truth_cost, candidate_id)
    return {goal_id: candidate_id for goal_id, (_, candidate_id) in best.items()}


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


def ranked_viable_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = by_id(state.get("nodes", []), "node")
    node_truth_costs = node_effective_truth_costs(state)
    ranked: list[dict[str, Any]] = []
    for candidate_id in sorted(viable_candidate_ids(state)):
        node = nodes.get(candidate_id, {})
        truth_cost = node_truth_costs.get(candidate_id)
        if truth_cost is None:
            truth_cost = node_truth_cost(node)
        belief = math.exp(-truth_cost)
        ranked.append(
            {
                "node": candidate_id,
                "belief": round(belief, 6),
                "effective_truth_cost": round(truth_cost, 6),
            }
        )
    return sorted(ranked, key=lambda candidate: (candidate["effective_truth_cost"], str(candidate["node"])))


def best_candidate_ids(state: dict[str, Any]) -> set[str]:
    ranked = ranked_viable_candidates(state)
    return {str(ranked[0]["node"])} if ranked else set()


def best_epistemic_candidate_ids(state: dict[str, Any]) -> set[str]:
    epistemic_goals = epistemic_goal_ids(state)
    if not epistemic_goals:
        return set()
    targets = candidate_goal_targets(state)
    return {candidate_id for candidate_id in best_candidate_ids(state) if targets.get(candidate_id, set()) & epistemic_goals}


def candidate_pruned_ids(state: dict[str, Any]) -> set[str]:
    """Legacy compatibility: contradictions no longer disqualify candidate nodes."""

    return set()


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
        search_cost = float(candidate.get("search_cost"))
    except (TypeError, ValueError):
        search_cost = math.inf
    return (truth_cost, search_cost, str(candidate.get("id") or candidate.get("name") or ""))


def sorted_report_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    report = state.get("report", {}) if isinstance(state.get("report"), dict) else {}
    report_candidates = report.get("candidates") if isinstance(report.get("candidates"), list) else []
    metadata_by_id = {
        str(candidate.get("id")): candidate
        for candidate in report_candidates
        if isinstance(candidate, dict) and candidate.get("id") is not None
    }
    nodes = by_id(state.get("nodes", []), "node")
    node_truth_costs = node_effective_truth_costs(state)
    filtered: list[dict[str, Any]] = []
    # The graph is the source of candidates; `report` is optional metadata that can
    # lag behind the graph, so it only annotates live candidates and never adds any.
    for candidate_id in viable_candidate_ids(state):
        node = nodes.get(candidate_id, {})
        enriched = {"id": candidate_id, "name": node.get("text"), **metadata_by_id.get(candidate_id, {})}
        search_cost = finite_float(enriched.get("search_cost"))
        if search_cost is not None:
            enriched["search_cost"] = round(search_cost, 6)
        truth_cost = node_truth_costs.get(candidate_id)
        if truth_cost is None:
            truth_cost = finite_float(enriched.get("truth_cost"))
        if truth_cost is None:
            truth_cost = node_truth_cost(node)
        effective_truth_cost = truth_cost
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


def ungrounded_claims_by_candidate(state: dict[str, Any], candidate_ids: set[str]) -> dict[str, list[str]]:
    """Map each ungrounded candidate to the deepest ungrounded claims on its premise chain.

    Those claims are where evidence is missing; grounded candidates are omitted.
    """

    inputs = truth_inputs(state)
    grounded = evidence_grounded_node_ids(inputs)

    def ungrounded_roots(node_id: str) -> set[str]:
        ungrounded_premises = [premise for premise in inputs.premise_sources.get(node_id, []) if premise not in grounded]
        if not ungrounded_premises:
            return {node_id}
        return set().union(*(ungrounded_roots(premise) for premise in ungrounded_premises))

    return {candidate_id: sorted(ungrounded_roots(candidate_id)) for candidate_id in sorted(candidate_ids) if candidate_id not in grounded}


def ungrounded_goal_answer_messages(state: dict[str, Any]) -> list[str]:
    """Explain each best answer to an accepted, non-optional goal that lacks evidence grounding."""

    best_by_goal = goal_best_candidates(state)
    required_goals = accepted_goal_ids(state) - optional_goal_ids(state)
    best_candidates = {candidate_id for goal_id, candidate_id in best_by_goal.items() if goal_id in required_goals}
    return [
        f"best candidate {candidate_id} is not evidence-grounded; claims resting on scores alone: {', '.join(claims)}"
        for candidate_id, claims in ungrounded_claims_by_candidate(state, best_candidates).items()
    ]


def strongest_grounded_candidate_belief(state: dict[str, Any]) -> float:
    ranked = ranked_viable_candidates(state)
    ungrounded = ungrounded_claims_by_candidate(state, {str(candidate["node"]) for candidate in ranked})
    beliefs = [finite_float(candidate.get("belief")) for candidate in ranked if candidate["node"] not in ungrounded]
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
