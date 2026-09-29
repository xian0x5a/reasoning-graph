"""State I/O and simple graph lookup helpers."""

from __future__ import annotations

import json
import os
import sys
import tempfile
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
        _replace_file_atomically(Path(path), text)
        return
    sys.stdout.write(text)


def _replace_file_atomically(target: Path, text: str) -> None:
    """Write through a same-directory temporary file so an interrupted write never
    leaves a truncated state file behind; the previous file stays intact until rename."""

    directory = target.parent if str(target.parent) else Path(".")
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory, prefix=f".{target.name}.", suffix=".tmp", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            os.chmod(temporary, os.stat(target).st_mode & 0o7777)
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def edge_id(edge: dict[str, Any]) -> str:
    """An edge is identified by its ends: one edge per ordered pair, and no hyphen in a node id."""
    return f"{edge.get('from')}-{edge.get('to')}"


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
