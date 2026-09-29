"""Goal, candidate, and stop-policy helper predicates."""

from __future__ import annotations

import math
import re
from typing import Any

from .costs import node_effective_truth_costs, evidence_grounded_node_ids, truth_inputs
from .models import EPISTEMIC_GOAL_MARKERS, GOAL_TEXT_CLUE_MARKERS, GOAL_TEXT_EXACT_ANSWER_MARKERS
from .state import by_id


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


def goal_candidates(state: dict[str, Any]) -> dict[str, list[str]]:
    """Candidates answering each accepted goal that has any, in node order."""

    accepted = accepted_goal_ids(state)
    targets = candidate_goal_targets(state)
    by_goal: dict[str, list[str]] = {}
    # Walk the nodes, not the target map: its order follows a set and changes between runs.
    for candidate_id in by_id(state.get("nodes", []), "node"):
        for goal_id in sorted(targets.get(candidate_id, set()) & accepted):
            by_goal.setdefault(goal_id, []).append(candidate_id)
    return by_goal


def goal_best_candidates(state: dict[str, Any]) -> dict[str, str]:
    """Top-ranked candidate per accepted goal, for the rendered view only: no gate reads belief."""

    node_truth_costs = node_effective_truth_costs(state)
    accepted = accepted_goal_ids(state)
    best: dict[str, tuple[float, str]] = {}
    for candidate_id, goal_targets in candidate_goal_targets(state).items():
        truth_cost = node_truth_costs[candidate_id]
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


def viable_candidate_ids(state: dict[str, Any]) -> set[str]:
    accepted = accepted_goal_ids(state)
    targets = candidate_goal_targets(state)
    return {candidate_id for candidate_id, goal_targets in targets.items() if goal_targets & accepted}


