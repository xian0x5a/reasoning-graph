"""Command-line interface for the reasoning graph helper."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .audit import audit_state
from .index import index_document
from .render import html_document, to_mermaid
from .schema_validation import patch_schema_errors, standalone_schema
from .source_quotes import quote_mismatch_messages
from .state import dump_state, edge_id, load_state, strict_json_dumps, write_output_text
from .validation import authored_field_errors, validate_state


def cmd_schema(args: argparse.Namespace) -> int:
    schema_name = f"{args.name}.schema.json"
    text = strict_json_dumps(standalone_schema(schema_name), indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    write_output_text(text, args.output)
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    """Read-only: report the status first, then what failed or what an answer still needs."""
    state = load_state(args.state)
    quote_errors = _quote_errors(state, args.state) if isinstance(state, dict) else []
    report = audit_state(state, quote_errors)
    print(report.status)
    for need in report.needs:
        print(f"needs: {need}")
    for warning in report.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    return 0 if report.ok else 1


def starter_state(goal: str = "Solve the problem") -> dict[str, Any]:
    return {
        "summary": {"title": "Reasoning Graph", "answer": ""},
        "nodes": [{"id": "G1", "type": "goal", "text": goal}],
        "edges": [],
    }


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
    state = starter_state(goal)
    dump_state(state, args.output)
    if args.output and args.output != "-":
        # Said aloud so the first patch does not add the goal again.
        goal_node = state["nodes"][0]
        print(f"created {args.output} with goal {goal_node['id']}: {goal_node['text']}")
    return 0


RECORD_PATCH_FIELDS = {
    "answer",
    "nodes", "update_nodes", "remove_nodes",
    "edges", "update_edges", "remove_edges",
    "factors", "remove_factors",
}


def removed_patch_field_errors(patch: dict[str, Any]) -> list[str]:
    if "reason" not in patch:
        return []
    # A sentence per record that only the index read, and only the last one (issue #38).
    return ["reason was removed: the state keeps no log; put what is worth keeping in a note on the node or edge it concerns"]


def _apply_graph_patch(state: dict[str, Any], patch: dict[str, Any]) -> None:
    """Apply removals, then updates, then additions.

    Additions are appended and nothing is reordered: the list order is the order of the work,
    and nothing else records it.
    """
    nodes_to_add = _object_list(patch.get("nodes"), "nodes")
    edges_to_add = _object_list(patch.get("edges"), "edges")
    factors_to_upsert = _object_list(patch.get("factors"), "factors")
    node_updates = _field_update_list(patch.get("update_nodes"), "update_nodes")
    edge_updates = _field_update_list(patch.get("update_edges"), "update_edges")

    removed_node_ids = _remove_by_id(state, "nodes", patch.get("remove_nodes") or [])
    # An edge means nothing without both endpoints, so removing a node removes its edges.
    incident_edge_ids = [
        edge_id(edge)
        for edge in state.get("edges", [])
        if isinstance(edge, dict) and (edge.get("from") in removed_node_ids or edge.get("to") in removed_node_ids)
    ]
    _remove_by_id(state, "edges", [*(patch.get("remove_edges") or []), *incident_edge_ids])
    _remove_by_id(state, "factors", patch.get("remove_factors") or [])

    _apply_field_updates(state.get("nodes", []), node_updates, "update_nodes")
    _apply_field_updates(state.get("edges", []), edge_updates, "update_edges")

    existing_nodes = {node.get("id") for node in state.get("nodes", []) if isinstance(node, dict)}
    _ensure_unique_new_ids({str(item) for item in existing_nodes if item}, nodes_to_add, "nodes")
    existing_edges = {edge_id(edge) for edge in state.get("edges", []) if isinstance(edge, dict)}
    for edge in edges_to_add:
        if edge_id(edge) in existing_edges:
            raise ValueError(f"edge {edge_id(edge)} already exists: one edge per ordered pair; change it with update_edges")
        existing_edges.add(edge_id(edge))
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


def _quote_errors(state: dict[str, Any], state_path: str) -> list[str]:
    source_base_dir = Path(state_path).parent if state_path != "-" else Path.cwd()
    # Malformed nodes are validation's to report.
    nodes = [node for node in state.get("nodes", []) if isinstance(node, dict)]
    return [message for node in nodes for message in quote_mismatch_messages(node, source_base_dir)]


def _passes_quote_and_graph_checks(state: dict[str, Any], state_path: str) -> bool:
    """Recheck every quote and validate the graph; print every failure and return False on any.

    The two checks are independent, so one run lists everything to fix instead of one kind per retry.
    """
    quote_errors = _quote_errors(state, state_path)
    for message in quote_errors:
        print(f"error: {message}", file=sys.stderr)
    graph_valid = passes_validation(state)
    return graph_valid and not quote_errors


def passes_validation(state: dict[str, Any]) -> bool:
    """Validate the graph; report errors and return False if invalid."""
    result = validate_state(state)
    for error in result.errors:
        print(f"error: {error}", file=sys.stderr)
    if result.errors:
        return False
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return True


def write_views(state: dict[str, Any], args: argparse.Namespace) -> None:
    """Refresh the two views beside the written state: <state>.html for a human watching
    progress, <state>.index.md for the agent to reread instead of the whole state."""
    target = getattr(args, "output", None) or args.state
    if target == "-":
        return
    views = {
        ".html": html_document(state, to_mermaid(state), "default", "mermaid"),
        ".index.md": index_document(state),
    }
    for suffix, document in views.items():
        view_path = Path(target).with_suffix(suffix)
        # A record can leave a view byte-identical; skipping the rewrite saves the disk
        # write and keeps the file's mtime a real change signal.
        if view_path.is_file() and view_path.read_text(encoding="utf-8") == document:
            continue
        write_output_text(document, str(view_path))


def cmd_record(args: argparse.Namespace) -> int:
    """Apply a patch to the graph, then refresh the views beside the state."""
    state = load_state(args.state)
    patch = load_state(args.patch)
    if not isinstance(patch, dict):
        raise ValueError("record patch must be a JSON object")
    added = {field: patch[field] if isinstance(patch.get(field), list) else [] for field in ("nodes", "edges")}
    # Listed first: the schema rejects a removed field too, but does not say what replaced it.
    patch_errors = removed_patch_field_errors(patch) + authored_field_errors(added["nodes"], added["edges"]) + patch_schema_errors(patch)
    if patch_errors:
        for error in patch_errors:
            print(f"error: {error}", file=sys.stderr)
        return 1
    unsupported_fields = sorted(set(patch) - RECORD_PATCH_FIELDS)
    if unsupported_fields:
        print(f"error: record patch field(s) not allowed: {', '.join(unsupported_fields)}", file=sys.stderr)
        return 1
    _apply_graph_patch(state, patch)
    if "answer" in patch:
        # The claim `audit` judges. An empty answer withdraws it.
        state.setdefault("summary", {})["answer"] = patch["answer"].strip()

    # The checks judge the patched graph, so a patch may repair a hand edit.
    if not _passes_quote_and_graph_checks(state, args.state):
        return 1
    dump_state(state, args.output, default_in_place_source(args))
    write_views(state, args)
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    """Take in a hand-edited state: validate it, recheck every quote, and refresh the views."""
    state = load_state(args.state)
    if not _passes_quote_and_graph_checks(state, args.state):
        return 1
    print("ok")
    write_views(state, args)
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


def _item_id(item: dict[str, Any], key: str) -> Any:
    """The id a patch names an item of state[key] by; an edge carries none and is named by its ends."""
    return edge_id(item) if key == "edges" else item.get("id")


def _apply_field_updates(items: list[Any], updates: list[dict[str, Any]], field: str) -> None:
    """Set and unset fields on existing items by id."""
    items_by_id = {_item_id(item, field.removeprefix("update_")): item for item in items if isinstance(item, dict)}
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


def _remove_by_id(state: dict[str, Any], key: str, ids: list[str]) -> list[str]:
    """Remove items from state[key] by id and return the removed ids in order."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    items = state.get(key) or []
    present = {_item_id(item, key) for item in items if isinstance(item, dict)}
    for item_id in ids:
        if item_id not in present:
            raise ValueError(f"remove_{key} id {item_id} does not exist")
    state[key] = [item for item in items if not (isinstance(item, dict) and _item_id(item, key) in ids)]
    return ids


def cmd_mermaid(args: argparse.Namespace) -> int:
    state = load_state(args.state)
    write_output_text(to_mermaid(state), args.output)
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
    source = to_mermaid(state)
    render_mode = "offline" if args.offline else "mermaid"
    document = html_document(state, source, args.spacing, render_mode, _quote_errors(state, args.state))
    write_output_text(document, args.output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reasoning graph helper")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="emit a starter state for a goal")
    init.add_argument("--goal", required=True, help="goal text for G1")
    init.add_argument("-o", "--output", help="write result to path instead of stdout")
    init.set_defaults(func=cmd_init)

    record = sub.add_parser("record", help="apply a patch to the graph and refresh <state>.html and <state>.index.md")
    record.add_argument("state", help="state JSON path, or - for stdin")
    record.add_argument("--patch", required=True, help="patch JSON path, or - for stdin: any add, update, or remove operations, and the answer")
    record.add_argument("-o", "--output", help="write updated state to path")
    record.set_defaults(func=cmd_record)

    refresh = sub.add_parser("refresh", help="after a hand edit: validate, recheck quotes, and refresh the views")
    refresh.add_argument("state", help="state JSON path")
    refresh.set_defaults(func=cmd_refresh)

    schema = sub.add_parser("schema", help="emit a packaged JSON Schema")
    schema.add_argument("name", choices=("state", "patch"), help="schema to emit")
    schema.add_argument("-o", "--output", help="write schema JSON to path instead of stdout")
    schema.set_defaults(func=cmd_schema)

    audit = sub.add_parser("audit", help="read-only check of the graph, the quotes, and the claimed answer")
    audit.add_argument("state", help="state JSON path, or - for stdin")
    audit.set_defaults(func=cmd_audit)

    mermaid = sub.add_parser("mermaid", help="render Mermaid source")
    mermaid.add_argument("state", help="state JSON path, or - for stdin")
    mermaid.add_argument("-o", "--output", help="write Mermaid source to path")
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
