"""Driver event and stop-policy audit."""

from __future__ import annotations

import json
import math
from typing import Any

from .costs import compute_costs, probability_from_value
from .frontier import expansion_signature
from .models import AUDIT_EVENT_ACTIONS, STOP_OUTCOMES, ValidationResult
from .policy import best_epistemic_candidate_ids, ranked_viable_candidates, salient_clue_family_ids, stop_reason_claims_exhaustion, strongest_candidate_belief, viable_candidate_ids
from .state import by_id
from .utils import as_string_list
from .validation import validate_state


def _event_ids(event: dict[str, Any], field: str) -> set[str]:
    values = event.get(field)
    if not isinstance(values, list):
        return set()
    return {str(value) for value in values if isinstance(value, str) and value}


def _remove_items_by_id(items: Any, removed_ids: set[str]) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []
    return [
        item
        for item in items
        if not isinstance(item, dict) or str(item.get("id") or "") not in removed_ids
    ]


def _snapshot_specs(event: dict[str, Any], field: str) -> list[dict[str, Any]]:
    snapshots = event.get(field)
    if not isinstance(snapshots, list):
        return []
    return [snapshot for snapshot in snapshots if isinstance(snapshot, dict)]


def _restore_snapshots(
    items: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(item.get("id")): item for item in items if isinstance(item.get("id"), str)}
    for snapshot in snapshots:
        item_id = snapshot.get("id")
        if not isinstance(item_id, str):
            continue
        before = snapshot.get("before")
        if before is None:
            by_id.pop(item_id, None)
        elif isinstance(before, dict):
            by_id[item_id] = json.loads(json.dumps(before))
    return list(by_id.values())


def _undo_replay_event(state: dict[str, Any], event: dict[str, Any]) -> None:
    """Undo one event so state reflects the graph before that event.

    The final state stores graph objects once, while events store insertion ids. Replaying
    backwards lets audit evaluate each pop against only evidence that existed at that time.
    Update snapshots are emitted by the CLI for mutable node/factor replacements; old traces
    without snapshots retain their final value because their prior value is unknowable.
    """

    action = event.get("action")
    if action not in {"seed", "expand"}:
        return

    node_snapshots = _snapshot_specs(event, "updated_node_snapshots")
    if not node_snapshots:
        node_snapshots = [
            snapshot
            for snapshot in _snapshot_specs(event, "updated_nodes")
            if isinstance(snapshot.get("before"), dict)
        ]
    if node_snapshots:
        state["nodes"] = _restore_snapshots(state.get("nodes", []), node_snapshots)

    factor_snapshots = _snapshot_specs(event, "updated_factor_snapshots")
    if factor_snapshots:
        state["factors"] = _restore_snapshots(state.get("factors", []), factor_snapshots)

    state["nodes"] = _remove_items_by_id(state.get("nodes", []), _event_ids(event, "add_nodes"))
    removed_edge_ids = _event_ids(event, "add_edges")
    retained_edge_ids: set[str] = set()
    factors = [factor for factor in state.get("factors", []) if isinstance(factor, dict)]
    for edge in state.get("edges", []):
        if not isinstance(edge, dict) or str(edge.get("id") or "") not in removed_edge_ids:
            continue
        edge_type = edge.get("type") or edge.get("label")
        if any(
            factor.get("relation") == edge_type
            and factor.get("target") == edge.get("to")
            and isinstance(factor.get("inputs"), list)
            and edge.get("from") in factor["inputs"]
            for factor in factors
        ):
            retained_edge_ids.add(str(edge["id"]))
    state["edges"] = _remove_items_by_id(state.get("edges", []), removed_edge_ids - retained_edge_ids)


