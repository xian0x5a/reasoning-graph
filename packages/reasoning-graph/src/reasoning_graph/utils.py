"""Small shared coercion helpers."""

from __future__ import annotations

import math
from typing import Any


def as_string_list(value: Any, field: str, errors: list[str]) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        errors.append(f"{field} must be a list")
        return []
    result: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item:
            errors.append(f"{field}[{i}] must be a non-empty string")
            continue
        result.append(item)
    return result


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isfinite(number):
        return number
    return None
