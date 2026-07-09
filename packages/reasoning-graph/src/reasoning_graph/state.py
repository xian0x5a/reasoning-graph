"""State I/O and simple graph lookup helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Iterable


def load_state(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def strict_json_dumps(value: Any, **kwargs: Any) -> str:
    """Serialize JSON without permitting non-standard NaN or Infinity values."""

    return json.dumps(value, allow_nan=False, **kwargs)


def dump_state(state: dict[str, Any], path: str | None, in_place_source: str | None = None) -> None:
    text = strict_json_dumps(state, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    target = path or (in_place_source if in_place_source != "-" else None)
    write_output_text(text, target)


def write_output_text(text: str, path: str | None) -> None:
    if path and path != "-":
        Path(path).write_text(text, encoding="utf-8")
        return
    sys.stdout.write(text)


def by_id(items: Iterable[dict[str, Any]], label: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for i, item in enumerate(items):
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            continue
        if item_id in result:
            # Keep first; validation reports duplicate.
            continue
        result[item_id] = item
    return result


def node_label(node: dict[str, Any]) -> str:
    parts = [str(node.get("type", "node"))]
    text = str(node.get("text", node.get("id", ""))).strip()
    if text:
        parts.append(text)
    if node.get("type") == "assumption" and "prior" in node:
        parts.append(f"prior {float(node['prior']):.2f}")
    if "posterior" in node:
        parts.append(f"posterior {float(node['posterior']):.2f}")
    return ": ".join(parts[:2]) + (f"\n{parts[2]}" if len(parts) > 2 else "")
