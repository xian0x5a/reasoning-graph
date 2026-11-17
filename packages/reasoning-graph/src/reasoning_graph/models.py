"""Shared constants and result types for reasoning graph state."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass


NODE_TYPES = {
    "goal",
    "observation",
    "constraint",
    "hypothesis",
    "test",
}


BELIEF_NODE_TYPES = {"observation", "hypothesis"}


EDGE_TYPES = {
    "requires",
    "supports",
    "contradicts",
    "prompts",
    "tested_by",  # legacy alias; prefer prompts for follow-up work provenance
    "tests",  # legacy alias; prefer prompts for follow-up work provenance
    "premise_of",
    "yields",
    "answers",
    "rules_out",
}


FACTOR_RELATIONS = {
    "premise_of",
    "supports",
    "contradicts",
}


# A test yields what was observed. A conclusion drawn from that observation is a
# separate hypothesis, with the observation as its premise.
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


# The page draws, groups, and filters a node by its role: its type, or `candidate` for a
# node with an answers edge to a goal. Validation guarantees such a node is a hypothesis.
CANDIDATE_ROLE = "candidate"
RENDER_CLASSES = {"goal", "observation", "constraint", "hypothesis", "test", CANDIDATE_ROLE}


def node_role(node: dict, candidate_ids: Collection[str]) -> str:
    return CANDIDATE_ROLE if node.get("id") in candidate_ids else str(node.get("type", "node"))


def node_type_label(node: dict) -> str:
    """Short type label shown on a node; a not_run test says so, since no result will ever exist."""
    if node.get("type") == "test" and "not_run" in node:
        return "test · not run"
    return str(node.get("type", "node"))


def node_render_class(node: dict, candidate_ids: Collection[str]) -> str:
    if node.get("type") == "test" and "not_run" in node:
        return "not_run"
    role = node_role(node, candidate_ids)
    return role if role in RENDER_CLASSES else "hypothesis"


@dataclass
class ValidationResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors
