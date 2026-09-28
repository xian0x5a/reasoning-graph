"""Command-line interface for the reasoning graph helper."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .audit import audit_state
from .costs import claim_beliefs
from .events import GRAPH_CHANGE_ACTIONS, RECORD_CLAIM_FIELDS, graph_digest, is_stopped, last_graph_change, live_record_claims, next_event_step
from .models import CANDIDATE_STOP_OUTCOMES, EVIDENCE_GROUNDED_STOP_OUTCOMES, STOP_OUTCOMES
from .policy import best_candidate_ids, candidate_stop_messages, confidence_stop_messages, goal_best_candidates, ranked_viable_candidates, unanswered_goal_messages
from .render import html_document, presentation_node_ids, to_mermaid
from .schema_validation import patch_schema_errors, standalone_schema
from .source_quotes import quote_mismatch_messages
from .state import by_id, dump_state, load_state, strict_json_dumps, write_output_text
from .validation import validate_state


def cmd_validate(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    result = validate_state(state)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if result.ok:
        print("ok")
        print(f"nodes={len(state.get('nodes', []))} edges={len(state.get('edges', []))}")
        return 0
    return 1


def cmd_schema(args: argparse.Namespace) -> int:
    schema_name = f"{args.name}.schema.json"
    text = strict_json_dumps(standalone_schema(schema_name), indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    write_output_text(text, args.output)
    return 0


def cmd_beliefs(args: argparse.Namespace) -> int:
    """Print each claim's computed belief."""
    state = load_state(args.state)
    beliefs = claim_beliefs(state)
    rows = [{"id": node["id"], "type": node["type"], "belief": beliefs[node["id"]]} for node in state.get("nodes", []) if node["id"] in beliefs]
    if args.json:
        print(strict_json_dumps(rows, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            print(f"{row['id']} {row['type']} belief {row['belief']:.3g}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    result, stats = audit_state(state)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if result.ok:
        print("ok")
        print(
            "events={events} records={records} reviews={reviews} rankings={rankings}".format(**stats)
        )
        return 0
    return 1


# Confidence plus an independent review gate a solved stop: minimum-candidate and empty-frontier
# gates pushed agents into seeding rivals they never needed (countdown-island benchmark).
STRICT_STOP_POLICY = {
    "belief_threshold": 0.8,
    "require_review": True,
    "severity": "error",
}


def starter_state(profile: str, goal: str = "Solve the problem") -> dict[str, Any]:
    state: dict[str, Any] = {
        "summary": {"title": "Reasoning Graph", "answer": ""},
        "nodes": [{"id": "G1", "type": "goal", "text": goal}],
        "edges": [],
    }
    if profile == "strict":
        state["stop_policy"] = dict(STRICT_STOP_POLICY)
    return state


def default_in_place_source(args: argparse.Namespace) -> str | None:
    """Return the input state path used as the default mutation target."""
    if args.output:
        return None
    state_path = getattr(args, "state", None)
    if not state_path or state_path == "-":
        return None
    return str(state_path)


def cmd_init(args: argparse.Namespace) -> int:
    goal = args.goal.strip()
    if not goal:
        print("error: --goal must be non-empty", file=sys.stderr)
        return 1
    profile = "strict" if args.strict else args.profile
    state = starter_state(profile, goal)
    dump_state(state, args.output)
    return 0


RECORD_PATCH_FIELDS = {
    "reason",
    "nodes", "update_nodes", "remove_nodes",
    "edges", "update_edges", "remove_edges",
    "factors", "remove_factors",
}


def _apply_graph_patch(state: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Apply removals, then updates, then additions; return the event fields that make the change auditable."""
    nodes_to_add = _object_list(patch.get("nodes"), "nodes")
    edges_to_add = _object_list(patch.get("edges"), "edges")
    factors_to_upsert = _object_list(patch.get("factors"), "factors")
    node_updates = _field_update_list(patch.get("update_nodes"), "update_nodes")
    edge_updates = _field_update_list(patch.get("update_edges"), "update_edges")

    removed_node_ids = _remove_by_id(state, "nodes", patch.get("remove_nodes") or [])
    # An edge means nothing without both endpoints, so removing a node removes its edges.
    incident_edge_ids = [
        edge["id"]
        for edge in state.get("edges", [])
        if isinstance(edge, dict) and (edge.get("from") in removed_node_ids or edge.get("to") in removed_node_ids)
    ]
    removed_edge_ids = _remove_by_id(state, "edges", [*(patch.get("remove_edges") or []), *incident_edge_ids])
    removed_factor_ids = _remove_by_id(state, "factors", patch.get("remove_factors") or [])

    updated_nodes = _apply_field_updates(state.get("nodes", []), node_updates, "update_nodes")
    updated_edges = _apply_field_updates(state.get("edges", []), edge_updates, "update_edges")

    existing_nodes = {node.get("id") for node in state.get("nodes", []) if isinstance(node, dict)}
    existing_edges = {edge.get("id") for edge in state.get("edges", []) if isinstance(edge, dict) and edge.get("id")}
    _ensure_unique_new_ids({str(item) for item in existing_nodes if item}, nodes_to_add, "nodes")
    _ensure_unique_new_ids({str(item) for item in existing_edges if item}, edges_to_add, "edges")
    _ensure_object_ids(factors_to_upsert, "factors")
    state.setdefault("nodes", []).extend(nodes_to_add)
    state.setdefault("edges", []).extend(edges_to_add)
    factors = state.setdefault("factors", [])
    if not isinstance(factors, list):
        raise ValueError("factors must be a list before a patch can update it")
    factor_indexes: dict[str, int] = {}
    for index, factor in enumerate(factors):
        if not isinstance(factor, dict) or not isinstance(factor.get("id"), str) or not factor.get("id"):
            continue
        factor_id = str(factor["id"])
        if factor_id in factor_indexes:
            raise ValueError(f"factors has duplicate id {factor_id}")
        factor_indexes[factor_id] = index
    for factor in factors_to_upsert:
        factor_id = str(factor["id"])
        if factor_id in factor_indexes:
            factors[factor_indexes[factor_id]] = factor
        else:
            factor_indexes[factor_id] = len(factors)
            factors.append(factor)
    optional_fields = {
        "updated_nodes": updated_nodes,
        "updated_edges": updated_edges,
        "remove_nodes": removed_node_ids,
        "remove_edges": removed_edge_ids,
        "remove_factors": removed_factor_ids,
    }
    return {
        "add_nodes": [node["id"] for node in nodes_to_add],
        "add_edges": [edge["id"] for edge in edges_to_add],
        "update_factors": [factor["id"] for factor in factors_to_upsert],
        **{field: value for field, value in optional_fields.items() if value},
    }


def _hand_edit_event(state: dict[str, Any]) -> dict[str, Any] | None:
    """Describe edits made outside the CLI since the last record or refresh as refresh event fields.

    Callers append the event only after the edited graph passes the checks a patch would, so the
    trace records the edit and any review of the older graph goes stale.
    """
    last_change = last_graph_change(state)
    digest = graph_digest(state)
    if last_change is None or last_change.get("graph_digest") == digest:
        return None
    return {"action": "refresh", **_objects_removed_outside_record(state), "graph_digest": digest}


def _quote_errors(state: dict[str, Any], state_path: str) -> list[str]:
    source_base_dir = Path(state_path).parent if state_path != "-" else Path.cwd()
    # Malformed nodes are validation's to report.
    nodes = [node for node in state.get("nodes", []) if isinstance(node, dict)]
    return [message for node in nodes for message in quote_mismatch_messages(node, source_base_dir)]


def _passes_quote_and_graph_checks(state: dict[str, Any], state_path: str) -> bool:
    """Recheck every quote and validate the graph, rewriting beliefs; print every failure and return False on any.

    The two checks are independent, so one run lists everything to fix instead of one kind per retry.
    """
    quote_errors = _quote_errors(state, state_path)
    for message in quote_errors:
        print(f"error: {message}", file=sys.stderr)
    graph_valid = refresh_beliefs(state)
    return graph_valid and not quote_errors


def _objects_removed_outside_record(state: dict[str, Any]) -> dict[str, list[str]]:
    """Name, by event removal field, objects an earlier record added that the state no longer holds.

    Only a hand edit removes an object without a record; logging the removal keeps `audit` consistent.
    Objects added by hand stay untraced, like the goal `init` writes.
    """
    existing_ids = {
        "node": {node.get("id") for node in state.get("nodes", []) if isinstance(node, dict)},
        "edge": {edge.get("id") for edge in state.get("edges", []) if isinstance(edge, dict)},
        "factor": {factor.get("id") for factor in state.get("factors", []) or [] if isinstance(factor, dict)},
    }
    removed: dict[str, list[str]] = {}
    for kind, object_id in live_record_claims(state.get("events")):
        if object_id not in existing_ids[kind]:
            removed.setdefault(RECORD_CLAIM_FIELDS[kind][1], []).append(object_id)
    return removed


def refresh_beliefs(state: dict[str, Any]) -> bool:
    """Validate the graph and rewrite each claim's stored belief; report errors and return False if invalid."""
    # Stored beliefs describe the graph before this edit; drop them so validation judges the graph, not the stale copy.
    for node in state.get("nodes", []):
        node.pop("belief", None)
    result = validate_state(state)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if result.errors:
        return False
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    beliefs = claim_beliefs(state)
    for node in state["nodes"]:
        if node["id"] in beliefs:
            node["belief"] = beliefs[node["id"]]
    return True


def write_live_view(state: dict[str, Any], args: argparse.Namespace) -> None:
    """Refresh <state>.html beside the written state so a human can watch progress."""
    target = args.output or args.state
    if target == "-":
        return
    document = html_document(state, to_mermaid(state, group_by_type=True), "default", "mermaid")
    live_view_path = Path(target).with_suffix(".html")
    # The view omits the event log, so a record can leave it byte-identical; skipping
    # the rewrite saves the disk write and keeps the file's mtime a real change signal.
    if live_view_path.is_file() and live_view_path.read_text(encoding="utf-8") == document:
        return
    write_output_text(document, str(live_view_path))


REVIEW_VERDICTS = ("pass", "fail")


def cmd_review(args: argparse.Namespace) -> int:
    """Append a reviewer's verdict on the current graph; a later record makes it stale."""
    state = load_state(args.state)
    if is_stopped(state):
        print("error: search already has a stop event; review cannot append", file=sys.stderr)
        return 1
    events = state.get("events")
    if not isinstance(events, list) or not any(isinstance(event, dict) and event.get("action") in GRAPH_CHANGE_ACTIONS for event in events):
        print("error: nothing to review; record the graph first", file=sys.stderr)
        return 1
    reviewer = args.reviewer.strip()
    findings = args.findings.strip()
    if not reviewer:
        print("error: --reviewer must name the reviewing agent", file=sys.stderr)
        return 1
    if not findings:
        print("error: --findings must say what was checked and what was found", file=sys.stderr)
        return 1
    events.append({
        "step": next_event_step(state), "action": "review", "reviewer": reviewer, "verdict": args.verdict, "findings": findings,
        "graph_digest": graph_digest(state),
    })
    dump_state(state, args.output, default_in_place_source(args))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    """Append graph progress, then refresh the human-facing view."""
    state = load_state(args.state)
    if is_stopped(state):
        print("error: search already has a stop event; record cannot append work", file=sys.stderr)
        return 1
    patch = load_state(args.patch)
    if not isinstance(patch, dict):
        raise ValueError("record patch must be a JSON object")
    patch_errors = patch_schema_errors(patch)
    if patch_errors:
        for error in patch_errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    unsupported_fields = sorted(set(patch) - RECORD_PATCH_FIELDS)
    if unsupported_fields:
        print(f"error: record patch field(s) not allowed: {', '.join(unsupported_fields)}", file=sys.stderr)
        return 1
    reason = str(patch.get("reason") or "").strip()
    if not reason:
        print("error: record patch requires reason: what this step did", file=sys.stderr)
        return 1

    # Validation and quote checks below judge the patched graph, so a patch may repair a hand edit.
    hand_edit = _hand_edit_event(state)
    patch_trace = _apply_graph_patch(state, patch)
    events = state.setdefault("events", [])
    if not isinstance(events, list):
        raise ValueError("events must be a list before record can append")
    if hand_edit:
        events.append({"step": next_event_step(state), **hand_edit})
    events.append(
        {
            "step": next_event_step(state),
            "action": "record",
            "reason": reason,
            **patch_trace,
            "graph_digest": graph_digest(state),
        }
    )

    if not _passes_quote_and_graph_checks(state, args.state):
        return 1
    dump_state(state, args.output, default_in_place_source(args))
    write_live_view(state, args)
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    """Re-sync a hand-edited state: validate it, recheck every quote, log removed objects, rewrite beliefs and the view."""
    state = load_state(args.state)
    if is_stopped(state):
        print("error: search already has a stop event; refresh cannot append", file=sys.stderr)
        return 1
    hand_edit = _hand_edit_event(state)
    if not _passes_quote_and_graph_checks(state, args.state):
        return 1
    if hand_edit is None:
        print("ok: no edits outside the CLI; beliefs rewritten")
    else:
        step = next_event_step(state)
        state.setdefault("events", []).append({"step": step, **hand_edit})
        print(f"ok: logged the hand edit as refresh step {step}")
        for _, remove_field in RECORD_CLAIM_FIELDS.values():
            if hand_edit.get(remove_field):
                print(f"{remove_field}: {', '.join(hand_edit[remove_field])}")
    dump_state(state, args.output, default_in_place_source(args))
    write_live_view(state, args)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    result = validate_state(state)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if not result.ok:
        print("doctor: validation failed")
        return 1

    try:
        claim_beliefs(state)
    except Exception as exc:
        print(f"error: belief computation failed: {exc}", file=sys.stderr)
        print("doctor: belief computation failed")
        return 1

    print("doctor: validation ok")
    print(
        "doctor: nodes={nodes} edges={edges} stopped={stopped}".format(
            nodes=len(state.get("nodes", [])),
            edges=len(state.get("edges", [])),
            stopped=str(is_stopped(state)).lower(),
        )
    )

    # audit judges a finished trace; a working state is healthy once it validates.
    if not is_stopped(state):
        print("doctor: audit skipped (not stopped)")
        return 0

    audit_result, stats = audit_state(state)
    for warning in audit_result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in audit_result.errors:
        print(f"error: {error}", file=sys.stderr)
    print(
        "doctor: audit events={events} records={records} reviews={reviews} rankings={rankings}".format(**stats)
    )
    if not audit_result.ok:
        print("doctor: audit failed")
        return 1
    print("doctor: audit ok")
    return 0


def _print_yaml_list(name: str, values: list[str]) -> None:
    print(f"{name}:")
    if not values:
        print("  []")
        return
    for value in values:
        print(f"  - {strict_json_dumps(value, ensure_ascii=False)}")


def _stop_events(state: dict[str, Any]) -> list[dict[str, Any]]:
    events = state.get("events")
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict) and event.get("action") == "stop"]


def cmd_stop_review(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    required_fixes: list[str] = []
    notes: list[str] = []
    checks = [
        "validation passed before semantic review",
        "audit passed when driver events exist",
        "stop event exists and includes structured outcome",
        "best viable candidate is derived for solved/candidate-threshold stops",
        "best candidate answers an accepted goal",
        "every accepted goal is answered for solved/candidate-threshold stops",
        "summary/report answer names the best candidate for each accepted goal",
        "draft names the best candidate for each accepted goal when draft is supplied",
    ]

    validation_result = validate_state(state)
    required_fixes.extend(f"validation error: {error}" for error in validation_result.errors)
    validation_warnings = [f"validation warning: {warning}" for warning in validation_result.warnings]
    if args.strict_warnings:
        required_fixes.extend(validation_warnings)
    else:
        notes.extend(validation_warnings)
    if not isinstance(state, dict):
        # Nothing below can be evaluated on a non-object document; report the schema failure alone.
        return _print_stop_review("fail", required_fixes, checks, notes)

    events = state.get("events")
    if not isinstance(events, list) or not events:
        required_fixes.append("state has no driver events; stop-review expects a stopped driver state")
    else:
        audit_result, _ = audit_state(state)
        required_fixes.extend(f"audit error: {error}" for error in audit_result.errors)
        audit_warnings = [f"audit warning: {warning}" for warning in audit_result.warnings]
        if args.strict_warnings:
            required_fixes.extend(audit_warnings)
        else:
            notes.extend(audit_warnings)

    stops = _stop_events(state)
    if not stops:
        required_fixes.append("missing stop event")
        stop_outcome = ""
    else:
        stop_outcome = str(stops[-1].get("outcome") or "")
        if not stop_outcome:
            required_fixes.append("latest stop event missing outcome")

    try:
        best_ids = best_candidate_ids(state)
    except ValueError as exc:
        # Malformed scores were already reported by validation; keep the review report structured.
        required_fixes.append(f"cannot derive best candidate: {exc}")
        best_ids = set()
    needs_best_candidate = stop_outcome in CANDIDATE_STOP_OUTCOMES
    if needs_best_candidate and not best_ids:
        required_fixes.append(f"stop outcome {stop_outcome!r} requires a viable candidate_solution")

    if needs_best_candidate:
        required_fixes.extend(f"stop outcome {stop_outcome!r} leaves an accepted goal open; {message}" for message in unanswered_goal_messages(state))
        # The reported answer must be the graph's answer: every answer-bearing text names
        # the best candidate of each accepted goal, by id or exact candidate text.
        nodes = by_id(state.get("nodes", []), "node")
        answer_texts = {
            f"{section}.answer": str(state[section].get("answer") or "").strip()
            for section in ("summary", "report")
            if isinstance(state.get(section), dict)
        }
        if args.draft:
            answer_texts["draft"] = Path(args.draft).read_text(encoding="utf-8")
        for goal_id, candidate_id in sorted(goal_best_candidates(state).items()):
            candidate_text = str(nodes.get(candidate_id, {}).get("text") or "").strip()
            for field, text in answer_texts.items():
                if not text:
                    continue
                if candidate_id in text or (candidate_text and candidate_text in text):
                    continue
                verb = "mention" if field == "draft" else "name"
                quoted = "" if field == "draft" else f"; answer: {text!r}"
                required_fixes.append(f"{field} does not {verb} best candidate {candidate_id} ({candidate_text!r}) for goal {goal_id}{quoted}")

    verdict = "fail" if required_fixes else "pass"
    return _print_stop_review(verdict, required_fixes, checks, notes)


def _print_stop_review(verdict: str, required_fixes: list[str], checks: list[str], notes: list[str]) -> int:
    print(f"verdict: {verdict}")
    _print_yaml_list("required_fixes", required_fixes)
    _print_yaml_list("semantic_tricks_checked", checks)
    _print_yaml_list("notes", notes)
    return 0 if verdict == "pass" else 1


def _object_list(value: Any, field: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"{field} must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{field}[{index}] must be an object")
        result.append(item)
    return result


def _ensure_object_ids(items: list[dict[str, Any]], field: str) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for index, item in enumerate(items):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"{field}[{index}] missing string id")
        if item_id in seen:
            raise ValueError(f"{field}[{index}] duplicate id {item_id}")
        seen.add(item_id)
        ids.append(item_id)
    return ids


def _ensure_unique_new_ids(existing: set[str], additions: list[dict[str, Any]], field: str) -> None:
    for item_id in _ensure_object_ids(additions, field):
        if item_id in existing:
            raise ValueError(f"{field} id {item_id} already exists")


# Identity fields: changing one would make a different claim or edge, so a patch removes the
# object and adds a new one instead.
IMMUTABLE_UPDATE_FIELDS = {"update_nodes": {"id", "type"}, "update_edges": {"id", "from", "to"}}


def _field_update_list(value: Any, field: str) -> list[dict[str, Any]]:
    updates = _object_list(value, field)
    for index, update in enumerate(updates):
        changes, removals = update.get("set") or {}, update.get("unset") or []
        for operation, names in (("set", set(changes)), ("unset", set(removals))):
            immutable = sorted(names & IMMUTABLE_UPDATE_FIELDS[field])
            if immutable:
                raise ValueError(f"{field}[{index}].{operation} cannot change {', '.join(immutable)}")
        conflicting = sorted(set(changes) & set(removals))
        if conflicting:
            raise ValueError(f"{field}[{index}] both sets and unsets {', '.join(conflicting)}")
    _ensure_object_ids(updates, field)
    return updates


def _apply_field_updates(items: list[Any], updates: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    """Set and unset fields on existing items by id; return each item's changed field names for the event."""
    items_by_id = {item["id"]: item for item in items if isinstance(item, dict) and isinstance(item.get("id"), str)}
    specs: list[dict[str, Any]] = []
    for update in updates:
        item_id = str(update["id"])
        item = items_by_id.get(item_id)
        if item is None:
            raise ValueError(f"{field} id {item_id} does not exist")
        changes, removals = update.get("set") or {}, update.get("unset") or []
        for name in removals:
            if name not in item:
                raise ValueError(f"{field} id {item_id} has no {name} to unset")
            del item[name]
        item.update(changes)
        specs.append({"id": item_id, "fields": sorted({*changes, *removals})})
    return specs


def _remove_by_id(state: dict[str, Any], key: str, ids: list[str]) -> list[str]:
    """Remove items from state[key] by id and return the removed ids in order."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    items = state.get(key) or []
    present = {item.get("id") for item in items if isinstance(item, dict)}
    for item_id in ids:
        if item_id not in present:
            raise ValueError(f"remove_{key} id {item_id} does not exist")
    state[key] = [item for item in items if not (isinstance(item, dict) and item.get("id") in ids)]
    return ids


def append_rank_event(state: dict[str, Any], top: int = 10) -> int:
    """Pin the best candidate at stop time so audit and stop-review check the answer against it."""
    ranked = ranked_viable_candidates(state)
    if not ranked:
        print("error: no viable candidate_solution answers an accepted goal", file=sys.stderr)
        return 1

    events = state.setdefault("events", [])
    if not isinstance(events, list):
        print("error: events must be a list before rank can append", file=sys.stderr)
        return 1

    event: dict[str, Any] = {
        "step": next_event_step(state),
        "action": "rank",
        "best": ranked[0]["node"],
        "belief": ranked[0]["belief"],
        "candidates": ranked[: max(1, top)],
    }
    events.append(event)
    return 0


def _stop_preflight(state: dict[str, Any], reason: str, outcome: str) -> int:
    """Reject a stop whose outcome the recorded graph does not support."""
    reason = reason.strip()
    if not reason:
        print("error: stop reason must be non-empty", file=sys.stderr)
        return 1
    if outcome not in STOP_OUTCOMES:
        print(f"error: --outcome must be one of {sorted(STOP_OUTCOMES)}, got {outcome!r}", file=sys.stderr)
        return 1

    events = state.get("events")
    if events is not None and not isinstance(events, list):
        print("error: events must be a list before stop can append", file=sys.stderr)
        return 1
    if is_stopped(state):
        print("error: search already has a stop event", file=sys.stderr)
        return 1
    if outcome in CANDIDATE_STOP_OUTCOMES:
        unmet = candidate_stop_messages(state)
        for message in unmet:
            print(f"error: stop outcome {outcome!r} is not met; {message}", file=sys.stderr)
        if unmet:
            print(
                "error: add a candidate_solution with an answers edge, list the goal in goal_policy.optional_goals, "
                "or stop with a non-candidate outcome such as inconclusive or budget_exhausted",
                file=sys.stderr,
            )
            return 1
    if outcome in EVIDENCE_GROUNDED_STOP_OUTCOMES:
        unmet = confidence_stop_messages(state)
        for message in unmet:
            print(f"error: stop outcome {outcome!r} requires a grounded, confident answer; {message}", file=sys.stderr)
        if unmet:
            print(
                "error: record the missing results or supporting observations, "
                "or stop with a non-confidence outcome such as inconclusive or budget_exhausted and report the open hypotheses",
                file=sys.stderr,
            )
            return 1
    return 0


def append_stop_event(state: dict[str, Any], reason: str, outcome: str) -> int:
    if _stop_preflight(state, reason, outcome) != 0:
        return 1
    events = state.setdefault("events", [])
    events.append({"step": next_event_step(state), "action": "stop", "reason": reason.strip(), "outcome": outcome, "graph_digest": graph_digest(state)})
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    hand_edit = _hand_edit_event(state)
    # The gates need a valid graph and judge beliefs computed here; stored ones are overwritten, never trusted.
    if not refresh_beliefs(state):
        return 1
    # Quote and gate failures are independent, so report both in one run instead of one per retry.
    quote_errors = _quote_errors(state, args.state)
    for message in quote_errors:
        print(f"error: {message}", file=sys.stderr)
    # Preflight all terminal invariants before candidate auto-ranking can append
    # a rank event.
    if _stop_preflight(state, args.reason, args.outcome) != 0 or quote_errors:
        return 1
    # Logged only once every check passes, and before rank and stop, since nothing may follow stop.
    if hand_edit:
        state.setdefault("events", []).append({"step": next_event_step(state), **hand_edit})
    if args.outcome in CANDIDATE_STOP_OUTCOMES:
        if append_rank_event(state, top=args.top) != 0:
            return 1
    if append_stop_event(state, args.reason, args.outcome) != 0:
        return 1
    dump_state(state, args.output, default_in_place_source(args))
    return 0


def cmd_mermaid(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    include_nodes = presentation_node_ids(state) if args.view == "presentation" else None
    source = to_mermaid(state, include_nodes, group_by_type=args.grouped or args.view == "audit")
    write_output_text(source, args.output)
    return 0


def cmd_html(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    result = validate_state(state)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if not result.ok:
        return 1
    source = to_mermaid(state, group_by_type=True)
    render_mode = "offline" if args.offline else "mermaid"
    document = html_document(state, source, args.spacing, render_mode)
    write_output_text(document, args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reasoning graph helper")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="emit a starter state for a goal")
    init.add_argument("--goal", required=True, help="goal text for G1")
    init.add_argument("--profile", choices=("minimal", "strict"), default="minimal", help="starter profile")
    init.add_argument("--strict", action="store_true", help="shortcut for --profile strict")
    init.add_argument("-o", "--output", help="write result to path instead of stdout")
    init.set_defaults(func=cmd_init)

    record = sub.add_parser("record", help="append graph progress and refresh <state>.html")
    record.add_argument("state", help="state JSON path, or - for stdin")
    record.add_argument("--patch", required=True, help="patch JSON path, or - for stdin: reason plus any add, update, or remove operations")
    record.add_argument("-o", "--output", help="write updated state to path")
    record.set_defaults(func=cmd_record)

    refresh = sub.add_parser("refresh", help="after a hand edit: validate, recheck quotes, recompute beliefs, and log the edit")
    refresh.add_argument("state", help="state JSON path")
    refresh.add_argument("-o", "--output", help="write updated state to path")
    refresh.set_defaults(func=cmd_refresh)

    review = sub.add_parser("review", help="record an independent reviewer's verdict on the current graph")
    review.add_argument("state", help="state JSON path, or - for stdin")
    review.add_argument("--reviewer", required=True, help="id of the reviewing agent")
    review.add_argument("--verdict", required=True, choices=REVIEW_VERDICTS, help="pass, or fail with findings to fix")
    review.add_argument("--findings", required=True, help="what was checked and what was found")
    review.add_argument("-o", "--output", help="write updated state to path")
    review.set_defaults(func=cmd_review)


    validate = sub.add_parser("validate", help="validate graph state")
    validate.add_argument("state", help="state JSON path, or - for stdin")
    validate.set_defaults(func=cmd_validate)

    schema = sub.add_parser("schema", help="emit a packaged JSON Schema")
    schema.add_argument("name", choices=("state", "patch"), help="schema to emit")
    schema.add_argument("-o", "--output", help="write schema JSON to path instead of stdout")
    schema.set_defaults(func=cmd_schema)

    doctor = sub.add_parser("doctor", help="validate state, compute beliefs, and audit a stopped trace")
    doctor.add_argument("state", help="state JSON path, or - for stdin")
    doctor.set_defaults(func=cmd_doctor)

    stop_review = sub.add_parser("stop-review", help="run semantic stop-review checklist for a stopped state")
    stop_review.add_argument("state", help="state JSON path, or - for stdin")
    stop_review.add_argument("--draft", help="optional final answer draft to compare against the derived best candidate")
    stop_review.add_argument("--strict-warnings", action="store_true", help="treat validation/audit warnings as required fixes")
    stop_review.set_defaults(func=cmd_stop_review)

    beliefs = sub.add_parser("beliefs", help="print each claim's computed belief")
    beliefs.add_argument("state", help="state JSON path, or - for stdin")
    beliefs.add_argument("--json", action="store_true", help="print JSON instead of compact text")
    beliefs.set_defaults(func=cmd_beliefs)

    audit = sub.add_parser("audit", help="audit the event trace and stop gates")
    audit.add_argument("state", help="state JSON path, or - for stdin")
    audit.set_defaults(func=cmd_audit)







    stop = sub.add_parser("stop", help="check stop gates, rank candidate-bearing outcomes, then append a stop event")
    stop.add_argument("state", help="state JSON path, or - for stdin")
    stop.add_argument("--reason", required=True, help="why search is stopping")
    stop.add_argument("--outcome", required=True, choices=sorted(STOP_OUTCOMES), help="structured stop outcome")
    stop.add_argument("--top", type=int, default=10, help="number of ranked candidates to include for candidate-bearing outcomes")
    stop.add_argument("-o", "--output", help="write mutated state to path")
    stop.add_argument("-i", "--in-place", action="store_true", help="optional; default already rewrites input file")
    stop.set_defaults(func=cmd_stop)


    mermaid = sub.add_parser("mermaid", help="render Mermaid source")
    mermaid.add_argument("state", help="state JSON path, or - for stdin")
    mermaid.add_argument("-o", "--output", help="write Mermaid source to path")
    mermaid.add_argument("--view", choices=("audit", "presentation"), default="audit", help="render full audit graph or curated presentation graph")
    mermaid.add_argument("--grouped", action="store_true", help="group nodes into Mermaid subgraphs by node type")
    mermaid.set_defaults(func=cmd_mermaid)

    html_cmd = sub.add_parser("html", help="render Mermaid HTML report")
    html_cmd.add_argument("state", help="state JSON path, or - for stdin")
    html_cmd.add_argument("-o", "--output", help="write HTML to path")
    html_cmd.add_argument("--offline", action="store_true", help="render inline SVG fallback with no CDN/network dependency")
    html_cmd.add_argument("--spacing", choices=("default", "relaxed", "wide", "compact"), default="default", help="graph spacing preset")
    html_cmd.set_defaults(func=cmd_html)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
