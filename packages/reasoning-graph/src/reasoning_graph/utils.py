"""Small shared coercion helpers."""

from __future__ import annotations

import math
from typing import Any


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
