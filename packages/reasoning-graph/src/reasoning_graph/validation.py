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
from .utils import as_string_list


# Computed numbers the state used to hold. They are computed when the graph is rendered, for
# the reader: an agent that sees them tunes scores until a number moves (issue #37).
REMOVED_REPORT_CANDIDATE_FIELDS = ("belief", "truth_cost", "effective_truth_cost", "weight")


def edge_id_set(state: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for edge in state.get("edges", []):
        if isinstance(edge, dict) and isinstance(edge.get("id"), str) and edge.get("id"):
            ids.add(edge["id"])
    return ids


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
        owner = f"edge {edge.get('id') or index}"
        errors.extend(removed_score_field_message(owner, field) for field in REMOVED_EDGE_SCORE_FIELDS if field in edge)
        if "reasoning" in edge:
            # `reasoning` was 45% of edge bytes and mostly restated the two node texts (issue #37).
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
        # It configured the stop gate, which went with the stop certificate (issue #38).
        errors.append("stop_policy was removed: nothing gates a stop; audit checks the answer summary.answer claims; delete the field")
    summary, report = (state.get(section) if isinstance(state.get(section), dict) else {} for section in ("summary", "report"))
    if str(report.get("answer") or "").strip() and not str(summary.get("answer") or "").strip():
        # The view shows either answer, so a report answer without the claim would be shown unchecked.
        errors.append("report.answer is set while summary.answer is empty; summary.answer is the claim, set it with the patch key answer")
    events = state.get("events")
    for i, event in enumerate(events if isinstance(events, list) else []):
        if isinstance(event, dict) and event.get("action") == "review":
            errors.append(f"events[{i}] is a review event, which was removed: no review gates a stop; delete the event")
        if isinstance(event, dict) and event.get("action") == "rank":
            errors.append(f"events[{i}] is a rank event, which was removed: the state holds no computed belief; delete the event")
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
        edge_id = edge.get("id")
        if isinstance(edge_id, str) and edge_id:
            if edge_id in seen_edge_ids:
                errors.append(f"duplicate edge id {edge_id}")
            seen_edge_ids.add(edge_id)
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

    report = state.get("report")
    if report is not None and not isinstance(report, dict):
        errors.append("report must be object when present")
    elif isinstance(report, dict):
        node_texts = {str(node.get("text") or "").strip() for node in nodes_by_id.values()}
        report_candidates = report.get("candidates")
        if report_candidates is not None and not isinstance(report_candidates, list):
            errors.append("report.candidates must be a list when present")
        for index, row in enumerate(report_candidates if isinstance(report_candidates, list) else []):
            if not isinstance(row, dict):
                errors.append(f"report.candidates[{index}] must be object")
                continue
            errors.extend(
                f"report.candidates[{index}].{field} was removed; ranking is computed when the graph is rendered; delete the field"
                for field in REMOVED_REPORT_CANDIDATE_FIELDS
                if field in row
            )
            row_id = row.get("id")
            if row_id is not None and row_id not in candidate_ids:
                errors.append(f"report.candidates[{index}].id references missing candidate_solution {row_id!r}")
            if "path_nodes" in row:
                for path_index, path_node in enumerate(as_string_list(row.get("path_nodes"), f"report.candidates[{index}].path_nodes", errors)):
                    if path_node not in node_ids:
                        errors.append(f"report.candidates[{index}].path_nodes[{path_index}] references missing node {path_node!r}")
        if "winning_path" in report:
            for index, step in enumerate(as_string_list(report.get("winning_path"), "report.winning_path", errors)):
                if step not in node_ids and step.strip() not in node_texts:
                    errors.append(f"report.winning_path[{index}] {step!r} matches no node id or exact node text")

    for section, keys in (("presentation", ("include_nodes", "highlight_nodes", "dim_nodes")), ("view", ("winning_path", "dimmed_branches"))):
        metadata = state.get(section)
        if metadata is None:
            continue
        if not isinstance(metadata, dict):
            errors.append(f"{section} must be object when present")
            continue
        for key in keys:
            if key not in metadata:
                continue
            for index, node_ref in enumerate(as_string_list(metadata.get(key), f"{section}.{key}", errors)):
                if node_ref not in node_ids:
                    errors.append(f"{section}.{key}[{index}] references missing node {node_ref!r}")

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
