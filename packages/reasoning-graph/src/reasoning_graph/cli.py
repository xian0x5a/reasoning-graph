"""Command-line interface for the reasoning graph helper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .audit import audit_state, expansion_gaps, stop_policy_severity
from .costs import compute_costs, sorted_frontier, sorted_frontier_items
from .frontier import expansion_signature, item_view, next_event_step, reconstruct_path, search_cursor
from .models import CANDIDATE_STOP_OUTCOMES, DEFAULT_MAX_PROBE_CONCURRENCY, EVIDENCE_GROUNDED_STOP_OUTCOMES, STOP_OUTCOMES
from .policy import best_candidate_ids, confidence_stop_messages, goal_best_candidates, ranked_viable_candidates, unanswered_goal_messages
from .render import html_document, presentation_node_ids, to_mermaid
from .schema_validation import patch_schema_errors, standalone_schema
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
        print(f"nodes={len(state.get('nodes', []))} edges={len(state.get('edges', []))} frontier={len(state.get('frontier', []))}")
        return 0
    return 1


def cmd_schema(args: argparse.Namespace) -> int:
    schema_name = f"{args.name}.schema.json"
    text = strict_json_dumps(standalone_schema(schema_name), indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    write_output_text(text, args.output)
    return 0


def cmd_costs(args: argparse.Namespace) -> int:
    state = compute_costs(load_state(args.state))
    dump_state(state, args.output, default_in_place_source(args))
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
            "events={events} pops={pops} expansions={expansions} rankings={rankings} peak_live_frontier={peak_live_frontier}".format(**stats)
        )
        return 0
    return 1


# Confidence alone gates a solved stop: minimum-candidate and empty-frontier gates pushed agents
# into seeding rivals they never needed (countdown-island benchmark).
STRICT_STOP_POLICY = {
    "belief_threshold": 0.8,
    "severity": "error",
}


def starter_state(profile: str, goal: str = "Solve the problem") -> dict[str, Any]:
    state: dict[str, Any] = {
        "summary": {"title": "Reasoning Graph", "answer": ""},
        "nodes": [{"id": "G1", "type": "goal", "text": goal}],
        "edges": [],
        "frontier": [],
    }
    if profile == "strict":
        state["search_policy"] = {"estimated_remaining_weight": 1.0}
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


SEED_PATCH_FIELDS = {"nodes", "update_nodes", "edges", "frontier", "update_factors", "factors", "reason"}


def cmd_seed(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    events = state.get("events")
    if events is not None and not isinstance(events, list):
        print("error: events must be a list before seed can validate driver state", file=sys.stderr)
        return 1
    if cursor["stopped"]:
        print("error: search already has a stop event; seed cannot append root work", file=sys.stderr)
        return 1

    patch = load_state(args.patch)
    if not isinstance(patch, dict):
        raise ValueError("seed patch must be a JSON object")
    patch_errors = patch_schema_errors(patch)
    if patch_errors:
        for error in patch_errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    unsupported_fields = sorted(set(patch) - SEED_PATCH_FIELDS)
    if unsupported_fields:
        print(f"error: seed patch field(s) not allowed: {', '.join(unsupported_fields)}", file=sys.stderr)
        return 1
    is_driver_seed = bool(cursor["initialized"])
    seed_reason = str(patch.get("reason") or "").strip()
    if is_driver_seed and not seed_reason:
        print("error: seed after driver init requires patch.reason", file=sys.stderr)
        return 1

    nodes_to_add = _object_list(patch.get("nodes"), "nodes")
    node_updates = _node_update_list(patch.get("update_nodes"), "update_nodes")
    edges_to_add = _object_list(patch.get("edges"), "edges")
    frontier_to_add = _object_list(patch.get("frontier"), "frontier")
    factors_to_update = _object_list(
        patch.get("update_factors", patch.get("factors")),
        "update_factors",
    )
    if not frontier_to_add:
        print("error: seed patch must add at least one frontier item", file=sys.stderr)
        return 1
    for index, item in enumerate(frontier_to_add):
        parent = item.get("parent")
        if parent not in (None, ""):
            print(f"error: seed frontier[{index}] must be a root item without parent", file=sys.stderr)
            return 1
        item.pop("parent", None)

    existing_frontier = {item.get("id") for item in state.get("frontier", []) if isinstance(item, dict)}
    _ensure_unique_new_ids({str(item) for item in existing_frontier if item}, frontier_to_add, "frontier")
    patch_trace = _apply_graph_patch(state, nodes_to_add, node_updates, edges_to_add, factors_to_update)
    supersede_events: list[dict[str, Any]] = []
    if is_driver_seed:
        frontier_to_add, supersede_events = _dedupe_frontier_additions(state, set(cursor["active_ids"]), frontier_to_add)
    state.setdefault("frontier", []).extend(frontier_to_add)
    sorted_frontier(state)

    if is_driver_seed:
        events = state.setdefault("events", [])
        if not isinstance(events, list):
            raise ValueError("events must be a list before seed can append")
        events.append(
            {
                "step": next_event_step(state),
                "action": "seed",
                "reason": seed_reason,
                "add_nodes": [node["id"] for node in nodes_to_add],
                "add_edges": [edge["id"] for edge in edges_to_add],
                "add_frontier": [item["id"] for item in frontier_to_add],
                "update_factors": [factor["id"] for factor in factors_to_update],
                **patch_trace,
            }
        )
        for supersede_event in supersede_events:
            events.append({"step": next_event_step(state), **supersede_event})

    result = validate_state(state)
    if result.errors:
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    dump_state(state, args.output, default_in_place_source(args))
    return 0


RECORD_PATCH_FIELDS = {"nodes", "update_nodes", "edges", "factors", "reason"}


def _apply_graph_patch(
    state: dict[str, Any],
    nodes_to_add: list[dict[str, Any]],
    node_updates: list[dict[str, Any]],
    edges_to_add: list[dict[str, Any]],
    factors_to_update: list[dict[str, Any]],
) -> dict[str, Any]:
    """Add nodes/edges and upsert factors; return the event fields that make the change auditable."""
    existing_nodes = {node.get("id") for node in state.get("nodes", []) if isinstance(node, dict)}
    existing_edges = {edge.get("id") for edge in state.get("edges", []) if isinstance(edge, dict) and edge.get("id")}
    _ensure_unique_new_ids({str(item) for item in existing_nodes if item}, nodes_to_add, "nodes")
    _ensure_unique_new_ids({str(item) for item in existing_edges if item}, edges_to_add, "edges")
    _ensure_object_ids(factors_to_update, "update_factors")

    node_update_snapshots = _node_update_snapshots(state, node_updates)
    factor_update_snapshots = _factor_update_snapshots(state, factors_to_update)
    updated_node_specs = _apply_node_updates(state, node_updates, "update_nodes")
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
    for factor in factors_to_update:
        factor_id = str(factor["id"])
        if factor_id in factor_indexes:
            factors[factor_indexes[factor_id]] = factor
        else:
            factor_indexes[factor_id] = len(factors)
            factors.append(factor)
    return {
        **({"updated_nodes": updated_node_specs} if updated_node_specs else {}),
        **({"updated_node_snapshots": node_update_snapshots} if node_update_snapshots else {}),
        **({"updated_factor_snapshots": factor_update_snapshots} if factor_update_snapshots else {}),
    }


def write_live_view(state: dict[str, Any], args: argparse.Namespace) -> None:
    """Refresh <state>.html beside the written state so a human can watch progress."""
    target = args.output or args.state
    if target == "-":
        return
    document = html_document(state, to_mermaid(state, group_by_type=True), "default", "mermaid")
    write_output_text(document, str(Path(target).with_suffix(".html")))


def cmd_record(args: argparse.Namespace) -> int:
    """Append graph progress without the frontier queue, then refresh the human-facing view."""
    state = load_state(args.state)
    if search_cursor(state)["stopped"]:
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

    nodes_to_add = _object_list(patch.get("nodes"), "nodes")
    edges_to_add = _object_list(patch.get("edges"), "edges")
    factors_to_update = _object_list(patch.get("factors"), "factors")
    patch_trace = _apply_graph_patch(
        state, nodes_to_add, _node_update_list(patch.get("update_nodes"), "update_nodes"), edges_to_add, factors_to_update
    )
    events = state.setdefault("events", [])
    if not isinstance(events, list):
        raise ValueError("events must be a list before record can append")
    events.append(
        {
            "step": next_event_step(state),
            "action": "record",
            "reason": reason,
            "add_nodes": [node["id"] for node in nodes_to_add],
            "add_edges": [edge["id"] for edge in edges_to_add],
            "update_factors": [factor["id"] for factor in factors_to_update],
            **patch_trace,
        }
    )

    result = validate_state(state)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if result.errors:
        return 1
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

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
        compute_costs(state)
    except Exception as exc:
        print(f"error: cost computation failed: {exc}", file=sys.stderr)
        print("doctor: cost computation failed")
        return 1

    cursor = search_cursor(state)
    print("doctor: validation ok")
    print(
        "doctor: nodes={nodes} edges={edges} frontier={frontier} active={active} pending={pending} in_flight={in_flight} stopped={stopped}".format(
            nodes=len(state.get("nodes", [])),
            edges=len(state.get("edges", [])),
            frontier=len(state.get("frontier", [])),
            active=len(cursor["active_ids"]),
            pending=cursor["pending_item"] or "none",
            in_flight=len(cursor.get("in_flight_ids", set())),
            stopped=str(cursor["stopped"]).lower(),
        )
    )

    events = state.get("events")
    if not isinstance(events, list) or not events:
        print("doctor: audit skipped (no events)")
        return 0

    audit_result, stats = audit_state(state)
    for warning in audit_result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in audit_result.errors:
        print(f"error: {error}", file=sys.stderr)
    print(
        "doctor: audit events={events} pops={pops} expansions={expansions} rankings={rankings} peak_live_frontier={peak_live_frontier}".format(**stats)
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


def cmd_sort(args: argparse.Namespace) -> int:
    state = sorted_frontier(load_state(args.state))
    dump_state(state, args.output, default_in_place_source(args))
    return 0


def cmd_frontier(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    ids = None if args.all else cursor["active_ids"]
    rows = [item_view(state, item) for item in sorted_frontier_items(state, ids)]
    if args.limit is not None:
        rows = rows[: args.limit]
    if args.json:
        print(strict_json_dumps(rows, indent=2, ensure_ascii=False))
    else:
        if cursor["stopped"] and not args.all:
            print("search stopped; active frontier empty unless --all is used", file=sys.stderr)
        if cursor["pending_item"] and not args.all:
            print(f"pending expansion: {cursor['pending_item']}", file=sys.stderr)
        in_flight_ids = cursor.get("in_flight_ids", set())
        if in_flight_ids and not args.all:
            print(f"in-flight probes: {','.join(sorted(in_flight_ids))}", file=sys.stderr)
        for row in rows:
            related = f" related={row['related_brief']}" if row.get("related_brief") else ""
            scratch = f" scratch={row['scratch_brief']}" if row.get("scratch_brief") else ""
            heuristic = ""
            if row.get("estimated_remaining_cost") is not None:
                heuristic = f" base={row['base_search_cost']} remaining={row['estimated_remaining_cost']} heuristic={row['heuristic_cost']}"
            print(
                f"{row['id']} search={row['search_cost']} truth={row['truth_cost']}{heuristic} node={row['node']} "
                f"type={row['node_type']} text={row['text']}{related}{scratch}"
            )
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    if cursor["stopped"]:
        print("error: search already has a stop event", file=sys.stderr)
        return 1
    if cursor["pending_item"]:
        print(f"error: pending popped item {cursor['pending_item']} must be expanded, assigned, or ranked before next pop", file=sys.stderr)
        return 1
    active = sorted_frontier_items(state, cursor["active_ids"])
    if args.pop and not cursor["initialized"]:
        kept_ids, _ = _choose_frontier_insertions(state, [str(frontier_item["id"]) for frontier_item in active])
        active = [frontier_item for frontier_item in active if str(frontier_item.get("id")) in kept_ids]
    if not active:
        print("error: active frontier is empty", file=sys.stderr)
        return 1

    item = active[0]
    view = item_view(state, item)
    path = reconstruct_path(state, str(item["id"]))

    if args.pop:
        events = state.setdefault("events", [])
        if not isinstance(events, list):
            print("error: events must be a list before --pop can append", file=sys.stderr)
            return 1
        if not cursor["initialized"]:
            init_ids = [frontier_item["id"] for frontier_item in active]
            events.append({"step": next_event_step(state), "action": "init", "frontier": init_ids})
        pop_event: dict[str, Any] = {
            "step": next_event_step(state),
            "action": "pop",
            "item": item["id"],
            "cost": item.get("search_cost"),
        }
        evidence_version = item.get("evidence_version", state.get("evidence_version"))
        if evidence_version is not None:
            pop_event["evidence_version"] = evidence_version
        events.append(pop_event)
        dump_state(state, args.output, default_in_place_source(args))
        if args.output == "-" or (args.state == "-" and not args.output):
            return 0

    if args.json:
        print(strict_json_dumps({"item": view, "path": path}, indent=2, ensure_ascii=False))
    else:
        heuristic = ""
        if view.get("estimated_remaining_cost") is not None:
            heuristic = f" base={view['base_search_cost']} remaining={view['estimated_remaining_cost']} heuristic={view['heuristic_cost']}"
        print(
            f"next {view['id']} search={view['search_cost']} truth={view['truth_cost']}{heuristic} node={view['node']} "
            f"type={view['node_type']} text={view['text']}"
        )
        if view.get("related_brief"):
            print(f"related: {view['related_brief']}")
        if view.get("scratch_brief"):
            print(f"scratch: {view['scratch_brief']}")
        print("path:")
        for step in path:
            path_item = step["item"]
            path_node = step["node"]
            print(
                f"  {path_item.get('id')} search={path_item.get('search_cost')} "
                f"base={path_item.get('base_search_cost')} truth={path_item.get('truth_cost')} "
                f"node={path_node.get('id')} type={path_node.get('type')} text={path_node.get('text', '')}"
            )
    return 0


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


IMMUTABLE_NODE_UPDATE_FIELDS = {"id", "type"}


def _node_update_list(value: Any, field: str) -> list[dict[str, Any]]:
    updates = _object_list(value, field)
    seen: set[str] = set()
    for index, update in enumerate(updates):
        node_id = update.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise ValueError(f"{field}[{index}] missing string id")
        if node_id in seen:
            raise ValueError(f"{field}[{index}] duplicate id {node_id}")
        seen.add(node_id)
        changes = update.get("set")
        if not isinstance(changes, dict) or not changes:
            raise ValueError(f"{field}[{index}].set must be a non-empty object")
        for immutable_field in sorted(IMMUTABLE_NODE_UPDATE_FIELDS):
            if immutable_field in changes:
                raise ValueError(f"{field}[{index}].set cannot change {immutable_field}")
    return updates


def _node_update_snapshots(state: dict[str, Any], updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    nodes = by_id(state.get("nodes", []), "node")
    return [
        {
            "id": str(update["id"]),
            "before": json.loads(json.dumps(nodes[str(update["id"])])),
        }
        for update in updates
        if str(update["id"]) in nodes
    ]


def _factor_update_snapshots(state: dict[str, Any], updates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    factors = by_id(state.get("factors", []), "factor")
    return [
        {
            "id": str(update["id"]),
            "before": json.loads(json.dumps(factors[str(update["id"])]))
            if str(update["id"]) in factors
            else None,
        }
        for update in updates
    ]


def _apply_node_updates(state: dict[str, Any], updates: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    if not updates:
        return []
    nodes = state.setdefault("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("nodes must be a list before node updates can be applied")
    node_indexes: dict[str, int] = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not node.get("id"):
            continue
        node_id = str(node["id"])
        if node_id in node_indexes:
            raise ValueError(f"nodes has duplicate id {node_id}")
        node_indexes[node_id] = index

    updated_specs: list[dict[str, Any]] = []
    for update in updates:
        node_id = str(update["id"])
        if node_id not in node_indexes:
            raise ValueError(f"{field} id {node_id} does not exist")
        changes = update["set"]
        nodes[node_indexes[node_id]].update(changes)
        updated_specs.append({"id": node_id, "fields": sorted(changes)})
    return updated_specs


def _frontier_search_cost(item: dict[str, Any]) -> float:
    return float(item.get("search_cost", float("inf")))


def _frontier_item_positions(state: dict[str, Any]) -> dict[str, int]:
    return {
        str(item.get("id")): index
        for index, item in enumerate(state.get("frontier", []))
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }


def _choose_frontier_insertions(
    state: dict[str, Any],
    candidate_ids: list[str],
    *,
    new_ids: list[str] | None = None,
) -> tuple[set[str], list[dict[str, Any]]]:
    """Choose one inserted/active item per expansion signature using latest costs."""

    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    item_positions = _frontier_item_positions(state)
    new_id_set = set(new_ids or [])
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    seen_candidate_ids: set[str] = set()
    for candidate_order, raw_item_id in enumerate(candidate_ids):
        item_id = str(raw_item_id)
        if item_id in seen_candidate_ids:
            continue
        seen_candidate_ids.add(item_id)
        item = items.get(item_id)
        if item is None:
            continue
        grouped.setdefault(expansion_signature(item), []).append(
            {
                "id": item_id,
                "item": item,
                "source": "new" if item_id in new_id_set else "existing",
                "position": item_positions.get(item_id, 10**9),
                "candidate_order": candidate_order,
            }
        )

    kept_ids: set[str] = set()
    supersede_events: list[dict[str, Any]] = []
    for candidates in grouped.values():
        best = min(
            candidates,
            key=lambda candidate: (
                _frontier_search_cost(candidate["item"]),
                0 if candidate["source"] == "existing" else 1,
                candidate["position"],
                candidate["candidate_order"],
                candidate["id"],
            ),
        )
        kept_ids.add(str(best["id"]))
        if best["source"] != "new":
            continue
        for candidate in candidates:
            if candidate["id"] == best["id"]:
                continue
            if candidate["source"] == "existing":
                supersede_events.append(
                    {
                        "action": "supersede",
                        "item": candidate["id"],
                        "replacement": best["id"],
                        "reason": "duplicate expansion_signature; kept lower latest search_cost",
                    }
                )
    return kept_ids, supersede_events


def _dedupe_frontier_additions(
    state: dict[str, Any],
    active_ids: set[str],
    frontier_to_add: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Keep one active item per expansion signature using latest costs."""

    temp_state = json.loads(json.dumps(state))
    temp_state.setdefault("frontier", [])
    temp_state["frontier"].extend(json.loads(json.dumps(frontier_to_add)))
    new_ids = [str(item["id"]) for item in frontier_to_add]
    original_new_by_id = {str(item["id"]): item for item in frontier_to_add}
    item_positions = _frontier_item_positions(temp_state)
    active_candidate_ids = sorted(
        (str(item_id) for item_id in active_ids),
        key=lambda item_id: (item_positions.get(item_id, 10**9), item_id),
    )

    kept_ids, supersede_events = _choose_frontier_insertions(
        temp_state,
        active_candidate_ids + new_ids,
        new_ids=new_ids,
    )
    frontier_to_keep = [original_new_by_id[item_id] for item_id in new_ids if item_id in kept_ids]
    return frontier_to_keep, supersede_events