def sorted_report_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Candidates ranked by computed belief, for the rendered view only."""

    report = state.get("report", {}) if isinstance(state.get("report"), dict) else {}
    report_candidates = report.get("candidates") if isinstance(report.get("candidates"), list) else []
    metadata_by_id = {
        str(candidate.get("id")): candidate
        for candidate in report_candidates
        if isinstance(candidate, dict) and candidate.get("id") is not None
    }
    nodes = by_id(state.get("nodes", []), "node")
    node_truth_costs = node_effective_truth_costs(state)
    # The graph is the source of candidates; `report` is optional metadata that can
    # lag behind the graph, so it only annotates live candidates and never adds any.
    ranked = [
        {
            "id": candidate_id,
            "name": nodes.get(candidate_id, {}).get("text"),
            **metadata_by_id.get(candidate_id, {}),
            "effective_truth_cost": round(node_truth_costs[candidate_id], 6),
            "belief": round(math.exp(-node_truth_costs[candidate_id]), 6),
        }
        for candidate_id in viable_candidate_ids(state)
    ]
    total_belief = sum(candidate["belief"] for candidate in ranked)
    if total_belief > 0:
        for candidate in ranked:
            candidate["weight"] = round(candidate["belief"] / total_belief, 6)
    return sorted(ranked, key=lambda candidate: (candidate["effective_truth_cost"], str(candidate["id"])))


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
    """Explain each answer to an accepted, non-optional goal that is not named or lacks evidence grounding.

    The gate judges the candidate the answer names, never the top-ranked one: the agent is not
    steered by computed belief (issue #37).
    """

    nodes = by_id(state.get("nodes", []), "node")
    required_goals = accepted_goal_ids(state) - optional_goal_ids(state)
    answers = answer_candidates(state)
    messages = [
        f"goal {goal_id} has {len(candidates)} candidates and no answer names one; "
        f"name the one answer in summary.answer, by id or exact text: {_candidate_listing(nodes, candidates)}"
        for goal_id, candidates in sorted(goal_candidates(state).items())
        if goal_id in required_goals and answers[goal_id] is None and not _named_in_state(state, nodes, candidates)
    ]
    named = {candidate_id for goal_id, candidate_id in answers.items() if goal_id in required_goals and candidate_id}
    return messages + [
        f"answer candidate {candidate_id} is not evidence-grounded; claims resting on scores alone: {', '.join(claims)}"
        for candidate_id, claims in ungrounded_claims_by_candidate(state, named).items()
    ]


def unrecorded_test_messages(state: dict[str, Any]) -> list[str]:
    """Name tests with no result observation; a failed or inconclusive probe still records one, a not_run test states why none exists."""

    nodes = by_id(state.get("nodes", []), "node")
    tests_with_results = {
        edge.get("from")
        for edge in state.get("edges", [])
        if isinstance(edge, dict)
        and edge.get("type") == "leads_to"
        and nodes.get(edge.get("to"), {}).get("type") == "observation"
    }
    missing = sorted(
        node_id
        for node_id, node in nodes.items()
        if node.get("type") == "test" and node_id not in tests_with_results and "not_run" not in node
    )
    if not missing:
        return []
    return [f"test(s) without a recorded result observation: {', '.join(missing)}"]


def too_few_candidates_messages(state: dict[str, Any]) -> list[str]:
    """Opt-in breadth gate for when the user asked for alternatives; strict init never sets it."""

    policy = state.get("stop_policy") if isinstance(state.get("stop_policy"), dict) else {}
    minimum = policy.get("min_viable_candidates")
    if not isinstance(minimum, int) or minimum <= 0:
        return []
    viable = len(viable_candidate_ids(state))
    if viable >= minimum:
        return []
    return [f"viable candidates {viable} < stop_policy.min_viable_candidates {minimum}"]


def candidate_stop_messages(state: dict[str, Any]) -> list[str]:
    """Everything a candidate-bearing stop must satisfy: each accepted goal answered, and requested breadth."""

    return unanswered_goal_messages(state) + too_few_candidates_messages(state)


def grounded_stop_messages(state: dict[str, Any]) -> list[str]:
    """Everything a solved stop must satisfy beyond answering each goal and naming the answer."""

    return ungrounded_goal_answer_messages(state) + unrecorded_test_messages(state)


def _names(text: str, candidate_id: str, candidate_text: str) -> bool:
    """Whether an answer text names the candidate, by id as a whole word or by its exact text."""

    # A bare substring would find CS1 inside CS10.
    by_id_word = re.search(rf"(?<![\w-]){re.escape(candidate_id)}(?![\w-])", text)
    return bool(by_id_word) or bool(candidate_text and candidate_text in text)


def _candidate_text(nodes: dict[str, dict[str, Any]], candidate_id: str) -> str:
    return str(nodes.get(candidate_id, {}).get("text") or "").strip()


def _candidate_listing(nodes: dict[str, dict[str, Any]], candidate_ids: list[str]) -> str:
    return ", ".join(f"{candidate_id} ({_candidate_text(nodes, candidate_id)!r})" for candidate_id in candidate_ids)


def state_answer_texts(state: dict[str, Any]) -> dict[str, str]:
    """The non-empty answer texts the state holds, by field."""

    texts = {
        f"{section}.answer": str(state[section].get("answer") or "").strip()
        for section in ("summary", "report")
        if isinstance(state.get(section), dict)
    }
    return {field: text for field, text in texts.items() if text}


def _named_in_state(state: dict[str, Any], nodes: dict[str, dict[str, Any]], candidate_ids: list[str]) -> list[str]:
    texts = state_answer_texts(state).values()
    return [
        candidate_id
        for candidate_id in candidate_ids
        if any(_names(text, candidate_id, _candidate_text(nodes, candidate_id)) for text in texts)
    ]


def answer_candidates(state: dict[str, Any]) -> dict[str, str | None]:
    """The candidate the answer stands for, per accepted goal that has candidates.

    A goal's only candidate is its answer. Among several, it is the one `summary.answer` or
    `report.answer` names; None when they name none or more than one.
    """

    nodes = by_id(state.get("nodes", []), "node")
    answers: dict[str, str | None] = {}
    for goal_id, candidates in goal_candidates(state).items():
        named = candidates if len(candidates) == 1 else _named_in_state(state, nodes, candidates)
        answers[goal_id] = named[0] if len(named) == 1 else None
    return answers


def unnamed_answer_messages(state: dict[str, Any], draft: str | None = None) -> list[str]:
    """Name each answer text that does not stand for a candidate of an accepted goal.

    `summary.answer`, `report.answer`, and the draft each name the answer candidate by id or exact
    text; any candidate may be the answer. An empty text is not checked.
    """

    nodes = by_id(state.get("nodes", []), "node")
    texts = state_answer_texts(state)
    if draft:
        texts["draft"] = draft
    answers = answer_candidates(state)
    messages = []
    for goal_id, candidates in sorted(goal_candidates(state).items()):
        answer = answers[goal_id]
        named_in_state = _named_in_state(state, nodes, candidates)
        if answer is None and len(named_in_state) > 1:
            messages.append(
                f"{' and '.join(state_answer_texts(state))} names several candidates for goal {goal_id}: "
                f"{', '.join(named_in_state)}; name the one answer"
            )
        for field, text in texts.items():
            verb = "mention" if field == "draft" else "name"
            quoted = "" if field == "draft" else f"; answer: {text!r}"
            if answer is not None and not _names(text, answer, _candidate_text(nodes, answer)):
                messages.append(f"{field} does not {verb} candidate {answer} ({_candidate_text(nodes, answer)!r}) for goal {goal_id}{quoted}")
            elif answer is None and not any(_names(text, candidate_id, _candidate_text(nodes, candidate_id)) for candidate_id in candidates):
                messages.append(f"{field} {verb}s no candidate for goal {goal_id}; candidates: {_candidate_listing(nodes, candidates)}{quoted}")
    return messages
