"""The case for the claimed answer: what a reader checks before trusting it.

Plain data, taken from the graph alone. The why-tree follows the edges belief flows
through (`leads_to` premises and `supports` evidence), so the case and the computed
belief tell the same story. The page lays it out; nothing here writes prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .costs import (
    node_effective_truth_costs,
    probability_from_cost,
    resolve_edge_groups,
)
from .graph_view import edge_type
from .models import BELIEF_NODE_TYPES
from .policy import answer_candidates, goal_candidates
from .state import by_id, edge_id

WHY_RELATIONS = ("leads_to", "supports")
# Edges that tie a test to the claim it checks, as (claim end, test end).
TEST_LINKS = {"prompts": ("from", "to"), "tested_by": ("from", "to"), "tests": ("to", "from")}
CLAIM_TYPES = {"hypothesis", "candidate_solution"}


@dataclass(frozen=True)
class CaseNode:
    id: str
    type: str
    text: str
    source: str | None
    quote: str | None
    not_run: str | None
    # Computed belief of a claim; None for goals, constraints and tests.
    belief: float | None


@dataclass(frozen=True)
class CaseLink:
    """One edge into a node of the case, and the node at its other end."""

    relation: str
    # The target of the edge: the node this link argues for or against.
    target: str
    node: CaseNode
    # The edge's own score, or its group's; None when the default applies.
    score: int | None
    group: str | None
    # True when the node was already laid out earlier in the case: it is referenced, not repeated.
    reference: bool
    reasons: tuple[CaseLink, ...]


@dataclass(frozen=True)
class CaseTest:
    node: CaseNode
    # The why-tree nodes that prompted this test, that it checks, or that it produced.
    about: tuple[str, ...]
    results: tuple[CaseNode, ...]


@dataclass(frozen=True)
class CaseRival:
    node: CaseNode
    against: tuple[CaseLink, ...]


@dataclass(frozen=True)
class WeakSpot:
    # no_input | single_input: a claim resting on nothing or on one input;
    # no_quote: an observation without its verbatim quote; test_not_run.
    kind: str
    node_id: str


@dataclass(frozen=True)
class Case:
    goal: CaseNode
    answer: CaseNode
    why: tuple[CaseLink, ...]
    against: tuple[CaseLink, ...]
    tests: tuple[CaseTest, ...]
    rivals: tuple[CaseRival, ...]
    weak_spots: tuple[WeakSpot, ...]


def answer_cases(state: dict[str, Any]) -> list[Case]:
    """One case per goal whose answer the claim names; empty while no answer is claimed."""

    answers = answer_candidates(state)
    if not any(answers.values()):
        return []
    graph = _CaseGraph(state)
    candidates_by_goal = goal_candidates(state)
    return [
        graph.case(goal_id, answer_id, candidates_by_goal.get(goal_id, []))
        for goal_id, answer_id in sorted(answers.items())
        if answer_id is not None
    ]


class _CaseGraph:
    def __init__(self, state: dict[str, Any]) -> None:
        self.nodes = by_id(state.get("nodes", []), "node")
        self.edges = [
            edge
            for edge in state.get("edges", [])
            if isinstance(edge, dict) and edge.get("from") in self.nodes and edge.get("to") in self.nodes
        ]
        groups, _ = resolve_edge_groups(state)
        self.group_of_edge = {member: group for group in groups for member in group.edge_ids}
        self.truth_costs = node_effective_truth_costs(state)

    def case_node(self, node_id: str) -> CaseNode:
        node = self.nodes[node_id]
        return CaseNode(
            id=node_id,
            type=str(node.get("type", "")),
            text=str(node.get("text") or ""),
            source=node.get("source"),
            quote=node.get("quote"),
            not_run=node.get("not_run"),
            belief=probability_from_cost(self.truth_costs[node_id]) if node.get("type") in BELIEF_NODE_TYPES else None,
        )

    def edges_into(self, node_id: str, relations: tuple[str, ...]) -> list[dict[str, Any]]:
        return [edge for edge in self.edges if edge["to"] == node_id and edge_type(edge) in relations]

    def link(self, edge: dict[str, Any], reference: bool, reasons: tuple[CaseLink, ...] = ()) -> CaseLink:
        group = self.group_of_edge.get(edge_id(edge))
        score = edge.get("score", group.score if group else None)
        return CaseLink(
            relation=edge_type(edge),
            target=str(edge["to"]),
            node=self.case_node(str(edge["from"])),
            score=score,
            group=group.group_id if group else None,
            reference=reference,
            reasons=reasons,
        )

    def input_count(self, node_id: str) -> int:
        """Premises and support of a claim, counting a group once."""
        edge_ids = [edge_id(edge) for edge in self.edges_into(node_id, WHY_RELATIONS)]
        return len({self.group_of_edge[member].group_id if member in self.group_of_edge else member for member in edge_ids})

    def why_tree(self, answer_id: str) -> tuple[tuple[CaseLink, ...], list[str]]:
        """The answer's reasons, depth first, and the why-tree nodes in the order they are laid out."""

        laid_out = [answer_id]

        def reasons_for(node_id: str) -> tuple[CaseLink, ...]:
            # Observations are the base of the argument: the walk stops there.
            if self.nodes[node_id].get("type") == "observation":
                return ()
            links = []
            for edge in self.edges_into(node_id, WHY_RELATIONS):
                source = str(edge["from"])
                if source in laid_out:
                    links.append(self.link(edge, reference=True))
                    continue
                laid_out.append(source)
                links.append(self.link(edge, reference=False, reasons=reasons_for(source)))
            return tuple(links)

        return reasons_for(answer_id), laid_out

    def tests_of(self, why_nodes: list[str]) -> list[CaseTest]:
        about: dict[str, list[str]] = {}
        for edge in self.edges:
            relation = edge_type(edge)
            if relation in TEST_LINKS:
                claim_end, test_end = TEST_LINKS[relation]
                claim, test = str(edge[claim_end]), str(edge[test_end])
            elif relation == "leads_to":
                claim, test = str(edge["to"]), str(edge["from"])
            else:
                continue
            if self.nodes[test].get("type") == "test" and claim in why_nodes and claim not in about.get(test, []):
                about.setdefault(test, []).append(claim)
        return [
            CaseTest(
                node=self.case_node(test_id),
                about=tuple(about[test_id]),
                results=tuple(
                    self.case_node(str(edge["to"]))
                    for edge in self.edges
                    if edge["from"] == test_id and edge_type(edge) == "leads_to" and self.nodes[edge["to"]].get("type") == "observation"
                ),
            )
            # In node order, so a test reads the same wherever it is linked from.
            for test_id in self.nodes
            if test_id in about
        ]

    def weak_spots(self, why_nodes: list[str], tests: list[CaseTest]) -> list[WeakSpot]:
        spots = []
        for node_id in why_nodes:
            node_type = self.nodes[node_id].get("type")
            if node_type == "observation" and not self.nodes[node_id].get("quote"):
                spots.append(WeakSpot("no_quote", node_id))
            elif node_type in CLAIM_TYPES and (count := self.input_count(node_id)) <= 1:
                spots.append(WeakSpot("no_input" if count == 0 else "single_input", node_id))
        spots.extend(WeakSpot("test_not_run", test.node.id) for test in tests if test.node.not_run)
        return spots

    def case(self, goal_id: str, answer_id: str, goal_candidate_ids: list[str]) -> Case:
        why, why_nodes = self.why_tree(answer_id)
        tests = self.tests_of(why_nodes)
        rivals = sorted(
            (candidate_id for candidate_id in goal_candidate_ids if candidate_id != answer_id),
            key=lambda candidate_id: (self.truth_costs[candidate_id], candidate_id),
        )
        return Case(
            goal=self.case_node(goal_id),
            answer=self.case_node(answer_id),
            why=why,
            against=tuple(
                self.link(edge, reference=False) for node_id in why_nodes for edge in self.edges_into(node_id, ("contradicts",))
            ),
            tests=tuple(tests),
            rivals=tuple(
                CaseRival(
                    node=self.case_node(rival_id),
                    against=tuple(self.link(edge, reference=False) for edge in self.edges_into(rival_id, ("contradicts",))),
                )
                for rival_id in rivals
            ),
            weak_spots=tuple(self.weak_spots(why_nodes, tests)),
        )
