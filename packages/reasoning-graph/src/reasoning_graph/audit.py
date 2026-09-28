"""Event-trace and stop-policy audit."""

from __future__ import annotations

import math
from typing import Any

from .models import AUDIT_EVENT_ACTIONS, CANDIDATE_STOP_OUTCOMES, EVIDENCE_GROUNDED_STOP_OUTCOMES, STOP_OUTCOMES, ValidationResult
from .policy import candidate_stop_messages, grounded_stop_messages, ranked_viable_candidates, unnamed_best_candidate_messages
from .costs import probability_from_value
from .events import RECORD_CLAIM_FIELDS, graph_digest, live_record_claims
from .state import by_id
from .utils import as_string_list
from .validation import validate_state


def stop_policy_severity(state: dict[str, Any]) -> str:
    policy = state.get("stop_policy") if isinstance(state.get("stop_policy"), dict) else {}
    severity = str(policy.get("severity") or "warning")
    return severity if severity in {"warning", "error"} else "warning"


def add_policy_violation(result: ValidationResult, message: str, severity: str) -> None:
    if severity == "error":
        result.errors.append(message)
    else:
        result.warnings.append(message)


def event_label(events: list[Any], index: int) -> str:
    event = events[index] if isinstance(events[index], dict) else {}
    return f"events[{index}] step={event.get('step')} action={event.get('action')}"


