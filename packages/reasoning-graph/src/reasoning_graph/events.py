"""Event-log helpers shared by commands that append to a state's trace."""

from __future__ import annotations

from typing import Any, Callable


def next_event_step(state: dict[str, Any]) -> int:
    events = state.get("events")
    if not isinstance(events, list):
        return 1
    steps = [event.get("step") for event in events if isinstance(event, dict) and isinstance(event.get("step"), int)]
    return max(steps, default=0) + 1


def is_stopped(state: dict[str, Any]) -> bool:
    events = state.get("events")
    return isinstance(events, list) and any(isinstance(event, dict) and event.get("action") == "stop" for event in events)


# Event fields through which record events add and remove each kind of graph object.
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
    """Replay record events in order, each one's removals before its additions.

    Returns (kind, id) -> index of the event that added each object the trace still holds.
    `on_repeated_add(kind, id, index, previous_index)` reports a node or edge added while the
    trace already holds it; the first claim stands.
    """

    live: dict[tuple[str, str], int] = {}
    if not isinstance(events, list):
        return live
    for index, event in enumerate(events):
        if not isinstance(event, dict) or event.get("action") != "record":
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
