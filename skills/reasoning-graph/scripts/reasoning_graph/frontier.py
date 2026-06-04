"""Frontier/event cursor and path reconstruction helpers."""

from __future__ import annotations

from typing import Any

from .costs import compute_costs
from .state import by_id, node_label


def next_event_step(state: dict[str, Any]) -> int:
    events = state.get("events")
    if not isinstance(events, list):
        return 1
    steps = [event.get("step") for event in events if isinstance(event, dict) and isinstance(event.get("step"), int)]
    return max(steps, default=0) + 1


def search_cursor(state: dict[str, Any]) -> dict[str, Any]:
    """Derive the active virtual frontier from compact events.

    If no strict events exist yet, every frontier item is considered active so
    older/loose states remain usable with `frontier` and `next`.
    """

    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    events = state.get("events")
    if not isinstance(events, list) or not events:
        return {
            "active_ids": {item_id for item_id in items},
            "pending_item": None,
            "initialized": False,
            "stopped": False,
        }

    active_ids: set[str] = set()
    popped_ids: set[str] = set()
    pending_item: str | None = None
    initialized = False
    stopped = False

    for event in events:
        if not isinstance(event, dict):
            continue
        action = event.get("action")
        if action == "init":
            init_frontier = event.get("frontier") if isinstance(event.get("frontier"), list) else []
            for item_id in init_frontier:
                if isinstance(item_id, str) and item_id in items and item_id not in popped_ids:
                    active_ids.add(item_id)
            initialized = True
        elif action == "pop":
            item_id = event.get("item")
            if isinstance(item_id, str) and item_id in items:
                active_ids.discard(item_id)
                popped_ids.add(item_id)
                pending_item = item_id
        elif action == "expand":
            item_id = event.get("item")
            if item_id == pending_item:
                pending_item = None
            added_frontier = event.get("add_frontier") if isinstance(event.get("add_frontier"), list) else []
            for child_id in added_frontier:
                if isinstance(child_id, str) and child_id in items and child_id not in popped_ids:
                    active_ids.add(child_id)
        elif action in {"select", "solution"}:
            item_id = event.get("item")
            if item_id == pending_item:
                pending_item = None
        elif action == "stop":
            stopped = True
            pending_item = None
            active_ids.clear()

    if not initialized:
        active_ids = {item_id for item_id in items}

    return {
        "active_ids": active_ids,
        "pending_item": pending_item,
        "initialized": initialized,
        "stopped": stopped,
    }


def related_brief(item: dict[str, Any]) -> str:
    related = item.get("related")
    if not isinstance(related, list) or not related:
        return ""
    return ",".join(str(node_id) for node_id in related[:8])


def scratch_brief(item: dict[str, Any]) -> str:
    scratch = item.get("scratch")
    if not isinstance(scratch, list) or not scratch:
        return ""
    return "; ".join(str(note) for note in scratch[:2])


def item_view(state: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    nodes = by_id(state.get("nodes", []), "node")
    node = nodes.get(str(item.get("node")), {})
    return {
        "id": item.get("id"),
        "node": item.get("node"),
        "node_type": node.get("type"),
        "search_cost": item.get("search_cost", item.get("path_cost")),
        "path_cost": item.get("path_cost"),
        "truth_cost": item.get("truth_cost"),
        "step_cost": item.get("step_cost"),
        "step_truth_cost": item.get("step_truth_cost"),
        "parent": item.get("parent"),
        "active_assumptions": item.get("active_assumptions", []),
        "related": item.get("related", []),
        "related_brief": related_brief(item),
        "scratch": item.get("scratch", []),
        "scratch_brief": scratch_brief(item),
        "text": node.get("text", ""),
    }


def reconstruct_path(state: dict[str, Any], item_id: str) -> list[dict[str, Any]]:
    compute_costs(state)
    items = by_id(state.get("frontier", []), "frontier item")
    nodes = by_id(state.get("nodes", []), "node")
    if item_id not in items:
        raise SystemExit(f"frontier item not found: {item_id}")
    path: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = item_id
    while current:
        if current in seen:
            raise SystemExit(f"cycle in parent chain at {current}")
        seen.add(current)
        item = items[current]
        node = nodes.get(str(item.get("node")), {})
        path.append({"item": item, "node": node})
        current = item.get("parent") or ""
    path.reverse()
    return path
