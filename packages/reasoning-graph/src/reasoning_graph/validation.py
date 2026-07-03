"""Reasoning graph schema and policy validation."""

from __future__ import annotations

import json
from typing import Any

from .costs import (
    NODE_NON_PRIOR_PROBABILITY_FIELDS,
    compute_costs,
    item_has_explicit_effort_budget,
    likelihood_ratio_from_edge,
    likelihood_ratio_from_likelihood,
    likelihood_ratio_from_value,
    probability_cost,
    probability_from_value,
    text_looks_probe_like,
    uncertainty_cost_from_prior,
)
from .models import ANSWER_KINDS, EDGE_TYPES, EPISTEMIC_GOAL_MARKERS, FACTOR_AGGREGATION_KINDS, FACTOR_RELATIONS, NODE_TYPES, TEST_STATUSES, ValidationResult
from .policy import accepted_goal_ids, candidate_goal_targets, goal_accepts_answer_kind, goal_ids
from .schema_validation import state_schema_errors
from .utils import as_string_list


def edge_id_set(state: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for edge in state.get("edges", []):
        if isinstance(edge, dict) and isinstance(edge.get("id"), str) and edge.get("id"):
            ids.add(edge["id"])
    return ids


def validate_state(state: dict[str, Any]) -> ValidationResult:
    errors: list[str] = state_schema_errors(state) if isinstance(state, dict) else ["schema $: state must be an object"]
    warnings: list[str] = []
    nodes_raw = state.get("nodes", [])
    edges_raw = state.get("edges", [])
    frontier_raw = state.get("frontier", [])
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
    if not isinstance(frontier_raw, list):
        errors.append("frontier must be a list")
        frontier_raw = []
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
        if node_type == "assumption":
            if "prior" not in node:
                warnings.append(f"assumption {node_id} missing prior")
            else:
                try:
                    uncertainty_cost_from_prior(node["prior"])
                except ValueError as exc:
                    errors.append(f"assumption {node_id}: {exc}")
        for probability_field in NODE_NON_PRIOR_PROBABILITY_FIELDS:
            if probability_field in node:
                try:
                    probability_cost(node[probability_field], probability_field)
                except ValueError as exc:
                    errors.append(f"node {node_id or i}: {exc}")
        if "clue_family" in node and not isinstance(node.get("clue_family"), bool):
            errors.append(f"node {node_id or i} clue_family must be boolean when present")
        if "salience" in node:
            try:
                salience = float(node.get("salience"))
                if not 0 <= salience <= 1:
                    errors.append(f"node {node_id or i} salience must be in [0, 1]")
            except (TypeError, ValueError):
                errors.append(f"node {node_id or i} salience must be numeric when present")
        if "exhausted" in node and not isinstance(node.get("exhausted"), bool):
            errors.append(f"node {node_id or i} exhausted must be boolean when present")
        if node.get("exhausted") is True and not str(node.get("exhaustion_reason") or "").strip():
            warnings.append(f"node {node_id or i} exhausted=true should include exhaustion_reason")
        if "status" in node and node_type != "test":
            errors.append(f"node {node_id or i} has status but only test nodes may use status")
        if node_type == "test":
            status = node.get("status")
            if status is None:
                warnings.append(f"test {node_id} missing status; use proposed/performed/inconclusive")
            elif str(status) not in TEST_STATUSES:
                warnings.append(f"test {node_id} has non-standard status {status!r}")

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
        for key in ("accepted_goals", "preferred_goals"):
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
        for key in ("min_viable_candidates", "max_live_frontier_items"):
            if key in stop_policy:
                value = stop_policy.get(key)
                if not isinstance(value, int) or value < 0:
                    errors.append(f"stop_policy.{key} must be a non-negative integer")
        if "belief_threshold" in stop_policy:
            probability = probability_from_value(stop_policy.get("belief_threshold"))
            if probability is None or probability <= 0:
                errors.append("stop_policy.belief_threshold must be in (0, 1]")
        for key in ("require_frontier_exhausted_for_epistemic_stop",):
            if key in stop_policy and not isinstance(stop_policy.get(key), bool):
                errors.append(f"stop_policy.{key} must be boolean when present")
        if "severity" in stop_policy and stop_policy.get("severity") not in {"warning", "error"}:
            errors.append("stop_policy.severity must be 'warning' or 'error' when present")
    branch_policy = state.get("branch_policy", {})
    if branch_policy is not None:
        if not isinstance(branch_policy, dict):
            errors.append("branch_policy must be object when present")
            branch_policy = {}
        for key in ("high_salience_min_children",):
            if key in branch_policy:
                value = branch_policy.get(key)
                if not isinstance(value, int) or value < 0:
                    errors.append(f"branch_policy.{key} must be a non-negative integer")
        if "low_prior_wildcard_required" in branch_policy and not isinstance(branch_policy.get("low_prior_wildcard_required"), bool):
            errors.append("branch_policy.low_prior_wildcard_required must be boolean when present")
        if "severity" in branch_policy and branch_policy.get("severity") not in {"warning", "error"}:
            errors.append("branch_policy.severity must be 'warning' or 'error' when present")
        if "enforce_on" in branch_policy and branch_policy.get("enforce_on") not in {"exhaustion_stop", "always"}:
            errors.append("branch_policy.enforce_on must be 'exhaustion_stop' or 'always' when present")
    search_policy = state.get("search_policy", {})
    if search_policy is not None:
        if not isinstance(search_policy, dict):
            errors.append("search_policy must be object when present")
            search_policy = {}
        if "max_probe_concurrency" in search_policy:
            value = search_policy.get("max_probe_concurrency")
            if not isinstance(value, int) or value < 1:
                errors.append("search_policy.max_probe_concurrency must be a positive integer")
    accepted_goal_values = goal_policy.get("accepted_goals") if isinstance(goal_policy, dict) else None
    accepted_goal_ids = {str(goal_id) for goal_id in accepted_goal_values} if isinstance(accepted_goal_values, list) else set(goal_ids)
    goals_by_id = {node.get("id"): node for node in nodes_raw if isinstance(node, dict) and node.get("type") == "goal"}
    candidate_nodes = [node for node in nodes_raw if isinstance(node, dict) and node.get("type") == "candidate_solution"]
    candidate_ids = {node.get("id") for node in candidate_nodes}
    candidate_goal_edges: set[str] = set()
    candidate_accepted_goal_edges: set[str] = set()
    candidate_goal_targets: dict[str, set[str]] = {}
    leads_to_pairs: set[tuple[str, str]] = set()
    relation_pairs: set[tuple[str, str, str]] = set()
    for i, edge in enumerate(edges_raw):
        if not isinstance(edge, dict):
            errors.append(f"edges[{i}] must be object")
            continue
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
                f"edge {i} uses ignored legacy field(s) {', '.join(ignored_legacy_fields)}; use likelihood/likelihood_ratio or target posterior for numeric belief updates"
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
        if edge_type == "leads_to" and isinstance(src, str) and isinstance(dst, str):
            leads_to_pairs.add((src, dst))
        src_type = next((node.get("type") for node in nodes_raw if isinstance(node, dict) and node.get("id") == src), None)
        dst_type = next((node.get("type") for node in nodes_raw if isinstance(node, dict) and node.get("id") == dst), None)
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
        if src_type == "assumption" and dst_type == "goal":
            errors.append(
                f"edge {i} connects assumption {src} directly to goal {dst}; route assumptions through tests/derived/candidate nodes instead"
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
            if "posterior" in nodes_by_id.get(target, {}):
                warnings.append(
                    f"factor {factor_id or i} targets node {target} with explicit posterior; "
                    "posterior overrides factor costs"
                )

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
    strict_answer_kind_required = isinstance(stop_policy, dict) and stop_policy.get("severity") == "error"
    for candidate in candidate_nodes:
        candidate_id = candidate.get("id")
        if not isinstance(candidate_id, str):
            continue
        candidate_text = str(candidate.get("text") or "").lower()
        answer_kind = candidate.get("answer_kind")
        if answer_kind is None:
            message = f"candidate_solution {candidate_id} missing answer_kind; use one of {sorted(ANSWER_KINDS)}"
            if strict_answer_kind_required:
                errors.append(message)
            else:
                warnings.append(message)
        elif answer_kind not in ANSWER_KINDS:
            errors.append(f"candidate_solution {candidate_id} answer_kind must be one of {sorted(ANSWER_KINDS)}, got {answer_kind!r}")
        goal_texts = [str(goals_by_id.get(goal_id, {}).get("text") or "").lower() for goal_id in candidate_goal_targets.get(candidate_id, set())]
        has_explicit_epistemic_goal = any(
            any(marker in goal_text for marker in epistemic_goal_markers)
            for goal_text in goal_texts
        )
        if any(marker in candidate_text for marker in unresolved_markers) and not has_explicit_epistemic_goal:
            warnings.append(
                f"candidate_solution {candidate_id} looks like an unresolved/stop outcome, not an answer candidate; use a derived blocker plus stop event unless the goal is explicitly epistemic"
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

    frontier_ids: set[str] = set()
    for i, item in enumerate(frontier_raw):
        if not isinstance(item, dict):
            errors.append(f"frontier[{i}] must be object")
            continue
        item_id = item.get("id")
        node = item.get("node")
        parent = item.get("parent")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"frontier[{i}] missing string id")
        elif item_id in frontier_ids:
            errors.append(f"duplicate frontier id {item_id}")
        else:
            frontier_ids.add(item_id)
        if node not in node_ids:
            errors.append(f"frontier item {item_id or i} references missing node {node!r}")
        if parent is not None and parent != "" and parent not in frontier_ids:
            # Parent may appear later; check all ids after collection below.
            pass
        for forbidden_field in ("next_action", "expansion_hint", "context", "additional_info", "focus"):
            if forbidden_field in item:
                errors.append(f"frontier item {item_id or i} uses forbidden field {forbidden_field}; use node plus related node ids only")
        related = item.get("related", [])
        if "related" in item:
            if not isinstance(related, list):
                errors.append(f"frontier item {item_id or i} related must be a list of node ids")
            else:
                for related_index, related_node in enumerate(related):
                    if related_node not in node_ids:
                        errors.append(f"frontier item {item_id or i} related[{related_index}] references missing node {related_node!r}")
        scratch = item.get("scratch", [])
        if "scratch" in item:
            if not isinstance(scratch, list):
                errors.append(f"frontier item {item_id or i} scratch must be a list of strings")
            else:
                for scratch_index, note in enumerate(scratch):
                    if not isinstance(note, str) or not note.strip():
                        errors.append(f"frontier item {item_id or i} scratch[{scratch_index}] must be a non-empty string")
        node_obj = nodes_by_id.get(str(node), {}) if isinstance(node, str) else {}
        scratch_text = " ".join(note for note in scratch if isinstance(note, str)) if isinstance(scratch, list) else ""
        if text_looks_probe_like(node_obj.get("text"), item.get("summary"), scratch_text) and not item_has_explicit_effort_budget(item):
            warnings.append(
                f"frontier item {item_id or i} looks probe/brute-force-like; add cost_components.effort_budget and budget metadata so frontier priority prices bounded effort"
            )

    all_frontier_ids = {item.get("id") for item in frontier_raw if isinstance(item, dict)}
    for item in frontier_raw:
        if not isinstance(item, dict):
            continue
        parent = item.get("parent")
        if parent is not None and parent != "" and parent not in all_frontier_ids:
            errors.append(f"frontier item {item.get('id')} references missing parent {parent!r}")

    solution_node_ids = {s.get("node") if isinstance(s, dict) else s for s in solutions_raw}
    for node_id in solution_node_ids:
        if node_id not in node_ids:
            errors.append(f"solutions references missing node {node_id!r}")
        elif node_id not in candidate_ids:
            errors.append(f"solutions references non-candidate node {node_id!r}; selected answers must be candidate_solution nodes")

    try:
        compute_costs(json.loads(json.dumps(state)))
    except Exception as exc:  # validation should report instead of throwing
        errors.append(f"cost computation failed: {exc}")

    return ValidationResult(errors=errors, warnings=warnings)
