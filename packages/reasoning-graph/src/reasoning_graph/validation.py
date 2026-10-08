"""Reasoning graph schema and policy validation."""

from __future__ import annotations

from typing import Any

from .costs import (
    EVIDENCE_EDGE_TYPES,
    REMOVED_EDGE_SCORE_FIELDS,
    REMOVED_NODE_SCORE_FIELDS,
    assert_acyclic_premise_dependencies,
    node_effective_truth_costs,
    removed_score_field_message,
    require_score,
    resolve_edge_groups,
)
from .models import ANSWER_KINDS, BELIEF_NODE_TYPES, EDGE_TYPES, EPISTEMIC_GOAL_MARKERS, NODE_TYPES, ValidationResult
from .policy import accepted_goal_ids, candidate_goal_targets, goal_accepts_answer_kind, goal_ids, goal_requirements
from .schema_validation import state_schema_errors
from .state import edge_id


# Sections that held a second copy of the graph for the reader. No agent wrote one in 42
# benchmark states, and the rendered view derives all of it from the graph.
REMOVED_GRAPH_COPIES = ("report", "presentation", "view")


def authored_field_errors(nodes: list[Any], edges: list[Any]) -> list[str]:
    """Reject removed fields, and scores off the scale or on objects that take none.

    `record` runs this on a patch's additions too, so a removed field names its replacement
    there instead of failing with the schema's generic message.
    """
    errors: list[str] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        owner = f"node {node.get('id') or index}"
        if isinstance(node.get("id"), str) and "-" in node["id"]:
            # `O1-H1` has to read as one edge, from O1 to H1.
            errors.append(f"node id {node['id']!r} contains a hyphen; an edge is named from-to, so a node id takes none")
        errors.extend(removed_score_field_message(owner, field) for field in REMOVED_NODE_SCORE_FIELDS if field in node)
        if "belief" in node:
            errors.append(f"{owner}: belief was removed from the state; it is computed when the graph is rendered; delete the field")
        if "score" not in node:
            continue
        if node.get("type") not in BELIEF_NODE_TYPES:
            errors.append(f"{owner}: score is only valid on observation, hypothesis, and candidate_solution nodes")
            continue
        try:
            require_score(node["score"])
        except ValueError as exc:
            errors.append(f"{owner}: {exc}")
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            continue
        owner = f"edge {edge_id(edge)}"
        if "id" in edge:
            # Agents wrote from-to as the id in 225 of 245 edges, the same thing twice.
            errors.append(f"{owner}: id was removed; an edge is identified by its ends, as from-to; delete the field")
        errors.extend(removed_score_field_message(owner, field) for field in REMOVED_EDGE_SCORE_FIELDS if field in edge)
        if "reasoning" in edge:
            # `reasoning` was 45% of edge bytes and mostly restated the two node texts.
            errors.append(f"{owner}: reasoning was removed; use the optional note, or leave the link unexplained when the two texts make it obvious")
        if "score" not in edge:
            continue
        if edge.get("type") not in EVIDENCE_EDGE_TYPES:
            errors.append(f"{owner}: score is only valid on supports/contradicts edges")
            continue
        try:
            require_score(edge["score"])
        except ValueError as exc:
            errors.append(f"{owner}: {exc}")
    return errors


