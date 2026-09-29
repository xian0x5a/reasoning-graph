"""Event-trace and stop-policy audit."""

from __future__ import annotations

from typing import Any

from .models import AUDIT_EVENT_ACTIONS, CANDIDATE_STOP_OUTCOMES, EVIDENCE_GROUNDED_STOP_OUTCOMES, STOP_OUTCOMES, ValidationResult
from .policy import candidate_stop_messages, grounded_stop_messages, unnamed_answer_messages
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
    already claimed, events after a stop, and stops whose outcome the graph does not support.
    """

    base = validate_state(state)
    errors = list(base.errors)
    warnings = list(base.warnings)
    stats = {"events": 0, "records": 0}
    if errors:
        return ValidationResult(errors=errors, warnings=warnings), stats

    events = state.get("events")
    if not isinstance(events, list) or not events:
        errors.append("events must be a non-empty list for audit")
        return ValidationResult(errors=errors, warnings=warnings), stats

    nodes = by_id(state.get("nodes", []), "node")
    edge_ids = {edge.get("id") for edge in state.get("edges", []) if isinstance(edge, dict) and isinstance(edge.get("id"), str)}
    factor_ids = {factor.get("id") for factor in state.get("factors", []) or [] if isinstance(factor, dict) and isinstance(factor.get("id"), str)}

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
                    errors.extend(f"{label}: {message}" for message in unnamed_answer_messages(state))
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