def audit_state(state: dict[str, Any]) -> tuple[ValidationResult, dict[str, int]]:
    """Audit the event trace against the graph it claims to have built.

    Catches decorative or forged traces: events claiming objects that do not exist or were
    already claimed, rank payloads that disagree with the graph at rank time, events after a
    stop, and stops whose outcome the graph does not support.
    """

    base = validate_state(state)
    errors = list(base.errors)
    warnings = list(base.warnings)
    stats = {"events": 0, "records": 0, "rankings": 0}
    if errors:
        return ValidationResult(errors=errors, warnings=warnings), stats

    events = state.get("events")
    if not isinstance(events, list) or not events:
        errors.append("events must be a non-empty list for audit")
        return ValidationResult(errors=errors, warnings=warnings), stats

    nodes = by_id(state.get("nodes", []), "node")
    edge_ids = {edge.get("id") for edge in state.get("edges", []) if isinstance(edge, dict) and isinstance(edge.get("id"), str)}
    factor_ids = {factor.get("id") for factor in state.get("factors", []) or [] if isinstance(factor, dict) and isinstance(factor.get("id"), str)}
    tolerance = 1e-6

    seen_stop = False
    previous_step: int | None = None

    policy_result = ValidationResult(errors=errors, warnings=warnings)
    severity = stop_policy_severity(state)

    for index, raw_event in enumerate(events):
        stats["events"] += 1
        if not isinstance(raw_event, dict):
            errors.append(f"events[{index}] must be object")
            continue
        event = raw_event
        label = event_label(events, index)

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
        if seen_stop:
            if action == "stop":
                errors.append(f"{label}: duplicate stop event; no events allowed after stop")
            else:
                errors.append(f"{label}: no events allowed after stop")
            continue

        if action in ("record", "refresh"):
            if action == "record" and not str(event.get("reason") or "").strip():
                errors.append(f"{label}: record requires a non-empty reason")
            for add_field, remove_field in RECORD_CLAIM_FIELDS.values():
                as_string_list(event.get(add_field), f"{label}.{add_field}", errors)
                as_string_list(event.get(remove_field), f"{label}.{remove_field}", errors)
            if action == "record":
                stats["records"] += 1
            continue

        if action == "rank":
            best_id = event.get("best")
            # stop appends rank as its last step before the stop event, so the final graph is the ranked one.
            ranked = ranked_viable_candidates(state)
            if not isinstance(best_id, str) or not best_id:
                errors.append(f"{label}: best must be a non-empty candidate_solution id")
            elif best_id not in nodes:
                errors.append(f"{label}: references missing candidate_solution node {best_id}")
            else:
                node_type = nodes[best_id].get("type")
                if node_type != "candidate_solution":
                    errors.append(f"{label}: best {best_id} must be candidate_solution, got {node_type!r}")
                derived_best = str(ranked[0]["node"]) if ranked else ""
                if derived_best and best_id != derived_best:
                    errors.append(f"{label}: best {best_id} != derived highest-belief candidate {derived_best}")
                elif ranked and "belief" in event:
                    event_belief = probability_from_value(event.get("belief"))
                    if event_belief is None or abs(event_belief - float(ranked[0]["belief"])) > tolerance:
                        errors.append(f"{label}: belief {event.get('belief')!r} != derived best belief {ranked[0]['belief']}")
            candidates = event.get("candidates")
            if candidates is not None and not isinstance(candidates, list):
                errors.append(f"{label}: candidates must be a list when present")
            elif isinstance(candidates, list):
                if len(candidates) > len(ranked):
                    errors.append(f"{label}: candidates lists {len(candidates)} rows but only {len(ranked)} viable candidates are derived")
                for row_index, (row, expected) in enumerate(zip(candidates, ranked)):
                    if not isinstance(row, dict):
                        errors.append(f"{label}: candidates[{row_index}] must be an object")
                        continue
                    row_node = str(row.get("node") or "")
                    if row_node != str(expected["node"]):
                        errors.append(f"{label}: candidates[{row_index}] node {row_node} != derived {expected['node']}")
                        continue
                    for field in ("belief", "effective_truth_cost"):
                        try:
                            row_value = float(row.get(field))
                        except (TypeError, ValueError):
                            row_value = math.nan
                        if not abs(row_value - float(expected[field])) <= tolerance:
                            errors.append(f"{label}: candidates[{row_index}] {field} {row.get(field)!r} != derived {expected[field]}")
            stats["rankings"] += 1
            continue

        if action == "stop":
            reason = event.get("reason")
            if not isinstance(reason, str) or not reason.strip():
                errors.append(f"{label}: stop reason must be non-empty")
            outcome = event.get("outcome")
            if outcome is None:
                warnings.append(f"{label}: stop outcome missing")
            elif not isinstance(outcome, str) or outcome not in STOP_OUTCOMES:
                errors.append(f"{label}: stop outcome must be one of {sorted(STOP_OUTCOMES)}, got {outcome!r}")
            else:
                if outcome in CANDIDATE_STOP_OUTCOMES:
                    for message in candidate_stop_messages(state):
                        add_policy_violation(policy_result, f"{label}: {outcome} stop is not met; {message}", severity)
                    # The answer texts sit outside the graph digest, so an edit after stop shows only here.
                    errors.extend(f"{label}: {message}" for message in unnamed_best_candidate_messages(state))
                if outcome in EVIDENCE_GROUNDED_STOP_OUTCOMES:
                    for message in grounded_stop_messages(state):
                        add_policy_violation(policy_result, f"{label}: {outcome} stop needs a grounded answer; {message}", severity)
            # stop fingerprints the graph it judged; any later edit breaks the match.
            if event.get("graph_digest") != graph_digest(state):
                errors.append(f"{label}: the graph changed after stop")
            seen_stop = True

    # Each object may be added by one event while the trace holds it (a repeat would let a later
    # record claim earlier work), and whatever the trace still holds must exist in the graph.
    def repeated_add(kind: str, object_id: str, index: int, previous: int) -> None:
        errors.append(f"{event_label(events, index)}: {kind} {object_id} was already added by events[{previous}]")

    existing_ids = {"node": set(nodes), "edge": edge_ids, "factor": factor_ids}
    for (kind, object_id), index in live_record_claims(events, repeated_add).items():
        if object_id not in existing_ids[kind]:
            add_field = RECORD_CLAIM_FIELDS[kind][0]
            errors.append(f"{event_label(events, index)}: {add_field} references missing {kind} {object_id}, and no later record removed it")

    if not seen_stop:
        errors.append("audit requires a stop event")
    return ValidationResult(errors=errors, warnings=warnings), stats