def validate_state(state: Any) -> ValidationResult:
    if not isinstance(state, dict):
        return ValidationResult(errors=["schema $: state must be an object"], warnings=[])
    errors: list[str] = state_schema_errors(state)
    warnings: list[str] = []
    nodes_raw = state.get("nodes", [])
    edges_raw = state.get("edges", [])
    solutions_raw = state.get("solutions", [])
    factors_raw = state.get("factors", [])

    if factors_raw is None:
        factors_raw = []
    if not isinstance(nodes_raw, list):
        errors.append("nodes must be a list")
        nodes_raw = []
    if not isinstance(edges_raw, list):
        errors.append("edges must be a list")
        edges_raw = []
    if not isinstance(solutions_raw, list):
        errors.append("solutions must be a list")
        solutions_raw = []
    elif solutions_raw:
        warnings.append("solutions list is deprecated; use candidate_solution nodes with answers edges to the goal")
    if not isinstance(factors_raw, list):
        errors.append("factors must be a list when present")
        factors_raw = []
    if "premise_groups" in state:
        errors.append("premise_groups is not supported; use factors, which group leads_to edges by id")

    errors.extend(authored_field_errors(nodes_raw, edges_raw))

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
        if "not_run" in node:
            if node_type != "test":
                errors.append(f"node {node_id or i} not_run is only valid on test nodes")
            elif not isinstance(node["not_run"], str) or not node["not_run"].strip():
                errors.append(f"node {node_id or i} not_run must be a non-empty reason")
        if "exhausted" in node and not isinstance(node.get("exhausted"), bool):
            errors.append(f"node {node_id or i} exhausted must be boolean when present")
        if node.get("exhausted") is True and not str(node.get("exhaustion_reason") or "").strip():
            warnings.append(f"node {node_id or i} exhausted=true should include exhaustion_reason")
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
        for key in ("accepted_goals", "preferred_goals", "optional_goals"):
            if key in goal_policy:
                values = goal_policy.get(key)
                if not isinstance(values, list) or not values:
                    errors.append(f"goal_policy.{key} must be a non-empty list when present")
                    continue
                for i, goal_id in enumerate(values):
                    if goal_id not in goal_ids:
                        errors.append(f"goal_policy.{key}[{i}] references missing goal {goal_id!r}")
    if "stop_policy" in state:
        # It configured the stop gate, which went with the stop certificate.
        errors.append("stop_policy was removed: nothing gates a stop; audit checks the answer summary.answer claims; delete the field")
    errors.extend(
        f"{section} was removed: the state is the graph; the answer is summary.answer, a reason is a note on the node or edge, "
        "a next check is a test node; delete the field"
        for section in REMOVED_GRAPH_COPIES
        if section in state
    )
    if "events" in state:
        # The trace was verified to guard the stop certificate; nothing else read it.
        errors.append("events was removed: the state keeps no trace; the list order of nodes and edges is the order of the work; delete the field")
    accepted_goal_values = goal_policy.get("accepted_goals") if isinstance(goal_policy, dict) else None
    accepted_goal_ids = {str(goal_id) for goal_id in accepted_goal_values} if isinstance(accepted_goal_values, list) else set(goal_ids)
    goals_by_id = {node.get("id"): node for node in nodes_raw if isinstance(node, dict) and node.get("type") == "goal"}
    candidate_nodes = [node for node in nodes_raw if isinstance(node, dict) and node.get("type") == "candidate_solution"]
    candidate_ids = {node.get("id") for node in candidate_nodes}
    candidate_goal_edges: set[str] = set()
    candidate_accepted_goal_edges: set[str] = set()
    candidate_goal_targets: dict[str, set[str]] = {}
    seen_edge_ids: set[str] = set()
    for i, edge in enumerate(edges_raw):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}] must be object")
            continue
        if edge_id(edge) in seen_edge_ids:
            errors.append(f"edge {edge_id(edge)} exists more than once: one edge per ordered pair; change it with update_edges")
        seen_edge_ids.add(edge_id(edge))
        src = edge.get("from")
        dst = edge.get("to")
        edge_type = edge.get("type") or edge.get("label")
        if src not in node_ids:
            errors.append(f"edge {i} references missing from node {src!r}")
        if dst not in node_ids:
            errors.append(f"edge {i} references missing to node {dst!r}")
        if edge_type not in EDGE_TYPES:
            errors.append(f"edge {i} invalid type {edge_type!r}")
        ignored_legacy_fields = sorted(field for field in ("hard", "mode", "strength") if field in edge)
        if ignored_legacy_fields:
            warnings.append(
                f"edge {i} uses ignored legacy field(s) {', '.join(ignored_legacy_fields)}; use score on supports/contradicts edges"
            )
        src_type = nodes_by_id.get(src, {}).get("type") if isinstance(src, str) else None
        dst_type = nodes_by_id.get(dst, {}).get("type") if isinstance(dst, str) else None
        if src in candidate_ids and dst in goal_ids:
            if edge_type == "answers":
                candidate_goal_edges.add(src)
                candidate_goal_targets.setdefault(str(src), set()).add(str(dst))
                if dst in accepted_goal_ids:
                    candidate_accepted_goal_edges.add(src)
            else:
                errors.append(f"edge {i} candidate_solution -> goal must use answers")
        if edge_type == "answers" and (src_type != "candidate_solution" or dst_type != "goal"):
            errors.append(f"edge {i} answers edge must connect candidate_solution -> goal")
        if src_type == "test" and dst_type == "observation" and edge_type == "leads_to" and "not_run" in nodes_by_id.get(src, {}):
            errors.append(f"edge {i} gives not_run test {src} a result observation {dst}; a check that ran is not not_run")
        if src_type == "goal" and dst_type == "goal" and edge_type != "requires":
            errors.append(f"edge {i} goal -> goal must use requires; {src} -> {dst} uses {edge_type!r}")
        if src_type == "hypothesis" and dst_type == "goal":
            errors.append(
                f"edge {i} connects hypothesis {src} directly to goal {dst}; route hypotheses through tests/candidate nodes instead"
            )
        if src_type == "constraint" and dst_type == "goal" and edge_type == "requires":
            errors.append(
                f"edge {i} has constraint {src} requires goal {dst}; reverse direction to goal requires constraint"
            )

    seen_factor_ids: set[str] = set()
    for i, factor in enumerate(factors_raw):
        if not isinstance(factor, dict):
            continue
        factor_id = factor.get("id")
        if not isinstance(factor_id, str) or not factor_id:
            errors.append(f"factors[{i}] missing string id")
        elif factor_id in seen_factor_ids:
            errors.append(f"duplicate factor id {factor_id}")
        else:
            seen_factor_ids.add(factor_id)
    errors.extend(resolve_edge_groups(state)[1])

    unresolved_markers = ("not solved", "not established", "cannot establish", "insufficient evidence", "missing dependency", "undetermined", "not recoverable")
    epistemic_goal_markers = EPISTEMIC_GOAL_MARKERS
    for candidate in candidate_nodes:
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str):
            continue
        candidate_text = str(candidate.get("text") or "").lower()
        answer_kind = candidate.get("answer_kind")
        if answer_kind not in ANSWER_KINDS:
            # The schema already requires the field; this keeps the semantic message when it is present but wrong.
            errors.append(f"candidate_solution {candidate_id} answer_kind must be one of {sorted(ANSWER_KINDS)}, got {answer_kind!r}")
        goal_texts = [str(goals_by_id.get(goal_id, {}).get("text") or "").lower() for goal_id in candidate_goal_targets.get(candidate_id, set())]
        has_explicit_epistemic_goal = any(
            any(marker in goal_text for marker in epistemic_goal_markers)
            for goal_text in goal_texts
        )
        if any(marker in candidate_text for marker in unresolved_markers) and not has_explicit_epistemic_goal:
            warnings.append(
                f"candidate_solution {candidate_id} looks like an unresolved outcome, not an answer candidate; record it as a hypothesis blocker and claim no answer, unless the goal is explicitly epistemic"
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
            errors.append(f"candidate_solution {candidate_id} must connect to a goal with an answers edge")
        elif isinstance(accepted_goal_values, list) and candidate_id not in candidate_accepted_goal_edges:
            errors.append(f"candidate_solution {candidate_id} must connect to an accepted goal with an answers edge")

    try:
        assert_acyclic_premise_dependencies({goal_id: sorted(subs) for goal_id, subs in goal_requirements(state).items()})
    except ValueError as exc:
        errors.append(f"goal requires {exc}")

    solution_node_ids = {s.get("node") if isinstance(s, dict) else s for s in solutions_raw}
    for node_id in solution_node_ids:
        if node_id not in node_ids:
            errors.append(f"solutions references missing node {node_id!r}")
        elif node_id not in candidate_ids:
            errors.append(f"solutions references non-candidate node {node_id!r}; selected answers must be candidate_solution nodes")

    try:
        # Computed only to catch inputs the belief math rejects, such as an evidence cycle.
        node_effective_truth_costs(state)
    except Exception as exc:  # validation should report instead of throwing
        errors.append(f"belief computation failed: {exc}")

    return ValidationResult(errors=errors, warnings=warnings)