def _historical_state_before_event(state: dict[str, Any], events: list[Any], event_index: int) -> dict[str, Any]:
    historical = json.loads(json.dumps(state))
    for event in reversed(events[event_index:]):
        if isinstance(event, dict):
            _undo_replay_event(historical, event)
    return historical


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
    best_epistemic = best_epistemic_candidate_ids(state)
    if best_epistemic and live_count:
        add_stop_policy_violation(
            result,
            "best candidate answers an epistemic/unresolved goal while event-reachable frontier remains live: "
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
    if policy.get("require_frontier_exhausted_for_epistemic_stop") is True and best_epistemic:
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

    This does not prove the model used best-first order internally, but it catches incoherent
    or purely decorative search traces: wrong pop order, orphan children, missing
    candidate-rank events, or frontier items that appear without an expansion.
    """

    base = validate_state(state)
    errors = list(base.errors)
    warnings = list(base.warnings)
    stats = {"events": 0, "pops": 0, "expansions": 0, "rankings": 0}
    if errors:
        return ValidationResult(errors=errors, warnings=warnings), stats

    events = state.get("events")
    if not isinstance(events, list) or not events:
        errors.append("events must be a non-empty list for strict search audit")
        return ValidationResult(errors=errors, warnings=warnings), stats

    costed_state = json.loads(json.dumps(state))
    compute_costs(costed_state)
    nodes = by_id(state.get("nodes", []), "node")
    items = by_id(costed_state.get("frontier", []), "frontier item")
    edges = [edge for edge in state.get("edges", []) if isinstance(edge, dict)]
    edges_by_id = {edge.get("id"): edge for edge in edges if isinstance(edge.get("id"), str) and edge.get("id")}
    edge_ids = set(edges_by_id)
    factors = [factor for factor in state.get("factors", []) if isinstance(factor, dict)]
    factors_by_id = {
        factor.get("id"): factor
        for factor in factors
        if isinstance(factor.get("id"), str) and factor.get("id")
    }
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
    in_flight_items: set[str] = set()
    expanded_items: set[str] = set()
    last_popped_item: str | None = None
    event_added_nodes: set[str] = set()
    event_ranked_nodes: set[str] = set()

    search_policy = state.get("search_policy") if isinstance(state.get("search_policy"), dict) else {}
    default_max_probe_concurrency = 3
    policy_max_probe_concurrency = search_policy.get("max_probe_concurrency", default_max_probe_concurrency)
    if not isinstance(policy_max_probe_concurrency, int) or policy_max_probe_concurrency < 1:
        policy_max_probe_concurrency = default_max_probe_concurrency

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

        if action == "seed":
            if not str(event.get("reason") or "").strip():
                errors.append(f"{label}: seed requires a non-empty reason")
            added_node_ids = as_string_list(event.get("add_nodes"), f"{label}.add_nodes", errors)
            for node_id in added_node_ids:
                if node_id not in nodes:
                    errors.append(f"{label}: add_nodes references missing node {node_id}")
                else:
                    event_added_nodes.add(node_id)
            added_edge_ids = as_string_list(event.get("add_edges"), f"{label}.add_edges", errors)
            for edge_id in added_edge_ids:
                if edge_ids and edge_id not in edge_ids:
                    errors.append(f"{label}: add_edges references missing edge id {edge_id}")
                elif not edge_ids:
                    warnings.append(f"{label}: add_edges cannot be cross-checked because edges have no ids")
            for factor_id in as_string_list(event.get("update_factors"), f"{label}.update_factors", errors):
                if factor_id not in factors_by_id:
                    errors.append(f"{label}: update_factors references missing factor id {factor_id}")
            added_frontier_ids = as_string_list(event.get("add_frontier"), f"{label}.add_frontier", errors)
            for item_id in added_frontier_ids:
                item = items.get(item_id)
                if item is None:
                    errors.append(f"{label}: add_frontier references missing frontier item {item_id}")
                    continue
                if item_id in popped_items:
                    errors.append(f"{label}: add_frontier item {item_id} was already popped")
                    continue
                if item_id in virtual_frontier:
                    errors.append(f"{label}: add_frontier item {item_id} is already active")
                parent_id = item.get("parent")
                if parent_id not in (None, ""):
                    errors.append(f"{label}: seeded frontier item {item_id} must be root without parent")
                virtual_frontier.add(item_id)
            continue

        if action == "pop":
            if last_popped_item is not None:
                errors.append(f"{label}: cannot pop while unresolved popped item {last_popped_item} is pending; expand, assign, or rank it first")
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
            historical_state = _historical_state_before_event(state, events, index)
            compute_costs(historical_state)
            historical_items = by_id(historical_state.get("frontier", []), "frontier item")
            historical_item = historical_items.get(item_id, item)
            expected_cost = float(historical_item.get("search_cost", math.inf))
            try:
                event_cost = float(event.get("cost"))
            except (TypeError, ValueError):
                errors.append(f"{label}: cost must be numeric")
                event_cost = expected_cost
            if abs(event_cost - expected_cost) > tolerance:
                errors.append(f"{label}: cost {event_cost} != item search_cost {expected_cost}")

            if virtual_frontier:
                historical_frontier_costs = {
                    q: float(historical_items[q].get("search_cost", math.inf))
                    for q in virtual_frontier
                    if q != item_id
                    if q in historical_items
                }
                lowest_cost = min(historical_frontier_costs.values(), default=math.inf)
                if expected_cost > lowest_cost + tolerance:
                    lowest_items = sorted(
                        q
                        for q, cost in historical_frontier_costs.items()
                        if abs(cost - lowest_cost) <= tolerance
                    )
                    errors.append(f"{label}: popped {item_id} cost {expected_cost} but lowest frontier search_cost is {lowest_cost} at {lowest_items[:3]}")

            virtual_frontier.discard(item_id)
            popped_items.add(item_id)
            last_popped_item = item_id
            stats["pops"] += 1
            continue

        if action == "assign":
            item_id = event.get("item")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{label}: item must be a non-empty string")
                continue
            if item_id not in items:
                errors.append(f"{label}: references missing frontier item {item_id}")
                continue
            if item_id != last_popped_item:
                errors.append(f"{label}: assign must follow most recent unresolved pop ({last_popped_item}), got {item_id}")
            if item_id not in popped_items:
                errors.append(f"{label}: cannot assign unpopped item {item_id}")
            max_concurrency = event.get("max_concurrency", policy_max_probe_concurrency)
            if not isinstance(max_concurrency, int) or max_concurrency < 1:
                errors.append(f"{label}: max_concurrency must be a positive integer when present")
                max_concurrency = policy_max_probe_concurrency
            if len(in_flight_items) >= max_concurrency:
                errors.append(
                    f"{label}: max probe concurrency exceeded ({len(in_flight_items) + 1}/{max_concurrency})"
                )
            in_flight_items.add(item_id)
            if item_id == last_popped_item:
                last_popped_item = None
            continue

        if action == "expand":
            item_id = event.get("item")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{label}: item must be a non-empty string")
                continue
            if item_id not in items:
                errors.append(f"{label}: references missing frontier item {item_id}")
                continue
            assigned_expansion = item_id in in_flight_items
            if item_id != last_popped_item and not assigned_expansion:
                errors.append(f"{label}: expand must follow most recent pop ({last_popped_item}) or target an in-flight assigned item, got {item_id}")
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
            updated_factor_ids = as_string_list(
                event.get("update_factors"), f"{label}.update_factors", errors
            )
            legacy_added_factor_ids = as_string_list(
                event.get("add_factors"), f"{label}.add_factors", errors
            )
            factor_event_ids = updated_factor_ids + legacy_added_factor_ids
            for factor_id in factor_event_ids:
                if factor_id not in factors_by_id:
                    errors.append(f"{label}: update_factors references missing factor id {factor_id}")
            item_node_id = str(items[item_id].get("node") or "")
            added_node_set = set(added_node_ids)
            added_edges = [edges_by_id[edge_id] for edge_id in added_edge_ids if edge_id in edges_by_id]
            updated_factors = [
                factors_by_id[factor_id]
                for factor_id in factor_event_ids
                if factor_id in factors_by_id
            ]
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
            evidence_update_targets = {
                str(edge.get("to"))
                for edge in added_edges
                if (
                    ((edge.get("type") or edge.get("label")) == "leads_to")
                    or (
                        ((edge.get("type") or edge.get("label")) in {"supports", "contradicts"})
                        and ("likelihood_ratio" in edge or "likelihood" in edge)
                    )
                )
                and isinstance(edge.get("to"), str)
            }
            evidence_update_targets.update(
                str(factor.get("target")) for factor in updated_factors if isinstance(factor.get("target"), str)
            )
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
            reranked_visited_nodes = evidence_update_targets | updated_node_ids
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
            in_flight_items.discard(item_id)
            if item_id == last_popped_item:
                last_popped_item = None
            stats["expansions"] += 1
            continue

        if action == "supersede":
            item_id = event.get("item")
            replacement_id = event.get("replacement")
            if not isinstance(item_id, str) or not item_id:
                errors.append(f"{label}: item must be a non-empty string")
                continue
            if not isinstance(replacement_id, str) or not replacement_id:
                errors.append(f"{label}: replacement must be a non-empty string")
                continue
            if item_id == replacement_id:
                errors.append(f"{label}: item and replacement must differ")
                continue
            if item_id not in items:
                errors.append(f"{label}: references missing frontier item {item_id}")
                continue
            if replacement_id not in items:
                errors.append(f"{label}: references missing replacement frontier item {replacement_id}")
                continue
            if item_id not in virtual_frontier:
                errors.append(f"{label}: item {item_id} is not in current virtual frontier")
            if replacement_id not in virtual_frontier:
                errors.append(f"{label}: replacement {replacement_id} is not in current virtual frontier")
            if expansion_signature(items[item_id]) != expansion_signature(items[replacement_id]):
                errors.append(f"{label}: item {item_id} and replacement {replacement_id} have different expansion_signature")
            item_cost = float(items[item_id].get("search_cost", math.inf))
            replacement_cost = float(items[replacement_id].get("search_cost", math.inf))
            if replacement_cost >= item_cost - tolerance:
                errors.append(
                    f"{label}: replacement {replacement_id} cost {replacement_cost} must be lower than superseded item {item_id} cost {item_cost}"
                )
            virtual_frontier.discard(item_id)
            if replacement_id not in popped_items:
                virtual_frontier.add(replacement_id)
            continue

        if action == "rank":
            item_id = event.get("item")
            if item_id is not None:
                if not isinstance(item_id, str) or not item_id:
                    errors.append(f"{label}: item must be a non-empty string when present")
                elif item_id not in items:
                    errors.append(f"{label}: references missing frontier item {item_id}")
                elif item_id not in popped_items:
                    warnings.append(f"{label}: ranked item {item_id} was recorded before a pop event")
                if item_id == last_popped_item:
                    last_popped_item = None
                in_flight_items.discard(item_id)
            best_id = event.get("best")
            if not isinstance(best_id, str) or not best_id:
                errors.append(f"{label}: best must be a non-empty candidate_solution id")
            elif best_id not in nodes:
                errors.append(f"{label}: references missing candidate_solution node {best_id}")
            else:
                node_type = nodes[best_id].get("type")
                if node_type != "candidate_solution":
                    errors.append(f"{label}: best {best_id} must be candidate_solution, got {node_type!r}")
                event_ranked_nodes.add(best_id)
                ranked = ranked_viable_candidates(state)
                derived_best = str(ranked[0]["node"]) if ranked else ""
                if derived_best and best_id != derived_best:
                    errors.append(f"{label}: best {best_id} != derived highest-belief candidate {derived_best}")
            candidates = event.get("candidates")
            if candidates is not None and not isinstance(candidates, list):
                errors.append(f"{label}: candidates must be a list when present")
            stats["rankings"] += 1
            continue

        if action == "stop":
            if last_popped_item is not None:
                errors.append(f"{label}: stop cannot follow unresolved popped item {last_popped_item}; expand, assign, or rank it first")
            if in_flight_items:
                errors.append(f"{label}: stop cannot occur while assigned items remain in-flight: {sorted(in_flight_items)}")
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
    has_best_epistemic_candidate = bool(best_epistemic_candidate_ids(state))
    emit_completion_coverage_warnings = branch_policy_enforce_on == "always" or stop_claims_exhaustion or has_best_epistemic_candidate
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

    # Stop-policy thresholds count canonical graph candidates, not report metadata rows.
    # Keep report rows untouched: rendering intentionally preserves duplicate metadata.
    viable_candidates = viable_candidate_ids(state)
    candidate_count = len(viable_candidates)
    stop_policy_result = audit_stop_policy(state, reachable_unpopped_frontier_items, candidate_count)
    errors.extend(stop_policy_result.errors)
    warnings.extend(stop_policy_result.warnings)
    if stats["rankings"] == 0 and candidate_count > 0:
        warnings.append("strict search audit saw no candidate-rank events")
    if candidate_count >= 3:
        expected_branch_count = min(3, candidate_count)
        unvisited_candidates = sorted(
            node_id
            for node_id, node in nodes.items()
            if node.get("type") == "candidate_solution"
            and node_id in viable_candidates
            and node_id not in event_added_nodes
            and node_id not in event_ranked_nodes
        )
        if unvisited_candidates:
            warnings.append(
                "candidate_solution nodes not added or ranked by strict events: "
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
