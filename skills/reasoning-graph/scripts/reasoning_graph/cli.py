"""Command-line interface for the reasoning graph helper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .audit import audit_state
from .costs import compute_costs, sorted_frontier, sorted_frontier_items
from .frontier import expansion_signature, item_view, next_event_step, reconstruct_path, search_cursor
from .models import STOP_OUTCOMES
from .render import html_document, presentation_node_ids, to_mermaid
from .state import by_id, dump_state, load_state
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


def cmd_costs(args: argparse.Namespace) -> int:
    state = compute_costs(load_state(args.state))
    dump_state(state, args.output, args.state if args.in_place else None)
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
            "events={events} pops={pops} expansions={expansions} selections={selections}".format(**stats)
        )
        return 0
    return 1


STRICT_STOP_POLICY = {
    "min_viable_candidates": 3,
    "belief_threshold": 0.8,
    "max_live_frontier_items": 0,
    "require_frontier_exhausted_for_epistemic_stop": True,
    "severity": "error",
}


DEFAULT_BRANCH_POLICY = {
    "high_salience_min_children": 3,
    "low_prior_wildcard_required": True,
    "enforce_on": "exhaustion_stop",
    "severity": "warning",
}


BENCHMARK_BRANCH_POLICY = {
    **DEFAULT_BRANCH_POLICY,
    "enforce_on": "always",
    "severity": "error",
}


def starter_state(profile: str, goal: str = "Solve the problem") -> dict[str, Any]:
    state: dict[str, Any] = {
        "summary": {"title": "Reasoning Graph", "answer": ""},
        "nodes": [{"id": "G1", "type": "goal", "text": goal}],
        "edges": [],
        "frontier": [],
    }
    if profile in {"strict", "benchmark"}:
        state["search_policy"] = {"estimated_remaining_weight": 1.0}
        state["stop_policy"] = dict(STRICT_STOP_POLICY)
        state["branch_policy"] = dict(BENCHMARK_BRANCH_POLICY if profile == "benchmark" else DEFAULT_BRANCH_POLICY)
    return state


def cmd_template(args: argparse.Namespace) -> int:
    state = starter_state(args.profile)
    dump_state(state, args.output)
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    goal = args.goal.strip()
    if not goal:
        print("error: --goal must be non-empty", file=sys.stderr)
        return 1
    profile = "strict" if args.strict else args.profile
    state = starter_state(profile, goal)
    dump_state(state, args.output)
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
        "doctor: nodes={nodes} edges={edges} frontier={frontier} active={active} pending={pending} stopped={stopped}".format(
            nodes=len(state.get("nodes", [])),
            edges=len(state.get("edges", [])),
            frontier=len(state.get("frontier", [])),
            active=len(cursor["active_ids"]),
            pending=cursor["pending_item"] or "none",
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
        "doctor: audit events={events} pops={pops} expansions={expansions} selections={selections}".format(**stats)
    )
    if not audit_result.ok:
        print("doctor: audit failed")
        return 1
    print("doctor: audit ok")
    return 0


def cmd_sort(args: argparse.Namespace) -> int:
    state = sorted_frontier(load_state(args.state))
    dump_state(state, args.output, args.state if args.in_place else None)
    return 0


def cmd_frontier(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    ids = None if args.all else cursor["active_ids"]
    rows = [item_view(state, item) for item in sorted_frontier_items(state, ids)]
    if args.limit is not None:
        rows = rows[: args.limit]
    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    else:
        if cursor["stopped"] and not args.all:
            print("search stopped; active frontier empty unless --all is used", file=sys.stderr)
        if cursor["pending_item"] and not args.all:
            print(f"pending expansion: {cursor['pending_item']}", file=sys.stderr)
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
        print(f"error: pending popped item {cursor['pending_item']} must be expanded or selected before next pop", file=sys.stderr)
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
        if not args.in_place and not args.output:
            print("error: --pop requires --in-place or --output so the pop event is persisted", file=sys.stderr)
            return 1
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
            "cost": item.get("search_cost", item.get("path_cost")),
        }
        evidence_version = item.get("evidence_version", state.get("evidence_version"))
        if evidence_version is not None:
            pop_event["evidence_version"] = evidence_version
        events.append(pop_event)
        dump_state(state, args.output, args.state if args.in_place else None)

    if args.json:
        print(json.dumps({"item": view, "path": path}, indent=2, ensure_ascii=False))
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
                f"  {path_item.get('id')} search={path_item.get('search_cost', path_item.get('path_cost'))} "
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


def _frontier_search_cost(item: dict[str, Any]) -> float:
    return float(item.get("search_cost", item.get("path_cost", float("inf"))))


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


def cmd_expand(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    cursor = search_cursor(state)
    if cursor["stopped"] and not args.force:
        print("error: search already has a stop event; use --force to append anyway", file=sys.stderr)
        return 1
    if cursor["pending_item"] != args.item and not args.force:
        print(
            f"error: expand must target pending popped item {cursor['pending_item']!r}; use `next --pop` first or pass --force",
            file=sys.stderr,
        )
        return 1

    patch = load_state(args.patch)
    if not isinstance(patch, dict):
        raise ValueError("expansion patch must be a JSON object")

    nodes_to_add = _object_list(patch.get("nodes", patch.get("add_node_objects")), "nodes")
    edges_to_add = _object_list(patch.get("edges", patch.get("add_edge_objects")), "edges")
    frontier_to_add = _object_list(patch.get("frontier", patch.get("add_frontier_objects")), "frontier")
    premise_groups_to_update = _object_list(
        patch.get("update_premise_groups", patch.get("premise_groups", patch.get("add_premise_group_objects"))),
        "update_premise_groups",
    )
    factors_to_update = _object_list(
        patch.get("update_factors", patch.get("factors", patch.get("add_factor_objects"))),
        "update_factors",
    )

    existing_nodes = {node.get("id") for node in state.get("nodes", []) if isinstance(node, dict)}
    existing_edges = {edge.get("id") for edge in state.get("edges", []) if isinstance(edge, dict) and edge.get("id")}
    existing_frontier = {item.get("id") for item in state.get("frontier", []) if isinstance(item, dict)}
    _ensure_unique_new_ids({str(item) for item in existing_nodes if item}, nodes_to_add, "nodes")
    _ensure_unique_new_ids({str(item) for item in existing_edges if item}, edges_to_add, "edges")
    _ensure_unique_new_ids({str(item) for item in existing_frontier if item}, frontier_to_add, "frontier")
    premise_group_update_ids = _ensure_object_ids(premise_groups_to_update, "update_premise_groups")
    factor_update_ids = _ensure_object_ids(factors_to_update, "update_factors")

    for child in frontier_to_add:
        if child.get("parent") in (None, ""):
            child["parent"] = args.item

    active_ids = set(cursor["active_ids"])
    state.setdefault("nodes", []).extend(nodes_to_add)
    state.setdefault("edges", []).extend(edges_to_add)
    premise_groups = state.setdefault("premise_groups", [])
    if not isinstance(premise_groups, list):
        raise ValueError("premise_groups must be a list before expand can update it")
    premise_group_indexes: dict[str, int] = {}
    for index, group in enumerate(premise_groups):
        if not isinstance(group, dict) or not isinstance(group.get("id"), str) or not group.get("id"):
            continue
        group_id = str(group["id"])
        if group_id in premise_group_indexes:
            raise ValueError(f"premise_groups has duplicate id {group_id}")
        premise_group_indexes[group_id] = index
    for group in premise_groups_to_update:
        group_id = str(group["id"])
        if group_id in premise_group_indexes:
            premise_groups[premise_group_indexes[group_id]] = group
        else:
            premise_group_indexes[group_id] = len(premise_groups)
            premise_groups.append(group)
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
        "update_premise_groups": premise_group_update_ids,
        "update_factors": factor_update_ids,
    }
    for key in (
        "mode",
        "summary",
        "reason",
        "updated_nodes",
        "no_new_work_reason",
        "no_reopen_reason",
        "under_branching_reason",
        "existing_sibling_frontier",
    ):
        if key in patch:
            event[key] = patch[key]
    events.append(event)
    for supersede_event in supersede_events:
        events.append({"step": next_event_step(state), **supersede_event})

    select_spec = patch.get("select", patch.get("solution"))
    selected_node: str | None = None
    selected_item = args.item
    if isinstance(select_spec, str):
        selected_node = select_spec
    elif isinstance(select_spec, dict):
        raw_selected_node = select_spec.get("node")
        raw_selected_item = select_spec.get("item")
        if isinstance(raw_selected_node, str):
            selected_node = raw_selected_node
        if isinstance(raw_selected_item, str):
            selected_item = raw_selected_item
    elif isinstance(patch.get("solution_node"), str):
        selected_node = patch["solution_node"]
    if selected_node:
        frontier_items = by_id(state.get("frontier", []), "frontier item")
        if selected_item not in frontier_items:
            raise ValueError(f"selected item {selected_item} is not a frontier item")
        events.append(
            {
                "step": next_event_step(state),
                "action": "select",
                "item": selected_item,
                "node": selected_node,
                "cost": frontier_items[selected_item].get("search_cost", frontier_items[selected_item].get("path_cost")),
            }
        )

    stop_reason = patch.get("stop_reason")
    if stop_reason is None and isinstance(patch.get("stop"), str):
        stop_reason = patch.get("stop")
    if stop_reason is not None:
        if not isinstance(stop_reason, str) or not stop_reason.strip():
            raise ValueError("stop_reason must be a non-empty string")
        stop_outcome = patch.get("stop_outcome", patch.get("outcome"))
        if stop_outcome not in STOP_OUTCOMES:
            raise ValueError(f"stop_outcome must be one of {sorted(STOP_OUTCOMES)}, got {stop_outcome!r}")
        events.append({"step": next_event_step(state), "action": "stop", "reason": stop_reason, "outcome": stop_outcome})

    result = validate_state(state)
    if result.errors:
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)

    dump_state(state, args.output, args.state if args.in_place else None)
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    nodes = by_id(state.get("nodes", []), "node")
    cursor = search_cursor(state)

    item_id = args.item or cursor.get("pending_item")
    if not isinstance(item_id, str) or not item_id:
        print("error: no pending popped item; use `next --pop` first or pass --item with --force", file=sys.stderr)
        return 1
    if item_id not in items:
        print(f"error: frontier item not found: {item_id}", file=sys.stderr)
        return 1
    if cursor.get("pending_item") not in (None, item_id) and not args.force:
        print(f"error: pending popped item is {cursor.get('pending_item')}, not {item_id}; use --force to override", file=sys.stderr)
        return 1
    if cursor.get("pending_item") is None and not args.force:
        print("error: select expects a pending popped item; use --force to append anyway", file=sys.stderr)
        return 1

    node = nodes.get(args.node)
    if node is None:
        print(f"error: candidate_solution node not found: {args.node}", file=sys.stderr)
        return 1
    if node.get("type") != "candidate_solution":
        print(f"error: node {args.node} must be candidate_solution", file=sys.stderr)
        return 1

    events = state.setdefault("events", [])
    if not isinstance(events, list):
        print("error: events must be a list before select can append", file=sys.stderr)
        return 1
    events.append(
        {
            "step": next_event_step(state),
            "action": "select",
            "item": item_id,
            "node": args.node,
            "cost": items[item_id].get("search_cost", items[item_id].get("path_cost")),
        }
    )
    dump_state(state, args.output, args.state if args.in_place else None)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    reason = args.reason.strip()
    if not reason:
        print("error: stop reason must be non-empty", file=sys.stderr)
        return 1
    if args.outcome not in STOP_OUTCOMES:
        print(f"error: --outcome must be one of {sorted(STOP_OUTCOMES)}, got {args.outcome!r}", file=sys.stderr)
        return 1
    events = state.setdefault("events", [])
    if not isinstance(events, list):
        print("error: events must be a list before stop can append", file=sys.stderr)
        return 1
    events.append({"step": next_event_step(state), "action": "stop", "reason": reason, "outcome": args.outcome})
    dump_state(state, args.output, args.state if args.in_place else None)
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    path = reconstruct_path(state, args.item)
    if args.json:
        print(json.dumps(path, indent=2, ensure_ascii=False))
    else:
        for step in path:
            item = step["item"]
            node = step["node"]
            print(
                f"{item.get('id')} search={item.get('search_cost', item.get('path_cost'))} base={item.get('base_search_cost')} "
                f"truth={item.get('truth_cost')} node={node.get('id')} type={node.get('type')} text={node.get('text', '')}"
            )
    return 0


def cmd_mermaid(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    include_nodes = presentation_node_ids(state) if args.view == "presentation" else None
    source = to_mermaid(state, include_nodes, group_by_type=args.grouped or args.view == "audit")
    if args.output:
        Path(args.output).write_text(source, encoding="utf-8")
    else:
        sys.stdout.write(source)
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
    document = html_document(state, source, args.spacing)
    if args.output:
        Path(args.output).write_text(document, encoding="utf-8")
    else:
        sys.stdout.write(document)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reasoning graph helper")
    sub = parser.add_subparsers(dest="command", required=True)

    template = sub.add_parser("template", help="emit a starter state template")
    template.add_argument("profile", choices=("minimal", "strict", "benchmark"), help="template profile")
    template.add_argument("-o", "--output", help="write result to path instead of stdout")
    template.set_defaults(func=cmd_template)

    init = sub.add_parser("init", help="emit a starter state for a goal")
    init.add_argument("--goal", required=True, help="goal text for G1")
    init.add_argument("--profile", choices=("minimal", "strict", "benchmark"), default="minimal", help="starter profile")
    init.add_argument("--strict", action="store_true", help="shortcut for --profile strict")
    init.add_argument("-o", "--output", help="write result to path instead of stdout")
    init.set_defaults(func=cmd_init)

    validate = sub.add_parser("validate", help="validate graph/search state")
    validate.add_argument("state", help="state JSON path, or - for stdin")
    validate.set_defaults(func=cmd_validate)

    doctor = sub.add_parser("doctor", help="validate state and summarize costs/frontier/audit health")
    doctor.add_argument("state", help="state JSON path, or - for stdin")
    doctor.set_defaults(func=cmd_doctor)

    costs = sub.add_parser("costs", help="compute truth_cost/search_cost; path_cost is emitted as a legacy alias")
    costs.add_argument("state", help="state JSON path, or - for stdin")
    costs.add_argument("-o", "--output", help="write result to path instead of stdout")
    costs.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
    costs.set_defaults(func=cmd_costs)

    audit = sub.add_parser("audit", help="audit strict-search compact events")
    audit.add_argument("state", help="state JSON path, or - for stdin")
    audit.set_defaults(func=cmd_audit)

    sort = sub.add_parser("sort", help="compute costs and sort frontier by search_cost")
    sort.add_argument("state", help="state JSON path, or - for stdin")
    sort.add_argument("-o", "--output", help="write result to path instead of stdout")
    sort.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
    sort.set_defaults(func=cmd_sort)

    frontier = sub.add_parser("frontier", help="show sorted active frontier derived from events")
    frontier.add_argument("state", help="state JSON path, or - for stdin")
    frontier.add_argument("--all", action="store_true", help="show all frontier items, not only active virtual frontier")
    frontier.add_argument("--json", action="store_true", help="print JSON instead of compact text")
    frontier.add_argument("--limit", type=int, help="maximum number of rows")
    frontier.set_defaults(func=cmd_frontier)

    next_cmd = sub.add_parser("next", help="show or persistently pop the lowest-cost active frontier item")
    next_cmd.add_argument("state", help="state JSON path, or - for stdin")
    next_cmd.add_argument("--pop", action="store_true", help="append init/pop events for the selected item")
    next_cmd.add_argument("-o", "--output", help="write mutated state to path when --pop is used")
    next_cmd.add_argument("-i", "--in-place", action="store_true", help="rewrite input file when --pop is used")
    next_cmd.add_argument("--json", action="store_true", help="print JSON item/path context")
    next_cmd.set_defaults(func=cmd_next)

    expand = sub.add_parser("expand", help="append nodes/edges/frontier from a JSON expansion patch and record an expand event")
    expand.add_argument("state", help="state JSON path, or - for stdin")
    expand.add_argument("--item", required=True, help="popped frontier item being expanded")
    expand.add_argument("--patch", required=True, help="JSON patch path, or - for stdin")
    expand.add_argument("-o", "--output", help="write mutated state to path")
    expand.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
    expand.add_argument("--force", action="store_true", help="skip pending-pop guard")
    expand.set_defaults(func=cmd_expand)

    select = sub.add_parser("select", help="record selected candidate_solution for the pending popped item")
    select.add_argument("state", help="state JSON path, or - for stdin")
    select.add_argument("--node", required=True, help="candidate_solution node id")
    select.add_argument("--item", help="frontier item id; defaults to pending popped item")
    select.add_argument("-o", "--output", help="write mutated state to path")
    select.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
    select.add_argument("--force", action="store_true", help="append even when there is no pending popped item")
    select.set_defaults(func=cmd_select)

    stop = sub.add_parser("stop", help="append a stop event")
    stop.add_argument("state", help="state JSON path, or - for stdin")
    stop.add_argument("--reason", required=True, help="why search is stopping")
    stop.add_argument("--outcome", required=True, choices=sorted(STOP_OUTCOMES), help="structured stop outcome")
    stop.add_argument("-o", "--output", help="write mutated state to path")
    stop.add_argument("-i", "--in-place", action="store_true", help="rewrite input file")
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

    html_cmd = sub.add_parser("html", help="render CDN Mermaid HTML")
    html_cmd.add_argument("state", help="state JSON path, or - for stdin")
    html_cmd.add_argument("-o", "--output", help="write HTML to path")
    html_cmd.add_argument("--spacing", choices=("default", "relaxed", "wide", "compact"), default="default", help="Mermaid flowchart spacing preset")
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
