"""Shared constants and result types for reasoning graph state."""

from __future__ import annotations

from dataclasses import dataclass


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
