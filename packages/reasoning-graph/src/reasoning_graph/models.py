"""Shared constants and result types for reasoning graph state."""

from __future__ import annotations

from dataclasses import dataclass


NODE_TYPES = {
    "goal",
    "observation",
    "constraint",
    "hypothesis",
    "test",
    "candidate_solution",
}


BELIEF_NODE_TYPES = {"observation", "hypothesis", "candidate_solution"}


EDGE_TYPES = {
    "requires",
    "supports",
    "contradicts",
    "prompts",
    "tested_by",  # legacy alias; prefer prompts for follow-up work provenance
    "tests",  # legacy alias; prefer prompts for follow-up work provenance
    "leads_to",
    "answers",
}


FACTOR_RELATIONS = {
    "leads_to",
    "supports",
    "contradicts",
}


FACTOR_AGGREGATION_KINDS = {
    "joint_probability",
    "likelihood",
}


AUDIT_EVENT_ACTIONS = {
    "record",
    "review",
    "rank",
    "stop",
}


STOP_OUTCOMES = {
    "solved",
    "candidate_threshold_met",
    "candidate_count_met",
    "budget_exhausted",
    "blocked",
    "user_stopped",
    "inconclusive",
}


CANDIDATE_STOP_OUTCOMES = {
    "solved",
    "candidate_threshold_met",
    "candidate_count_met",
}

# Confidence claims need observation-backed belief; candidate_count_met measures breadth, not confidence.
EVIDENCE_GROUNDED_STOP_OUTCOMES = {
    "solved",
    "candidate_threshold_met",
}


# A test result is what was observed; a conclusion drawn from it is a separate hypothesis
# linked by leads_to from the observation.
RESULT_NODE_TYPES = {"observation"}


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


CLASS_BY_NODE_TYPE = {
    "goal": "goal",
    "observation": "observation",
    "constraint": "constraint",
    "hypothesis": "hypothesis",
    "test": "test",
    "candidate_solution": "candidate",
}


def node_type_label(node: dict) -> str:
    """Short type label shown on a node; a not_run test says so, since no result will ever exist."""
    node_type = str(node.get("type", "node"))
    if node_type == "test" and "not_run" in node:
        return "test · not run"
    return "candidate" if node_type == "candidate_solution" else node_type


def node_render_class(node: dict) -> str:
    if node.get("type") == "test" and "not_run" in node:
        return "not_run"
    return CLASS_BY_NODE_TYPE.get(str(node.get("type")), "hypothesis")


@dataclass
class ValidationResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors
