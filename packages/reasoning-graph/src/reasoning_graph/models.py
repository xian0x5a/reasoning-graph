"""Shared constants and result types for reasoning graph state."""

from __future__ import annotations

from dataclasses import dataclass


NODE_TYPES = {
    "goal",
    "evidence",
    "constraint",
    "derived",
    "assumption",
    "test",
    "candidate_solution",
}


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
    "init",
    "seed",
    "pop",
    "assign",
    "expand",
    "supersede",
    "rank",
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
    "evidence": "evidence",
    "constraint": "constraint",
    "derived": "derived",
    "assumption": "assumption",
    "test": "test",
    "candidate_solution": "candidate",
}


@dataclass
class ValidationResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors
