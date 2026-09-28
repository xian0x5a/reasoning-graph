"""Reasoning graph schema and policy validation."""

from __future__ import annotations

from typing import Any

from .costs import (
    NODE_SCORE_FIELDS,
    assert_acyclic_premise_dependencies,
    claim_beliefs,
    likelihood_ratio_from_edge,
    likelihood_ratio_from_likelihood,
    likelihood_ratio_from_value,
    nodes_with_belief_sources,
    probability_cost,
)
from .models import ANSWER_KINDS, BELIEF_NODE_TYPES, EDGE_TYPES, EPISTEMIC_GOAL_MARKERS, FACTOR_AGGREGATION_KINDS, FACTOR_RELATIONS, NODE_TYPES, ValidationResult
from .policy import accepted_goal_ids, candidate_goal_targets, goal_accepts_answer_kind, goal_ids, goal_requirements
from .schema_validation import state_schema_errors
from .utils import as_string_list


# Stored beliefs are rounded to 6 places when written.
BELIEF_TOLERANCE = 1e-6
# Belief did not separate right answers from wrong ones and a same-model reviewer shared the
# author's misreading (issue #37), so neither gates a stop. A state that still asks for them fails.
REMOVED_STOP_POLICY_KEYS = ("belief_threshold", "require_review")


def edge_id_set(state: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for edge in state.get("edges", []):
        if isinstance(edge, dict) and isinstance(edge.get("id"), str) and edge.get("id"):
            ids.add(edge["id"])
    return ids


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
        errors.append("premise_groups is not supported; use factors with relation='leads_to'")

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
        if "posterior" in node:
            errors.append(f"node {node_id or i}: posterior was removed; belief always follows prior, premises, and evidence; delete the field")
        for probability_field in NODE_SCORE_FIELDS:
            if probability_field in node:
                try:
                    probability_cost(node[probability_field], probability_field)
                except ValueError as exc:
                    errors.append(f"node {node_id or i}: {exc}")
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
    stop_policy = state.get("stop_policy", {})
    if stop_policy is not None:
        if not isinstance(stop_policy, dict):
            errors.append("stop_policy must be object when present")
            stop_policy = {}
        if "min_viable_candidates" in stop_policy:
            value = stop_policy.get("min_viable_candidates")
            if not isinstance(value, int) or value < 0:
                errors.append("stop_policy.min_viable_candidates must be a non-negative integer")
        for removed_key in REMOVED_STOP_POLICY_KEYS:
            if removed_key in stop_policy:
                errors.append(f"stop_policy.{removed_key} was removed: no belief level or review gates a stop; delete the key")
        if "severity" in stop_policy and stop_policy.get("severity") not in {"warning", "error"}:
            errors.append("stop_policy.severity must be 'warning' or 'error' when present")
    events = state.get("events")
    for i, event in enumerate(events if isinstance(events, list) else []):
        if isinstance(event, dict) and event.get("action") == "review":
            errors.append(f"events[{i}] is a review event, which was removed: no review gates a stop; delete the event")
    accepted_goal_values = goal_policy.get("accepted_goals") if isinstance(goal_policy, dict) else None
    accepted_goal_ids = {str(goal_id) for goal_id in accepted_goal_values} if isinstance(accepted_goal_values, list) else set(goal_ids)
    goals_by_id = {node.get("id"): node for node in nodes_raw if isinstance(node, dict) and node.get("type") == "goal"}
    candidate_nodes = [node for node in nodes_raw if isinstance(node, dict) and node.get("type") == "candidate_solution"]
    candidate_ids = {node.get("id") for node in candidate_nodes}
    candidate_goal_edges: set[str] = set()
    candidate_accepted_goal_edges: set[str] = set()
    candidate_goal_targets: dict[str, set[str]] = {}
    relation_pairs: set[tuple[str, str, str]] = set()
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
                f"edge {i} uses ignored legacy field(s) {', '.join(ignored_legacy_fields)}; use likelihood/likelihood_ratio for numeric belief updates"
            )
        has_likelihood_update = "likelihood_ratio" in edge or "likelihood" in edge
        if has_likelihood_update:
            try:
                likelihood_ratio = likelihood_ratio_from_edge(edge) if "likelihood" in edge else likelihood_ratio_from_value(edge.get("likelihood_ratio"), "likelihood_ratio")
            except ValueError as exc:
                errors.append(f"edge {i}: {exc}")
                likelihood_ratio = None
            if edge_type not in {"supports", "contradicts"}:
                errors.append(f"edge {i} likelihood/likelihood_ratio is only valid on supports/contradicts edges")
            elif likelihood_ratio is not None:
                if edge_type == "supports" and likelihood_ratio <= 1:
                    errors.append(f"edge {i} supports likelihood ratio must be > 1")
                if edge_type == "contradicts" and likelihood_ratio >= 1:
                    errors.append(f"edge {i} contradicts likelihood ratio must be in (0, 1)")
        if isinstance(src, str) and isinstance(dst, str) and isinstance(edge_type, str):
            relation_pairs.add((src, dst, edge_type))
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

    grouped_leads_to_inputs_by_target: dict[str, set[str]] = {}
    seen_factor_ids: set[str] = set()
    grouped_likelihood_inputs_by_target_relation: dict[tuple[str, str], set[str]] = {}
    for i, factor in enumerate(factors_raw):
        if not isinstance(factor, dict):
            errors.append(f"factors[{i}] must be object")
            continue
        factor_id = factor.get("id")
        if not isinstance(factor_id, str) or not factor_id:
            errors.append(f"factors[{i}] missing string id")
        elif factor_id in seen_factor_ids:
            errors.append(f"duplicate factor id {factor_id}")
        else:
            seen_factor_ids.add(factor_id)

        relation = factor.get("relation")
        if relation not in FACTOR_RELATIONS:
            errors.append(f"factors[{i}].relation must be one of {sorted(FACTOR_RELATIONS)}, got {relation!r}")
            relation_valid = False
        else:
            relation_valid = True

        target = factor.get("target")
        if not isinstance(target, str) or not target:
            errors.append(f"factors[{i}].target must be a non-empty string")
            target_valid = False
        elif target not in node_ids:
            errors.append(f"factors[{i}].target references missing node {target!r}")
            target_valid = False
        else:
            target_valid = True

        inputs = factor.get("inputs")
        if not isinstance(inputs, list) or len(inputs) < 2:
            errors.append(f"factors[{i}].inputs must be a list of at least two node ids")
            input_ids: list[str] = []
        else:
            input_ids = []
            for input_index, input_id in enumerate(inputs):
                if not isinstance(input_id, str) or not input_id:
                    errors.append(f"factors[{i}].inputs[{input_index}] must be a non-empty string")
                    continue
                input_ids.append(input_id)
                if input_id not in node_ids:
                    errors.append(f"factors[{i}].inputs[{input_index}] references missing node {input_id!r}")
                if target_valid and relation_valid:
                    if input_id == target:
                        errors.append(f"factors[{i}] must not include target {target!r} as an input")
                    elif input_id in node_ids and (input_id, target, str(relation)) not in relation_pairs:
                        errors.append(
                            f"factors[{i}] input {input_id!r} must have a {relation} edge to target {target!r}"
                        )
            if len(set(input_ids)) != len(input_ids):
                errors.append(f"factors[{i}].inputs must not contain duplicates")

        if target_valid and relation_valid and input_ids:
            if relation == "leads_to":
                grouped_for_target = grouped_leads_to_inputs_by_target.setdefault(str(target), set())
                overlap = grouped_for_target.intersection(input_ids)
                if overlap:
                    errors.append(
                        f"leads_to factors for target {target!r} overlap on input(s) {', '.join(sorted(overlap))}"
                    )
                grouped_for_target.update(input_ids)
            elif isinstance(relation, str) and relation in {"supports", "contradicts"}:
                grouped_key = (str(target), str(relation))
                grouped_for_relation = grouped_likelihood_inputs_by_target_relation.setdefault(grouped_key, set())
                overlap = grouped_for_relation.intersection(input_ids)
                if overlap:
                    errors.append(
                        f"{relation} factors for target {target!r} overlap on input(s) {', '.join(sorted(overlap))}"
                    )
                grouped_for_relation.update(input_ids)

        if "effective_truth_cost" in factor:
            errors.append(f"factors[{i}] must not set effective_truth_cost; it is computed from aggregation")
        if "likelihood_ratio" in factor:
            errors.append(
                f"factors[{i}] must not set likelihood_ratio directly; use aggregation.if_target_true and aggregation.if_target_false"
            )
        aggregation = factor.get("aggregation")
        if not isinstance(aggregation, dict):
            errors.append(f"factors[{i}].aggregation must be an object")
        else:
            if "likelihood_ratio" in aggregation:
                errors.append(
                    f"factors[{i}].aggregation must not set likelihood_ratio directly; use if_target_true and if_target_false"
                )
            aggregation_kind = aggregation.get("kind")
            if aggregation_kind not in FACTOR_AGGREGATION_KINDS:
                errors.append(
                    f"factors[{i}].aggregation.kind must be one of {sorted(FACTOR_AGGREGATION_KINDS)}, got {aggregation_kind!r}"
                )
            elif relation == "leads_to":
                if aggregation_kind != "joint_probability":
                    errors.append(f"factors[{i}].aggregation.kind must be 'joint_probability' for leads_to factors")
                if "probability" not in aggregation:
                    errors.append(f"factors[{i}].aggregation.probability missing")
                else:
                    try:
                        probability_cost(aggregation["probability"], f"factors[{i}].aggregation.probability")
                    except ValueError as exc:
                        errors.append(f"factors[{i}]: {exc}")
            elif isinstance(relation, str) and relation in {"supports", "contradicts"}:
                if aggregation_kind != "likelihood":
                    errors.append(f"factors[{i}].aggregation.kind must be 'likelihood' for supports/contradicts factors")
                else:
                    try:
                        likelihood_ratio = likelihood_ratio_from_likelihood(aggregation, f"factors[{i}].aggregation")
                    except ValueError as exc:
                        errors.append(f"factors[{i}]: {exc}")
                        likelihood_ratio = None
                    if likelihood_ratio is not None:
                        if relation == "supports" and likelihood_ratio <= 1:
                            errors.append(f"factors[{i}] supports likelihood ratio must be > 1")
                        if relation == "contradicts" and likelihood_ratio >= 1:
                            errors.append(f"factors[{i}] contradicts likelihood ratio must be in (0, 1)")
        if not str(factor.get("reason") or "").strip():
            warnings.append(
                f"factor {factor_id or i} should include reason explaining why inputs are grouped"
            )

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
                f"candidate_solution {candidate_id} looks like an unresolved/stop outcome, not an answer candidate; use a hypothesis blocker plus stop event unless the goal is explicitly epistemic"
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
        beliefs = claim_beliefs(state)
        for node_id, node in nodes_by_id.items():
            if "belief" not in node:
                continue
            if node_id not in beliefs:
                errors.append(f"{node.get('type')} node {node_id} has belief; only claims carry a computed belief")
            elif not isinstance(node["belief"], (int, float)) or abs(node["belief"] - beliefs[node_id]) > BELIEF_TOLERANCE:
                errors.append(
                    f"stale belief on {node_id}: stored {node['belief']!r}, computed {beliefs[node_id]}; "
                    "after a hand edit, run `reasoning-graph refresh <state>`"
                )
        grounded_nodes = nodes_with_belief_sources(state)
        for node_id, node in nodes_by_id.items():
            if node.get("type") in BELIEF_NODE_TYPES and node_id not in grounded_nodes:
                errors.append(
                    f"{node.get('type')} node {node_id} requires a belief source: "
                    "a local prior, belief-bearing leads_to premises, "
                    "or a calibrated joint-probability factor"
                )
    except Exception as exc:  # validation should report instead of throwing
        errors.append(f"belief computation failed: {exc}")

    return ValidationResult(errors=errors, warnings=warnings)
