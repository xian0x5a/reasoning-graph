"""Compact index of a state: what to reread after a context reset instead of the whole JSON.

One line per node, edge, and group, with what is still open first. It holds what was authored,
without source quotes, and nothing computed.
"""

from __future__ import annotations

from typing import Any

from .costs import DEFAULT_CLAIM_SCORE, DEFAULT_EVIDENCE_SCORE
from .models import BELIEF_NODE_TYPES, RESULT_NODE_TYPES


def _one_line(value: Any) -> str:
    return " ".join(str(value or "").split())


def _note(item: dict[str, Any]) -> str:
    return f" | note: {_one_line(item['note'])}" if item.get("note") else ""


def _node_line(node: dict[str, Any], state_of_test: str = "") -> str:
    node_type = str(node.get("type"))
    details = []
    if "score" in node and node["score"] != DEFAULT_CLAIM_SCORE.get(node_type):
        details.append(f"score {node['score']}")
    if state_of_test:
        details.append(state_of_test)
    if node.get("exhausted"):
        details.append(_one_line(f"exhausted: {node.get('exhaustion_reason') or 'no reason given'}"))
    detail = f" ({'; '.join(details)})" if details else ""
    source = f" [{_one_line(node['source'])}]" if node.get("source") else ""
    return f"- {node.get('id')} {node_type}{detail}: {_one_line(node.get('text'))}{source}{_note(node)}"


def _edge_line(edge: dict[str, Any]) -> str:
    source, target = edge.get("from"), edge.get("to")
    score = f"({edge['score']})" if "score" in edge and edge["score"] != DEFAULT_EVIDENCE_SCORE else ""
    return f"- {source} -{edge.get('type')}{score}-> {target}{_note(edge)}"


def _group_line(group: dict[str, Any]) -> str:
    edge_ids = ", ".join(str(edge_id) for edge_id in group.get("edges") or [])
    return f"- {group.get('id')} [{edge_ids}] score {group.get('score')}{_note(group)}"


def index_document(state: dict[str, Any]) -> str:
    nodes = [node for node in state.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in state.get("edges", []) if isinstance(edge, dict)]
    groups = [group for group in state.get("factors") or [] if isinstance(group, dict)]
    node_types = {node.get("id"): node.get("type") for node in nodes}

    premises = [edge for edge in edges if edge.get("type") == "leads_to"]
    tests_with_results = {edge.get("from") for edge in premises if node_types.get(edge.get("to")) in RESULT_NODE_TYPES}
    premise_backed = {edge.get("to") for edge in premises if node_types.get(edge.get("from")) in BELIEF_NODE_TYPES}

    def test_state(node: dict[str, Any]) -> str:
        if "not_run" in node:
            return f"not run: {_one_line(node['not_run'])}"
        return "" if node.get("id") in tests_with_results else "no result"

    def is_open(node: dict[str, Any]) -> bool:
        if node.get("type") == "hypothesis":
            return node.get("id") not in premise_backed and not node.get("exhausted")
        return node.get("type") == "test" and bool(test_state(node))

    def lines_of(selected: list[dict[str, Any]]) -> list[str]:
        return [_node_line(node, test_state(node) if node.get("type") == "test" else "") for node in selected]

    goals = [node for node in nodes if node.get("type") == "goal"]
    open_nodes = [node for node in nodes if is_open(node)]
    other_nodes = [node for node in nodes if node.get("type") != "goal" and not is_open(node)]

    summary = state.get("summary") if isinstance(state.get("summary"), dict) else {}
    header = [
        *lines_of(goals),
        *([f"Answer: {_one_line(summary['answer'])}"] if summary.get("answer") else []),
    ]
    sections = [
        ("# Reasoning graph index", header),
        ("## Open", lines_of(open_nodes) or ["- nothing open"]),
        ("## Nodes", lines_of(other_nodes)),
        ("## Edges", [_edge_line(edge) for edge in edges]),
        ("## Groups", [_group_line(group) for group in groups]),
    ]
    return "\n\n".join("\n".join([title, *lines]) for title, lines in sections if lines) + "\n"
