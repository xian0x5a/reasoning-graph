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


def require_finite_float(value: Any, field: str) -> float:
    """Coerce numeric input while rejecting NaN and infinities."""

    try:
        number = float(value)
    except OverflowError:
        raise ValueError(f"{field} must be representable as a finite number") from None
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be numeric, got {value!r}")
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite, got {number}")
    return number


def require_non_negative_float(value: Any, field: str) -> float:
    number = require_finite_float(value, field)
    if number < 0:
        raise ValueError(f"{field} must be non-negative, got {number}")
    return number
