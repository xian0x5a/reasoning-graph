"""Frontier/event cursor and path reconstruction helpers."""

from __future__ import annotations

from typing import Any

from .costs import compute_costs
from .state import by_id, node_label


EXPANSION_SIGNATURE_CONTEXT_FIELDS = ("scope", "params", "budget")


def _canonical_signature_value(value: Any) -> Any:
    if isinstance(value, dict):
        return tuple(
            (str(key), _canonical_signature_value(value[key]))
            for key in sorted(value, key=lambda candidate: str(candidate))
        )
    if isinstance(value, list):
        return tuple(_canonical_signature_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_canonical_signature_value(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted((_canonical_signature_value(item) for item in value), key=repr))
    return value


def expansion_signature(item: dict[str, Any]) -> tuple[Any, ...]:
    """Return identity for work that would expand the same way.

    Parent/id/provenance fields are intentionally excluded. If path context
    should change expansion, encode it as assumptions or explicit params/scope.
    """

    active_assumptions = item.get("active_assumptions", [])
    if not isinstance(active_assumptions, list):
        active_assumptions = []
    return (
        ("node", _canonical_signature_value(item.get("node"))),
        ("active_assumptions", tuple(sorted(str(assumption) for assumption in active_assumptions))),
        *(
            (field, _canonical_signature_value(item.get(field)) if field in item else None)
            for field in EXPANSION_SIGNATURE_CONTEXT_FIELDS
        ),
    )


def next_event_step(state: dict[str, Any]) -> int:
    events = state.get("events")
    if not isinstance(events, list):
        return 1
    steps = [event.get("step") for event in events if isinstance(event, dict) and isinstance(event.get("step"), int)]
    return max(steps, default=0) + 1


def search_cursor(state: dict[str, Any]) -> dict[str, Any]:
    """Derive the active virtual frontier from compact events without mutating state.

    If no strict events exist yet, every frontier item is considered active so
    older/loose states remain usable with `frontier` and `next`.
    """

    items = by_id(state.get("frontier", []), "frontier item")
    events = state.get("events")
    if not isinstance(events, list) or not events:
        return {
            "active_ids": {item_id for item_id in items},
            "pending_item": None,
            "in_flight_ids": set(),
            "popped_ids": set(),
            "initialized": False,
            "stopped": False,
        }

    active_ids: set[str] = set()
    popped_ids: set[str] = set()
    pending_item: str | None = None
    in_flight_ids: set[str] = set()
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
        elif action == "record":
            initialized = True
        elif action == "seed":
            added_frontier = event.get("add_frontier") if isinstance(event.get("add_frontier"), list) else []
            for item_id in added_frontier:
                if isinstance(item_id, str) and item_id in items and item_id not in popped_ids:
                    active_ids.add(item_id)
        elif action == "pop":
            item_id = event.get("item")
            if isinstance(item_id, str) and item_id in items:
                active_ids.discard(item_id)
                popped_ids.add(item_id)
                pending_item = item_id
        elif action == "assign":
            item_id = event.get("item")
            if isinstance(item_id, str) and item_id in items:
                if item_id == pending_item:
                    pending_item = None
                in_flight_ids.add(item_id)
        elif action == "expand":
            item_id = event.get("item")
            if item_id == pending_item:
                pending_item = None
            if isinstance(item_id, str):
                in_flight_ids.discard(item_id)
            added_frontier = event.get("add_frontier") if isinstance(event.get("add_frontier"), list) else []
            for child_id in added_frontier:
                if isinstance(child_id, str) and child_id in items and child_id not in popped_ids:
                    active_ids.add(child_id)
        elif action == "supersede":
            item_id = event.get("item")
            if isinstance(item_id, str):
                active_ids.discard(item_id)
                if item_id == pending_item:
                    pending_item = None
            replacement = event.get("replacement")
            if isinstance(replacement, str) and replacement in items and replacement not in popped_ids:
                active_ids.add(replacement)
        elif action == "rank":
            item_id = event.get("item")
            if item_id == pending_item:
                pending_item = None
            if isinstance(item_id, str):
                in_flight_ids.discard(item_id)
        elif action == "stop":
            stopped = True
            pending_item = None
            in_flight_ids.clear()
            active_ids.clear()

    if not initialized:
        active_ids = {item_id for item_id in items}

    return {
        "active_ids": active_ids,
        "pending_item": pending_item,
        "in_flight_ids": in_flight_ids,
        "popped_ids": popped_ids,
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
        "search_cost": item.get("search_cost"),
        "base_search_cost": item.get("base_search_cost"),
        "estimated_remaining_cost": item.get("estimated_remaining_cost"),
        "heuristic_cost": item.get("heuristic_cost"),
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