def _max_probe_concurrency(state: dict[str, Any], cli_value: int | None) -> int:
    if cli_value is not None:
        return cli_value
    search_policy = state.get("search_policy") if isinstance(state.get("search_policy"), dict) else {}
    value = search_policy.get("max_probe_concurrency")
    if isinstance(value, int) and value >= 1:
        return value
    return DEFAULT_MAX_PROBE_CONCURRENCY


def cmd_assign(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    # --force skips ordering/concurrency policy only; events before init are never valid.
    if not cursor["initialized"]:
        print("error: cannot assign before driver init event; run `next --pop` first", file=sys.stderr)
        return 1
    if cursor["stopped"] and not args.force:
        print("error: search already has a stop event; use --force to append anyway", file=sys.stderr)
        return 1
    if cursor["pending_item"] != args.item and not args.force:
        print(
            f"error: assign must target pending popped item {cursor['pending_item']!r}; use `next --pop` first or pass --force",
            file=sys.stderr,
        )
        return 1

    max_concurrency = _max_probe_concurrency(state, args.max_concurrency)
    if max_concurrency < 1:
        print("error: --max-concurrency must be a positive integer", file=sys.stderr)
        return 1
    in_flight_ids = set(cursor.get("in_flight_ids", set()))
    if len(in_flight_ids) >= max_concurrency and not args.force:
        print(
            f"error: max probe concurrency reached ({len(in_flight_ids)}/{max_concurrency}); merge an in-flight probe before assigning more",
            file=sys.stderr,
        )
        return 1

    items = by_id(state.get("frontier", []), "frontier item")
    if args.item not in items:
        print(f"error: frontier item not found: {args.item}", file=sys.stderr)
        return 1

    events = state.setdefault("events", [])
    if not isinstance(events, list):
        print("error: events must be a list before assign can append", file=sys.stderr)
        return 1
    event: dict[str, Any] = {
        "step": next_event_step(state),
        "action": "assign",
        "item": args.item,
        "max_concurrency": max_concurrency,
    }
    for attr, key in (
        ("agent", "agent"),
        ("run_id", "run_id"),
        ("probe", "probe"),
        ("concurrency_group", "concurrency_group"),
        ("reason", "reason"),
    ):
        value = getattr(args, attr)
        if value:
            event[key] = value
    events.append(event)

    result = validate_state(state)
    if result.errors:
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    dump_state(state, args.output, default_in_place_source(args))
    return 0


def cmd_expand(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    # --force skips the pending-pop ordering guard only; identity and event-shape
    # invariants (init first, item exists, item was popped) always hold.
    if not cursor["initialized"]:
        print("error: cannot expand before driver init event; run `next --pop` first", file=sys.stderr)
        return 1
    if args.item not in by_id(state.get("frontier", []), "frontier item"):
        print(f"error: frontier item not found: {args.item}", file=sys.stderr)
        return 1
    if args.item not in cursor["popped_ids"]:
        print(f"error: frontier item {args.item} has not been popped; run `next --pop` first", file=sys.stderr)
        return 1
    if cursor["stopped"] and not args.force:
        print("error: search already has a stop event; use --force to append anyway", file=sys.stderr)
        return 1
    in_flight_ids = set(cursor.get("in_flight_ids", set()))
    if cursor["pending_item"] != args.item and args.item not in in_flight_ids and not args.force:
        print(
            f"error: expand must target pending popped item {cursor['pending_item']!r} or an in-flight assigned item; use `next --pop`/`assign` first or pass --force",
            file=sys.stderr,
        )
        return 1

    patch = load_state(args.patch)
    if not isinstance(patch, dict):
        raise ValueError("expansion patch must be a JSON object")
    patch_errors = patch_schema_errors(patch)
    if patch_errors:
        for error in patch_errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    stop_reason = patch.get("stop_reason")
    stop_outcome = patch.get("stop_outcome")
    if stop_reason is not None:
        if not isinstance(stop_reason, str) or not stop_reason.strip():
            raise ValueError("stop_reason must be a non-empty string")
        if stop_outcome not in STOP_OUTCOMES:
            raise ValueError(f"stop_outcome must be one of {sorted(STOP_OUTCOMES)}, got {stop_outcome!r}")

    nodes_to_add = _object_list(patch.get("nodes"), "nodes")
    node_updates = _node_update_list(patch.get("update_nodes"), "update_nodes")
    edges_to_add = _object_list(patch.get("edges"), "edges")
    frontier_to_add = _object_list(patch.get("frontier"), "frontier")
    factors_to_update = _object_list(
        patch.get("update_factors", patch.get("factors")),
        "update_factors",
    )

    existing_nodes = {node.get("id") for node in state.get("nodes", []) if isinstance(node, dict)}
    existing_edges = {edge.get("id") for edge in state.get("edges", []) if isinstance(edge, dict) and edge.get("id")}
    existing_frontier = {item.get("id") for item in state.get("frontier", []) if isinstance(item, dict)}
    _ensure_unique_new_ids({str(item) for item in existing_nodes if item}, nodes_to_add, "nodes")
    _ensure_unique_new_ids({str(item) for item in existing_edges if item}, edges_to_add, "edges")
    _ensure_unique_new_ids({str(item) for item in existing_frontier if item}, frontier_to_add, "frontier")
    factor_update_ids = _ensure_object_ids(factors_to_update, "update_factors")

    for child in frontier_to_add:
        if child.get("parent") in (None, ""):
            child["parent"] = args.item

    active_ids = set(cursor["active_ids"])
    node_update_snapshots = _node_update_snapshots(state, node_updates)
    factor_update_snapshots = _factor_update_snapshots(state, factors_to_update)
    updated_node_specs = _apply_node_updates(state, node_updates, "update_nodes")
    state.setdefault("nodes", []).extend(nodes_to_add)
    state.setdefault("edges", []).extend(edges_to_add)
    factors = state.setdefault("factors", [])
    if not isinstance(factors, list):
        raise ValueError("factors must be a list before expand can update it")
    factor_indexes: dict[str, int] = {}
    for index, factor in enumerate(factors):
        if not isinstance(factor, dict) or not isinstance(factor.get("id"), str) or not factor.get("id"):
            continue
        factor_id = str(factor["id"])
        if factor_id in factor_indexes:
            raise ValueError(f"factors has duplicate id {factor_id}")
        factor_indexes[factor_id] = index
    for factor in factors_to_update:
        factor_id = str(factor["id"])
        if factor_id in factor_indexes:
            factors[factor_indexes[factor_id]] = factor
        else:
            factor_indexes[factor_id] = len(factors)
            factors.append(factor)
    frontier_to_add, supersede_events = _dedupe_frontier_additions(state, active_ids, frontier_to_add)
    state.setdefault("frontier", []).extend(frontier_to_add)
    sorted_frontier(state)

    events = state.setdefault("events", [])
    if not isinstance(events, list):
        raise ValueError("events must be a list before expand can append")
    event: dict[str, Any] = {
        "step": next_event_step(state),
        "action": "expand",
        "item": args.item,
        "add_nodes": [node["id"] for node in nodes_to_add],
        "add_edges": [edge["id"] for edge in edges_to_add],
        "add_frontier": [item["id"] for item in frontier_to_add],
        "update_factors": factor_update_ids,
    }
    for key in (
        "mode",
        "summary",
        "reason",
        "no_new_work_reason",
    ):
        if key in patch:
            event[key] = patch[key]
    if updated_node_specs:
        event["updated_nodes"] = updated_node_specs
    if node_update_snapshots:
        event["updated_node_snapshots"] = node_update_snapshots
    if factor_update_snapshots:
        event["updated_factor_snapshots"] = factor_update_snapshots
    events.append(event)
    for supersede_event in supersede_events:
        events.append({"step": next_event_step(state), **supersede_event})

    gaps = expansion_gaps(
        by_id(state.get("nodes", []), "node"),
        str(by_id(state.get("frontier", []), "frontier item")[args.item].get("node") or ""),
        {node["id"] for node in nodes_to_add},
        edges_to_add,
        [item["id"] for item in frontier_to_add],
        event,
    )
    if gaps and stop_policy_severity(state) == "error":
        for gap in gaps:
            print(f"error: {gap}", file=sys.stderr)
        return 1
    for gap in gaps:
        print(f"warning: {gap}", file=sys.stderr)

    # Expansion resolves its target. Check resulting terminal state before rank or
    # stop persistence; command failures remain non-writing because dump happens last.
    if stop_reason is not None and _stop_preflight(state, stop_reason, str(stop_outcome)) != 0:
        return 1

    patch_ranked = patch.get("rank") is True
    if patch_ranked:
        ranked = ranked_viable_candidates(state)
        if not ranked:
            raise ValueError("rank requested but no viable candidate_solution answers an accepted goal")
        events.append(
            {
                "step": next_event_step(state),
                "action": "rank",
                "item": args.item,
                "best": ranked[0]["node"],
                "belief": ranked[0]["belief"],
                "candidates": ranked,
            }
        )

    if stop_reason is not None:
        if stop_outcome in CANDIDATE_STOP_OUTCOMES and not patch_ranked and append_rank_event(state, item_id=args.item, top=10) != 0:
            return 1
        if append_stop_event(state, stop_reason, str(stop_outcome)) != 0:
            return 1

    result = validate_state(state)
    if result.errors:
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    dump_state(state, args.output, default_in_place_source(args))
    return 0


def append_rank_event(state: dict[str, Any], item_id: str | None = None, top: int = 10) -> int:
    if not search_cursor(state)["initialized"]:
        print("error: cannot rank before driver init event; run `next --pop` first", file=sys.stderr)
        return 1
    ranked = ranked_viable_candidates(state)
    if not ranked:
        print("error: no viable candidate_solution answers an accepted goal", file=sys.stderr)
        return 1

    if item_id is not None:
        items = by_id(state.get("frontier", []), "frontier item")
        if not isinstance(item_id, str) or item_id not in items:
            print(f"error: frontier item not found: {item_id}", file=sys.stderr)
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
    if item_id is not None:
        event["item"] = item_id
    events.append(event)
    return 0


def _stop_preflight(state: dict[str, Any], reason: str, outcome: str) -> int:
    """Reject terminal events that would make the search cursor incoherent."""
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
    cursor = search_cursor(state)
    if not cursor.get("initialized"):
        print("error: cannot stop before driver init event", file=sys.stderr)
        return 1
    if cursor.get("stopped"):
        print("error: search already has a stop event", file=sys.stderr)
        return 1
    pending_item = cursor.get("pending_item")
    if pending_item:
        print(
            f"error: cannot stop while pending popped item {pending_item} is unresolved; expand, assign, or rank it first",
            file=sys.stderr,
        )
        return 1
    in_flight_ids = set(cursor.get("in_flight_ids", set()))
    if in_flight_ids:
        print(
            f"error: cannot stop while assigned items remain in-flight: {sorted(in_flight_ids)}",
            file=sys.stderr,
        )
        return 1
    if outcome == "frontier_exhausted" and cursor.get("active_ids"):
        print(
            "error: frontier_exhausted stop requires no active frontier work; "
            f"remaining items: {sorted(cursor['active_ids'])}",
            file=sys.stderr,
        )
        return 1
    if outcome in CANDIDATE_STOP_OUTCOMES:
        unanswered = unanswered_goal_messages(state)
        for message in unanswered:
            print(f"error: stop outcome {outcome!r} requires every accepted goal answered; {message}", file=sys.stderr)
        if unanswered:
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
    events = state["events"]
    assert isinstance(events, list)
    events.append({"step": next_event_step(state), "action": "stop", "reason": reason.strip(), "outcome": outcome})
    return 0


def cmd_rank(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    item_id = args.item or cursor.get("pending_item")
    if append_rank_event(state, item_id=item_id, top=args.top) != 0:
        return 1
    dump_state(state, args.output, default_in_place_source(args))
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    # Preflight all terminal invariants before candidate auto-ranking can append
    # a rank event.
    if _stop_preflight(state, args.reason, args.outcome) != 0:
        return 1
    if args.outcome in CANDIDATE_STOP_OUTCOMES:
        cursor = search_cursor(state)
        item_id = args.item or cursor.get("pending_item")
        if append_rank_event(state, item_id=item_id, top=args.top) != 0:
            return 1
    if append_stop_event(state, args.reason, args.outcome) != 0:
        return 1
    dump_state(state, args.output, default_in_place_source(args))
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    path = reconstruct_path(state, args.item)
    if args.json:
        print(strict_json_dumps(path, indent=2, ensure_ascii=False))
    else:
        for step in path:
            item = step["item"]
            node = step["node"]
            print(
                f"{item.get('id')} search={item.get('search_cost')} base={item.get('base_search_cost')} "
                f"truth={item.get('truth_cost')} node={node.get('id')} type={node.get('type')} text={node.get('text', '')}"
            )
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

    record = sub.add_parser("record", help="append graph progress without the frontier queue and refresh <state>.html")
    record.add_argument("state", help="state JSON path, or - for stdin")
    record.add_argument("--patch", required=True, help="patch JSON path with reason and nodes/update_nodes/edges/factors, or - for stdin")
    record.add_argument("-o", "--output", help="write updated state to path")
    record.set_defaults(func=cmd_record)

    seed = sub.add_parser("seed", help="apply root ledger/frontier seed patch and optional node updates")
    seed.add_argument("state", help="state JSON path, or - for stdin")
    seed.add_argument("--patch", required=True, help="initial seed patch JSON path, or - for stdin")
    seed.add_argument("-o", "--output", help="write seeded state to path")
    seed.add_argument("-i", "--in-place", action="store_true", help="optional; default already rewrites input file")
    seed.set_defaults(func=cmd_seed)

    validate = sub.add_parser("validate", help="validate graph/search state")
    validate.add_argument("state", help="state JSON path, or - for stdin")
    validate.set_defaults(func=cmd_validate)

    schema = sub.add_parser("schema", help="emit a packaged JSON Schema")
    schema.add_argument("name", choices=("state", "patch"), help="schema to emit")
    schema.add_argument("-o", "--output", help="write schema JSON to path instead of stdout")
    schema.set_defaults(func=cmd_schema)

    doctor = sub.add_parser("doctor", help="validate state and summarize costs/frontier/audit health")
    doctor.add_argument("state", help="state JSON path, or - for stdin")
    doctor.set_defaults(func=cmd_doctor)

    stop_review = sub.add_parser("stop-review", help="run semantic stop-review checklist for a stopped state")
    stop_review.add_argument("state", help="state JSON path, or - for stdin")
    stop_review.add_argument("--draft", help="optional final answer draft to compare against the derived best candidate")
    stop_review.add_argument("--strict-warnings", action="store_true", help="treat validation/audit warnings as required fixes")
    stop_review.set_defaults(func=cmd_stop_review)

    costs = sub.add_parser("costs", help="compute truth_cost/search_cost")
    costs.add_argument("state", help="state JSON path, or - for stdin")
    costs.add_argument("-o", "--output", help="write result to path, or - for stdout, instead of default in-place/stdout")
    costs.add_argument("-i", "--in-place", action="store_true", help="optional; default already rewrites input file")
    costs.set_defaults(func=cmd_costs)

    audit = sub.add_parser("audit", help="audit strict-search compact events")
    audit.add_argument("state", help="state JSON path, or - for stdin")
    audit.set_defaults(func=cmd_audit)

    sort = sub.add_parser("sort", help="compute costs and sort frontier by search_cost")
    sort.add_argument("state", help="state JSON path, or - for stdin")
    sort.add_argument("-o", "--output", help="write result to path, or - for stdout, instead of default in-place/stdout")
    sort.add_argument("-i", "--in-place", action="store_true", help="optional; default already rewrites input file")
    sort.set_defaults(func=cmd_sort)

    frontier = sub.add_parser("frontier", help="show sorted active frontier derived from events")
    frontier.add_argument("state", help="state JSON path, or - for stdin")
    frontier.add_argument("--all", action="store_true", help="show all frontier items, not only active virtual frontier")
    frontier.add_argument("--json", action="store_true", help="print JSON instead of compact text")
    frontier.add_argument("--limit", type=int, help="maximum number of rows")
    frontier.set_defaults(func=cmd_frontier)

    next_cmd = sub.add_parser("next", help="show or persistently pop the lowest-cost active frontier item")
    next_cmd.add_argument("state", help="state JSON path, or - for stdin")
    next_cmd.add_argument("--pop", action="store_true", help="append init/pop events for the lowest-cost item")
    next_cmd.add_argument("-o", "--output", help="write mutated state to path when --pop is used")
    next_cmd.add_argument("-i", "--in-place", action="store_true", help="optional; default already rewrites input file when --pop is used")
    next_cmd.add_argument("--json", action="store_true", help="print JSON item/path context")
    next_cmd.set_defaults(func=cmd_next)

    assign = sub.add_parser("assign", help="record the pending popped frontier item as async in-flight probe work")
    assign.add_argument("state", help="state JSON path, or - for stdin")
    assign.add_argument("--item", required=True, help="pending popped frontier item being assigned")
    assign.add_argument("--agent", help="subagent/worker name handling the probe")
    assign.add_argument("--run-id", help="external async run id")
    assign.add_argument("--probe", help="test/probe node id, when a graph node represents the assigned work")
    assign.add_argument("--concurrency-group", help="optional group for human-readable async coordination")
    assign.add_argument("--max-concurrency", type=int, help=f"maximum allowed in-flight probes; defaults to search_policy.max_probe_concurrency or {DEFAULT_MAX_PROBE_CONCURRENCY}")
    assign.add_argument("--reason", help="why this item is being delegated")
    assign.add_argument("-o", "--output", help="write mutated state to path")
    assign.add_argument("-i", "--in-place", action="store_true", help="optional; default already rewrites input file")
    assign.add_argument("--force", action="store_true", help="skip pending-pop and concurrency guards; driver init is still required")
    assign.set_defaults(func=cmd_assign)

    expand = sub.add_parser("expand", help="append nodes/edges/frontier, update existing nodes, and record an expand event")
    expand.add_argument("state", help="state JSON path, or - for stdin")
    expand.add_argument("--item", required=True, help="popped frontier item being expanded")
    expand.add_argument("--patch", required=True, help="JSON patch path, or - for stdin")
    expand.add_argument("-o", "--output", help="write mutated state to path")
    expand.add_argument("-i", "--in-place", action="store_true", help="optional; default already rewrites input file")
    expand.add_argument("--force", action="store_true", help="skip the pending-pop ordering guard; the item must still exist and have been popped")
    expand.set_defaults(func=cmd_expand)

    rank = sub.add_parser("rank", help="record current best viable candidate_solution by derived belief")
    rank.add_argument("state", help="state JSON path, or - for stdin")
    rank.add_argument("--item", help="frontier item id; defaults to pending popped item when one exists")
    rank.add_argument("--top", type=int, default=10, help="number of ranked candidates to include in the event")
    rank.add_argument("-o", "--output", help="write mutated state to path")
    rank.add_argument("-i", "--in-place", action="store_true", help="optional; default already rewrites input file")
    rank.set_defaults(func=cmd_rank)

    stop = sub.add_parser("stop", help="rank candidate-bearing outcomes when needed, then append a stop event")
    stop.add_argument("state", help="state JSON path, or - for stdin")
    stop.add_argument("--reason", required=True, help="why search is stopping")
    stop.add_argument("--outcome", required=True, choices=sorted(STOP_OUTCOMES), help="structured stop outcome")
    stop.add_argument("--item", help="frontier item id for the rank event; defaults to pending popped item when one exists")
    stop.add_argument("--top", type=int, default=10, help="number of ranked candidates to include for candidate-bearing outcomes")
    stop.add_argument("-o", "--output", help="write mutated state to path")
    stop.add_argument("-i", "--in-place", action="store_true", help="optional; default already rewrites input file")
    stop.set_defaults(func=cmd_stop)

    path = sub.add_parser("path", help="reconstruct parent-pointer path for a frontier item")
    path.add_argument("state", help="state JSON path, or - for stdin")
    path.add_argument("item", help="frontier item id, e.g. Q7")
    path.add_argument("--json", action="store_true", help="print JSON instead of compact text")
    path.set_defaults(func=cmd_path)

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
