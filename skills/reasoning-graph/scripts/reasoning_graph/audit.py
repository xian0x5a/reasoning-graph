"""Driver event and stop-policy audit."""

from __future__ import annotations

import math
from typing import Any

from .costs import compute_costs, probability_from_value
from .models import AUDIT_EVENT_ACTIONS, STOP_OUTCOMES, ValidationResult
from .policy import salient_clue_family_ids, selected_epistemic_candidate_ids, stop_reason_claims_exhaustion, strongest_candidate_belief, viable_candidate_ids
from .state import by_id
from .utils import as_string_list
from .validation import validate_state


def add_policy_violation(result: ValidationResult, message: str, severity: str) -> None:
    if severity == "error":
        result.errors.append(message)
    else:
        result.warnings.append(message)


def add_stop_policy_violation(result: ValidationResult, message: str, severity: str) -> None:
    add_policy_violation(result, message, severity)


def audit_stop_policy(
    state: dict[str, Any],
    live_frontier_items: list[dict[str, Any]],
    viable_count: int,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    result = ValidationResult(errors=errors, warnings=warnings)
    policy = state.get("stop_policy") if isinstance(state.get("stop_policy"), dict) else {}
    severity = str(policy.get("severity") or "warning")
    if severity not in {"warning", "error"}:
        severity = "warning"

    live_count = len(live_frontier_items)
    selected_epistemic = selected_epistemic_candidate_ids(state)
    if selected_epistemic and live_count:
        add_stop_policy_violation(
            result,
            "epistemic/unresolved candidate selected while event-reachable frontier remains live: "
            + ", ".join(item.get("id", "?") for item in live_frontier_items[:8])
            + ("..." if live_count > 8 else ""),
            severity,
        )

    if not policy:
        return result

    max_live = int(policy.get("max_live_frontier_items", 0))
    if live_count <= max_live:
        return result

    min_candidates = int(policy.get("min_viable_candidates", 0))
    threshold = probability_from_value(policy.get("belief_threshold")) or 0.0
    strongest_belief = strongest_candidate_belief(state)
    enough_candidates = min_candidates > 0 and viable_count >= min_candidates
    confident_candidate = threshold > 0 and strongest_belief >= threshold
    if not enough_candidates and not confident_candidate:
        add_stop_policy_violation(
            result,
            "stop_policy not satisfied: live_frontier={live} > max_live_frontier_items={max_live}, "
            "viable_candidates={viable} < min_viable_candidates={min_candidates}, "
            "strongest_belief={belief:.6g} < belief_threshold={threshold:.6g}".format(
                live=live_count,
                max_live=max_live,
                viable=viable_count,
                min_candidates=min_candidates,
                belief=strongest_belief,
                threshold=threshold,
            ),
            severity,
        )
    if policy.get("require_frontier_exhausted_for_epistemic_stop") is True and selected_epistemic:
        add_stop_policy_violation(
            result,
            "stop_policy requires frontier exhaustion for epistemic stop, but live frontier remains: "
            + ", ".join(item.get("id", "?") for item in live_frontier_items[:8])
            + ("..." if live_count > 8 else ""),
            severity,
        )
    return result


def audit_state(state: dict[str, Any]) -> tuple[ValidationResult, dict[str, int]]:
    """Audit compact strict-search events against graph/frontier state.

    This does not prove the model thought in UCS order, but it catches incoherent
    or purely decorative search traces: wrong pop order, orphan children, missing
    candidate-selection events, or frontier items that appear without an expansion.
    """

    base = validate_state(state)
    errors = list(base.errors)
    warnings = list(base.warnings)
    stats = {"events": 0, "pops": 0, "expansions": 0, "selections": 0}

    events = state.get("events")
    if not isinstance(events, list) or not events:
        errors.append("events must be a non-empty list for strict search audit")
        return ValidationResult(errors=errors, warnings=warnings), stats

    compute_costs(state)
    nodes = by_id(state.get("nodes", []), "node")
    items = by_id(state.get("frontier", []), "frontier item")
    edges = [edge for edge in state.get("edges", []) if isinstance(edge, dict)]
    edges_by_id = {edge.get("id"): edge for edge in edges if isinstance(edge.get("id"), str) and edge.get("id")}
    edge_ids = set(edges_by_id)
    frontier_ids_by_node: dict[str, set[str]] = {}
    for frontier_id, item in items.items():
        node_id = item.get("node")
        if isinstance(node_id, str):
            frontier_ids_by_node.setdefault(node_id, set()).add(frontier_id)
    tolerance = 1e-6

    seen_init = False
    seen_stop = False
    previous_step: int | None = None
    virtual_frontier: set[str] = set()
    popped_items: set[str] = set()
    expanded_items: set[str] = set()
    last_popped_item: str | None = None
    last_pop_cost: float | None = None
    last_evidence_version: Any = None
    event_added_nodes: set[str] = set()
    event_selected_nodes: set[str] = set()
    contradiction_added_steps_by_node: dict[str, list[int]] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        try:
            event_step = int(event.get("step"))
        except (TypeError, ValueError):
            continue
        for edge_id in event.get("add_edges") if isinstance(event.get("add_edges"), list) else []:
            edge = edges_by_id.get(str(edge_id))
            if not edge or (edge.get("type") or edge.get("label")) != "contradicts":
                continue
            target = edge.get("to")
            if isinstance(target, str):
                contradiction_added_steps_by_node.setdefault(target, []).append(event_step)

    branch_policy = state.get("branch_policy") if isinstance(state.get("branch_policy"), dict) else {}
    high_salience_min_children = int(branch_policy.get("high_salience_min_children", 3))
    branch_policy_severity = str(branch_policy.get("severity") or "warning")
    if branch_policy_severity not in {"warning", "error"}:
        branch_policy_severity = "warning"
    branch_policy_enforce_on = str(branch_policy.get("enforce_on") or "exhaustion_stop")
    if branch_policy_enforce_on not in {"exhaustion_stop", "always"}:
        branch_policy_enforce_on = "exhaustion_stop"
    deferred_branch_warnings: list[str] = []
    stop_reasons: list[str] = []
    stop_outcomes: list[str] = []

    def event_label(index: int, event: dict[str, Any]) -> str:
        return f"events[{index}] step={event.get('step')} action={event.get('action')}"

    def item_cost_changed_after(item_id: str, step: int) -> bool:
        item = items.get(item_id, {})
        node_id = item.get("node")
        if not isinstance(node_id, str):
            return False
        return any(change_step > step for change_step in contradiction_added_steps_by_node.get(node_id, []))

    for index, raw_event in enumerate(events):
        stats["events"] += 1
        if not isinstance(raw_event, dict):
            errors.append(f"events[{index}] must be object")
            continue
        event = raw_event
        label = event_label(index, event)

        step = event.get("step")
        if not isinstance(step, int):
            errors.append(f"{label}: step must be an integer")
        elif previous_step is not None and step <= previous_step:
            errors.append(f"{label}: step must strictly increase")
        if isinstance(step, int):
            previous_step = step

        action = event.get("action")
        if action not in AUDIT_EVENT_ACTIONS:
            errors.append(f"{label}: invalid action {action!r}")
            continue
        if seen_stop and action != "stop":
            errors.append(f"{label}: no events allowed after stop")

        if action == "init":
            if seen_init:
                errors.append(f"{label}: duplicate init event")
            init_frontier = as_string_list(event.get("frontier"), f"{label}.frontier", errors)
            for item_id in init_frontier:
                if item_id not in items:
                    errors.append(f"{label}: init references missing frontier item {item_id}")
                elif item_id in virtual_frontier:
                    errors.append(f"{label}: duplicate init frontier item {item_id}")
                else:
                    virtual_frontier.add(item_id)
            seen_init = True
            continue

        if not seen_init:
            errors.append(f"{label}: init event must appear before {action}")
            continue

        if action == "pop":
            item_id = event.get("item")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{label}: item must be a non-empty string")
                continue
            if item_id not in items:
                errors.append(f"{label}: references missing frontier item {item_id}")
                continue
            if item_id not in virtual_frontier:
                errors.append(f"{label}: item {item_id} is not in current virtual frontier")

            item = items[item_id]
            expected_cost = float(item.get("search_cost", item.get("path_cost", math.inf)))
            try:
                event_cost = float(event.get("cost"))
            except (TypeError, ValueError):
                errors.append(f"{label}: cost must be numeric")
                event_cost = expected_cost
            current_step = step if isinstance(step, int) else -1
            popped_cost_changed_later = item_cost_changed_after(item_id, current_step)
            if abs(event_cost - expected_cost) > tolerance and not popped_cost_changed_later:
                errors.append(f"{label}: cost {event_cost} != item search_cost {expected_cost}")

            if virtual_frontier:
                frontier_costs_changed_later = any(item_cost_changed_after(q, current_step) for q in virtual_frontier if q in items)
                lowest_cost = min(float(items[q].get("search_cost", items[q].get("path_cost", math.inf))) for q in virtual_frontier if q in items)
                if expected_cost > lowest_cost + tolerance and not frontier_costs_changed_later:
                    lowest_items = sorted(q for q in virtual_frontier if q in items and abs(float(items[q].get("search_cost", items[q].get("path_cost", math.inf))) - lowest_cost) <= tolerance)
                    errors.append(f"{label}: popped {item_id} cost {expected_cost} but lowest frontier search_cost is {lowest_cost} at {lowest_items[:3]}")

            evidence_version = event.get("evidence_version", item.get("evidence_version", state.get("evidence_version")))
            if last_pop_cost is not None and evidence_version == last_evidence_version and event_cost + tolerance < last_pop_cost:
                errors.append(f"{label}: pop cost decreased from {last_pop_cost} to {event_cost} without evidence_version change")
            last_pop_cost = event_cost
            last_evidence_version = evidence_version

            virtual_frontier.discard(item_id)
            popped_items.add(item_id)
            last_popped_item = item_id
            stats["pops"] += 1
            continue

        if action == "expand":
            item_id = event.get("item")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{label}: item must be a non-empty string")
                continue
            if item_id not in items:
                errors.append(f"{label}: references missing frontier item {item_id}")
                continue
            if item_id != last_popped_item:
                errors.append(f"{label}: expand must follow most recent pop ({last_popped_item}), got {item_id}")
            if item_id not in popped_items:
                errors.append(f"{label}: cannot expand unpopped item {item_id}")

            added_node_ids = as_string_list(event.get("add_nodes"), f"{label}.add_nodes", errors)
            added_node_types: set[str] = set()
            for node_id in added_node_ids:
                if node_id not in nodes:
                    errors.append(f"{label}: add_nodes references missing node {node_id}")
                else:
                    event_added_nodes.add(node_id)
                    node_type = nodes[node_id].get("type")
                    if isinstance(node_type, str):
                        added_node_types.add(node_type)
            added_edge_ids = as_string_list(event.get("add_edges"), f"{label}.add_edges", errors)
            for edge_id in added_edge_ids:
                if edge_ids and edge_id not in edge_ids:
                    errors.append(f"{label}: add_edges references missing edge id {edge_id}")
                elif not edge_ids:
                    warnings.append(f"{label}: add_edges cannot be cross-checked because edges have no ids")
            item_node_id = str(items[item_id].get("node") or "")
            added_node_set = set(added_node_ids)
            added_edges = [edges_by_id[edge_id] for edge_id in added_edge_ids if edge_id in edges_by_id]
            if item_node_id and added_node_set:
                has_outgoing_expansion_edge = any(
                    edge.get("from") == item_node_id and edge.get("to") in added_node_set
                    for edge in added_edges
                )
                if not has_outgoing_expansion_edge:
                    warnings.append(
                        f"{label}: expanded node {item_node_id} has no outgoing edge to added nodes; graph may hide that this assumption was explored"
                    )
            added_frontier_ids = as_string_list(event.get("add_frontier"), f"{label}.add_frontier", errors)
            for child_id in added_frontier_ids:
                child = items.get(child_id)
                if child is None:
                    errors.append(f"{label}: add_frontier references missing frontier item {child_id}")
                    continue
                if child_id in popped_items:
                    errors.append(f"{label}: add_frontier item {child_id} was already popped")
                    continue
                parent_id = child.get("parent")
                if parent_id is None or parent_id == "":
                    warnings.append(f"{label}: added frontier item {child_id} has no parent")
                elif parent_id != item_id:
                    warnings.append(f"{label}: added frontier item {child_id} parent is {parent_id}, expected {item_id}")
                virtual_frontier.add(child_id)

            contradiction_targets = {
                str(edge.get("to"))
                for edge in added_edges
                if (edge.get("type") or edge.get("label")) == "contradicts" and isinstance(edge.get("to"), str)
            }
            added_frontier_nodes = {
                str(items[child_id].get("node"))
                for child_id in added_frontier_ids
                if child_id in items and isinstance(items[child_id].get("node"), str)
            }
            # Older traces used no_reopen_reason/exhaustion_reason for this event-level escape.
            # Prefer no_new_work_reason; keep legacy acceptance so saved reports still audit cleanly.
            no_new_work_reason = str(
                event.get("no_new_work_reason")
                or event.get("no_reopen_reason")
                or event.get("exhaustion_reason")
                or ""
            ).strip()
            updated_node_specs = event.get("updated_nodes", [])
            if updated_node_specs is None:
                updated_node_specs = []
            if not isinstance(updated_node_specs, list):
                errors.append(f"{label}.updated_nodes must be a list when present")
                updated_node_specs = []
            updated_node_ids: set[str] = set()
            for update_index, update_spec in enumerate(updated_node_specs):
                if isinstance(update_spec, str):
                    update_node_id = update_spec
                elif isinstance(update_spec, dict) and isinstance(update_spec.get("id"), str):
                    update_node_id = str(update_spec["id"])
                    fields = update_spec.get("fields")
                    if fields is not None and (not isinstance(fields, list) or not all(isinstance(field, str) for field in fields)):
                        errors.append(f"{label}.updated_nodes[{update_index}].fields must be a list of strings when present")
                else:
                    errors.append(f"{label}.updated_nodes[{update_index}] must be a node id string or object with id")
                    continue
                if update_node_id not in nodes:
                    errors.append(f"{label}.updated_nodes[{update_index}] references missing node {update_node_id}")
                updated_node_ids.add(update_node_id)
            reranked_visited_nodes = contradiction_targets | updated_node_ids
            for target_node_id in sorted(reranked_visited_nodes):
                target_frontier_ids = frontier_ids_by_node.get(target_node_id, set())
                if not target_frontier_ids:
                    continue
                popped_target_items = target_frontier_ids & popped_items
                target_node = nodes.get(target_node_id, {})
                target_exhausted = target_node.get("exhausted") is True and bool(
                    str(target_node.get("exhaustion_reason") or "").strip()
                )
                if popped_target_items and target_node_id not in added_frontier_nodes and not (no_new_work_reason or target_exhausted):
                    warnings.append(
                        f"{label}: evidence updated visited node {target_node_id}; costs will recompute, but add frontier for new work, record no_new_work_reason, or mark the node exhausted with exhaustion_reason"
                    )

            terminal_or_contradicted = bool(added_node_types & {"candidate_solution"}) or bool(contradiction_targets)
            item_node = nodes.get(item_node_id, {})
            has_under_branching_escape = bool(str(event.get("under_branching_reason") or "").strip())
            existing_siblings = as_string_list(event.get("existing_sibling_frontier"), f"{label}.existing_sibling_frontier", errors)
            for sibling_id in existing_siblings:
                if sibling_id not in items:
                    errors.append(f"{label}: existing_sibling_frontier references missing frontier item {sibling_id}")
            has_under_branching_escape = has_under_branching_escape or bool(existing_siblings)
            item_exhausted = item_node.get("exhausted") is True and bool(
                str(item_node.get("exhaustion_reason") or "").strip()
            )
            has_under_branching_escape = has_under_branching_escape or item_exhausted
            if len(added_frontier_ids) == 1 and not terminal_or_contradicted and not has_under_branching_escape:
                deferred_branch_warnings.append(
                    f"{label}: one-child expansion may be under-branching; consider coarse sibling branches if any are meaningful"
                )
            is_high_salience = item_node_id in salient_clue_family_ids(state) or (
                (probability_from_value(item_node.get("salience")) or 0.0) >= 0.7
            )
            if is_high_salience and len(added_frontier_ids) < high_salience_min_children and not has_under_branching_escape:
                branch_result = ValidationResult(errors=[], warnings=[])
                add_policy_violation(
                    branch_result,
                    f"{label}: high-salience expansion added {len(added_frontier_ids)} child frontier item(s), below branch_policy.high_salience_min_children={high_salience_min_children}; add meaningful siblings, under_branching_reason, existing_sibling_frontier, or exhaustion_reason",
                    branch_policy_severity,
                )
                errors.extend(branch_result.errors)
                deferred_branch_warnings.extend(branch_result.warnings)
            try:
                popped_prior = float(nodes.get(item_node_id, {}).get("prior"))
            except (TypeError, ValueError):
                popped_prior = 0.0
            branch_penalized_by_contradiction = any(
                (edge.get("type") or edge.get("label")) == "contradicts"
                and edge.get("to") in ({item_node_id} | added_node_set)
                for edge in added_edges
            )
            if (
                popped_prior >= 0.65
                and branch_penalized_by_contradiction
                and not added_frontier_ids
                and not no_new_work_reason
                and not item_exhausted
            ):
                warnings.append(
                    f"{label}: high-prior branch {item_node_id} received a contradiction penalty with no follow-up frontier; ensure the negative result exhausts the whole clue family, not only one bounded interpretation"
                )

            expanded_items.add(item_id)
            last_popped_item = None
            stats["expansions"] += 1
            continue

        if action in {"select", "solution"}:
            if action == "solution":
                warnings.append(f"{label}: action 'solution' is deprecated; use 'select'")
            item_id = event.get("item")
            node_id = event.get("node")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{label}: item must be a non-empty string")
                continue
            if item_id not in items:
                errors.append(f"{label}: references missing frontier item {item_id}")
                continue
            item = items[item_id]
            if not isinstance(node_id, str) or not node_id:
                errors.append(f"{label}: node must be a non-empty string")
            elif node_id not in nodes:
                errors.append(f"{label}: references missing candidate_solution node {node_id}")
            else:
                node_type = nodes[node_id].get("type")
                if node_type != "candidate_solution":
                    errors.append(f"{label}: node {node_id} must be candidate_solution, got {node_type!r}")
                event_selected_nodes.add(node_id)
            try:
                event_cost = float(event.get("cost"))
            except (TypeError, ValueError):
                errors.append(f"{label}: cost must be numeric")
                event_cost = float(item.get("search_cost", item.get("path_cost", math.inf)))
            expected_cost = float(item.get("search_cost", item.get("path_cost", math.inf)))
            if abs(event_cost - expected_cost) > tolerance:
                errors.append(f"{label}: cost {event_cost} != item search_cost {expected_cost}")
            if item_id not in popped_items:
                warnings.append(f"{label}: selected item {item_id} was recorded before a pop event")
            stats["selections"] += 1
            continue

        if action == "stop":
            reason = event.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"{label}: stop reason must be non-empty")
            else:
                stop_reasons.append(reason)
            outcome = event.get("outcome")
            if outcome is None:
                warnings.append(f"{label}: stop outcome missing; using legacy reason-text fallback for exhaustion/coverage checks")
            elif not isinstance(outcome, str) or outcome not in STOP_OUTCOMES:
                errors.append(f"{label}: stop outcome must be one of {sorted(STOP_OUTCOMES)}, got {outcome!r}")
            else:
                stop_outcomes.append(outcome)
            seen_stop = True

    if not seen_stop:
        errors.append("strict search audit requires a stop event")
    if stop_outcomes:
        stop_claims_exhaustion = "frontier_exhausted" in stop_outcomes
    else:
        stop_claims_exhaustion = any(stop_reason_claims_exhaustion(reason) for reason in stop_reasons)
    has_selected_epistemic_candidate = bool(selected_epistemic_candidate_ids(state))
    emit_completion_coverage_warnings = branch_policy_enforce_on == "always" or stop_claims_exhaustion or has_selected_epistemic_candidate
    if deferred_branch_warnings and emit_completion_coverage_warnings:
        warnings.extend(deferred_branch_warnings)
    if stats["pops"] == 0:
        warnings.append("strict search audit saw no pop events")

    reachable_unpopped_frontier_items = [
        items[item_id]
        for item_id in sorted(virtual_frontier)
        if item_id in items and item_id not in popped_items
    ]
    for clue_id in sorted(salient_clue_family_ids(state)):
        clue_node = nodes.get(clue_id, {})
        if clue_node.get("exhausted") is True:
            if not str(clue_node.get("exhaustion_reason") or "").strip():
                warnings.append(f"salient clue family {clue_id} is marked exhausted but lacks exhaustion_reason")
            continue
        has_live_continuation = any(
            item.get("node") == clue_id or clue_id in (item.get("related") or [])
            for item in reachable_unpopped_frontier_items
        )
        if not has_live_continuation and emit_completion_coverage_warnings:
            warnings.append(
                f"salient clue family {clue_id} has no event-reachable unpopped frontier continuation and is not marked exhausted; bounded negative tests must not silently drop high-value clues"
            )

    report = state.get("report", {}) if isinstance(state.get("report"), dict) else {}
    report_candidates = report.get("candidates") if isinstance(report.get("candidates"), list) else []
    viable_candidates = viable_candidate_ids(state)
    report_viable_count = sum(
        1
        for candidate in report_candidates
        if isinstance(candidate, dict)
        and str(candidate.get("id") or "") in viable_candidates
    )
    candidate_count = max(len(viable_candidates), report_viable_count)
    stop_policy_result = audit_stop_policy(state, reachable_unpopped_frontier_items, candidate_count)
    errors.extend(stop_policy_result.errors)
    warnings.extend(stop_policy_result.warnings)
    if stats["selections"] == 0 and candidate_count > 0:
        warnings.append("strict search audit saw no candidate-selection events")
    if candidate_count >= 3:
        expected_branch_count = min(3, candidate_count)
        unvisited_candidates = sorted(
            node_id
            for node_id, node in nodes.items()
            if node.get("type") == "candidate_solution"
            and node_id in viable_candidates
            and node_id not in event_added_nodes
            and node_id not in event_selected_nodes
        )
        if unvisited_candidates:
            warnings.append(
                "candidate_solution nodes not added or selected by strict events: "
                + ", ".join(unvisited_candidates[:8])
                + ("..." if len(unvisited_candidates) > 8 else "")
            )
        if stats["expansions"] < expected_branch_count:
            warnings.append(
                f"strict search has {candidate_count} viable candidates but only {stats['expansions']} expansions; "
                f"expand/penalize at least {expected_branch_count} meaningful live branches when comparing candidates"
            )
        if stats["pops"] < expected_branch_count:
            warnings.append(
                f"strict search has {candidate_count} viable candidates but only {stats['pops']} pops; "
                f"early stop may be under-exploring competing branches"
            )

    return ValidationResult(errors=errors, warnings=warnings), stats
