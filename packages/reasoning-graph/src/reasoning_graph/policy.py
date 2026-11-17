"""Goal, candidate, and answer-check helper predicates."""

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
    """Goals that a claimed answer may leave unanswered."""

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
    """Explain each accepted, non-optional goal that a claimed answer would leave open."""

    answered = answered_goal_ids(state)
    directly = directly_answered_goal_ids(state)
    requirements = goal_requirements(state)
    messages: list[str] = []
    for goal_id in sorted(accepted_goal_ids(state) - optional_goal_ids(state)):
        if goal_id in answered:
            continue
        if goal_id not in directly:
            messages.append(f"accepted goal {_goal_brief(state, goal_id)} is unanswered: no answers edge from a hypothesis")
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
    """The one definition of a candidate: a node with an answers edge to a goal, mapped to those goals.

    Validation guarantees the node is a hypothesis; every reader of candidacy goes through here.
    """
    goals = goal_ids(state)
    targets: dict[str, set[str]] = {}
    for edge in state.get("edges", []):
        if not isinstance(edge, dict) or edge.get("type") != "answers":
            continue
        src, dst = edge.get("from"), edge.get("to")
        if isinstance(src, str) and dst in goals:
            targets.setdefault(src, set()).add(str(dst))
    return targets


def viable_candidate_ids(state: dict[str, Any]) -> set[str]:
    accepted = accepted_goal_ids(state)
    targets = candidate_goal_targets(state)
    return {candidate_id for candidate_id, goal_targets in targets.items() if goal_targets & accepted}


def ranked_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Candidates ranked by computed belief, for the rendered view only."""

    node_truth_costs = node_effective_truth_costs(state)
    ranked = [
        {
            "id": candidate_id,
            "effective_truth_cost": round(node_truth_costs[candidate_id], 6),
            "belief": round(math.exp(-node_truth_costs[candidate_id]), 6),
        }
        for candidate_id in viable_candidate_ids(state)
    ]
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


def ungrounded_answer_messages(state: dict[str, Any]) -> list[str]:
    """Explain each named answer candidate that lacks evidence grounding.

    The check judges the candidate the answer names, never the top-ranked one: the agent is not
    steered by computed belief.
    """

    named = {candidate_id for candidate_id in answer_candidates(state).values() if candidate_id}
    ruled_out = named & truth_inputs(state).ruled_out_nodes
    return [
        f"answer candidate {candidate_id} is ruled out: it, or a premise it rests on, has a rules_out edge from an observation; "
        "name another candidate, or change that edge to contradicts if the rule-out was wrong"
        for candidate_id in sorted(ruled_out)
    ] + [
        f"answer candidate {candidate_id} is not evidence-grounded; claims resting on scores alone: {', '.join(claims)}"
        for candidate_id, claims in ungrounded_claims_by_candidate(state, named - ruled_out).items()
    ]


def unrecorded_test_messages(state: dict[str, Any]) -> list[str]:
    """Name tests with no result observation; a failed or inconclusive probe still records one, a not_run test states why none exists."""

    nodes = by_id(state.get("nodes", []), "node")
    tests_with_results = {
        edge.get("from")
        for edge in state.get("edges", [])
        if isinstance(edge, dict)
        and edge.get("type") == "yields"
    }
    missing = sorted(
        node_id
        for node_id, node in nodes.items()
        if node.get("type") == "test" and node_id not in tests_with_results and "not_run" not in node
    )
    if not missing:
        return []
    return [f"test(s) without a recorded result observation: {', '.join(missing)}"]


def _names(text: str, candidate_id: str) -> bool:
    """Whether an answer text names the candidate by id as a whole word.

    Only the id: a text match found "Thornton" inside "Sergeant Josiah Thornton" and "42"
    inside "142", and silently picked a node.
    """

    # A bare substring would find CS1 inside CS10.
    return bool(re.search(rf"(?<![\w-]){re.escape(candidate_id)}(?![\w-])", text))


def _candidate_listing(nodes: dict[str, dict[str, Any]], candidate_ids: list[str]) -> str:
    return ", ".join(f"{candidate_id} ({str(nodes.get(candidate_id, {}).get('text') or '').strip()!r})" for candidate_id in candidate_ids)


def claimed_answer(state: dict[str, Any]) -> str:
    """The claim: `summary.answer`, empty while no answer is claimed."""

    summary = state.get("summary") if isinstance(state.get("summary"), dict) else {}
    return str(summary.get("answer") or "").strip()


def _named_in(text: str, candidate_ids: list[str]) -> list[str]:
    return [candidate_id for candidate_id in candidate_ids if _names(text, candidate_id)]


def answer_candidates(state: dict[str, Any]) -> dict[str, str | None]:
    """The candidate the answer names, per required goal that has candidates.

    The answer is always named, in `summary.answer`: a goal's only candidate is not its answer,
    or a half-finished graph with one candidate would count as a claim. None when
    the answer names no candidate of the goal, or more than one.
    """

    required_goals = accepted_goal_ids(state) - optional_goal_ids(state)
    answers: dict[str, str | None] = {}
    for goal_id, candidates in goal_candidates(state).items():
        if goal_id not in required_goals:
            continue
        named = _named_in(claimed_answer(state), candidates)
        answers[goal_id] = named[0] if len(named) == 1 else None
    return answers


def answer_labels(state: dict[str, Any]) -> dict[str, str]:
    """What the rendered view writes on each answer candidate; the goal is named when several take an answer."""

    answers = answer_candidates(state)
    goals_by_candidate: dict[str, list[str]] = {}
    for goal_id, candidate_id in sorted(answers.items()):
        if candidate_id is not None:
            goals_by_candidate.setdefault(candidate_id, []).append(goal_id)
    return {
        candidate_id: f"ANSWER to {', '.join(goals)}" if len(answers) > 1 else "ANSWER"
        for candidate_id, goals in goals_by_candidate.items()
    }


def unnamed_answer_messages(state: dict[str, Any]) -> list[str]:
    """Name each answer text that does not stand for one candidate of each required goal.

    `summary.answer` names the answer candidate by id; any candidate may be the answer.
    """

    nodes = by_id(state.get("nodes", []), "node")
    claim = claimed_answer(state)
    answers = answer_candidates(state)
    messages = []
    for goal_id, candidates in sorted(goal_candidates(state).items()):
        if goal_id not in answers:
            continue
        if answers[goal_id] is not None:
            continue
        named = _named_in(claim, candidates)
        if named:
            messages.append(f"summary.answer names several candidates for goal {goal_id}: {', '.join(named)}; name the one answer")
        else:
            messages.append(
                f"summary.answer names no candidate for goal {goal_id}; name one by id; candidates: {_candidate_listing(nodes, candidates)}; answer: {claim!r}"
            )
    return messages
