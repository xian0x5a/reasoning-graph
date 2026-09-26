"""Event-log helpers shared by commands that append to a state's trace."""

from __future__ import annotations

from typing import Any


def next_event_step(state: dict[str, Any]) -> int:
    events = state.get("events")
    if not isinstance(events, list):
        return 1
    steps = [event.get("step") for event in events if isinstance(event, dict) and isinstance(event.get("step"), int)]
    return max(steps, default=0) + 1


def is_stopped(state: dict[str, Any]) -> bool:
    events = state.get("events")
    return isinstance(events, list) and any(isinstance(event, dict) and event.get("action") == "stop" for event in events)
