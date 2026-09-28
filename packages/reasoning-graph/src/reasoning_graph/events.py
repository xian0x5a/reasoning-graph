"""Event-log helpers shared by commands that append to a state's trace."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

# Events that change the graph; a review or stop judges the graph the latest of them left.
GRAPH_CHANGE_ACTIONS = ("record", "refresh")
# Top-level state fields the stop gates read besides nodes, edges, and factors.
DIGEST_POLICY_FIELDS = ("stop_policy", "goal_policy", "goal_groups")


def next_event_step(state: dict[str, Any]) -> int:
    events = state.get("events")
    if not isinstance(events, list):
        return 1
    steps = [event.get("step") for event in events if isinstance(event, dict) and isinstance(event.get("step"), int)]
    return max(steps, default=0) + 1


def graph_digest(state: dict[str, Any]) -> str:
    """Fingerprint everything the gates judge: nodes minus the computed belief, edges, factors, and policies.

    Events store it so `record` and `stop` can tell when the state was edited outside the CLI.
    Lists are sorted by id, so reordering alone is not a change.
    """

    def rows(field: str, computed: frozenset[str] = frozenset()) -> list[Any]:
        items = state.get(field)
        items = items if isinstance(items, list) else []
        stripped = [{key: value for key, value in item.items() if key not in computed} if isinstance(item, dict) else item for item in items]
        return sorted(stripped, key=lambda item: str(item.get("id")) if isinstance(item, dict) else "")

    content = {
        "nodes": rows("nodes", frozenset({"belief"})),
        "edges": rows("edges"),
        "factors": rows("factors"),
        **{field: state.get(field) for field in DIGEST_POLICY_FIELDS},
    }
    text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def last_graph_change(state: dict[str, Any]) -> dict[str, Any] | None:
    events = state.get("events")
    if not isinstance(events, list):
        return None
    changes = [event for event in events if isinstance(event, dict) and event.get("action") in GRAPH_CHANGE_ACTIONS]
    return changes[-1] if changes else None


def is_stopped(state: dict[str, Any]) -> bool:
    events = state.get("events")
    return isinstance(events, list) and any(isinstance(event, dict) and event.get("action") == "stop" for event in events)


# Event fields through which graph-change events add and remove each kind of graph object.
# Factors are upserted by id, so re-adding a live factor is a replacement, not a repeat.
RECORD_CLAIM_FIELDS = {
    "node": ("add_nodes", "remove_nodes"),
    "edge": ("add_edges", "remove_edges"),
    "factor": ("update_factors", "remove_factors"),
}


def _event_ids(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str) and item] if isinstance(value, list) else []


def live_record_claims(
    events: Any,
    on_repeated_add: Callable[[str, str, int, int], None] | None = None,
) -> dict[tuple[str, str], int]:
    """Replay graph-change events in order, each one's removals before its additions.

    Returns (kind, id) -> index of the event that added each object the trace still holds.
    `on_repeated_add(kind, id, index, previous_index)` reports a node or edge added while the
    trace already holds it; the first claim stands.
    """

    live: dict[tuple[str, str], int] = {}
    if not isinstance(events, list):
        return live
    for index, event in enumerate(events):
        if not isinstance(event, dict) or event.get("action") not in GRAPH_CHANGE_ACTIONS:
            continue
        for kind, (_, remove_field) in RECORD_CLAIM_FIELDS.items():
            for object_id in _event_ids(event.get(remove_field)):
                live.pop((kind, object_id), None)
        for kind, (add_field, _) in RECORD_CLAIM_FIELDS.items():
            for object_id in _event_ids(event.get(add_field)):
                previous = live.get((kind, object_id))
                if previous is not None and kind != "factor":
                    if on_repeated_add:
                        on_repeated_add(kind, object_id, index, previous)
                    continue
                live[(kind, object_id)] = index
    return live
