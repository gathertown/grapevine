"""Type conversion utilities for safe casting operations."""

from typing import Any


def safe_int(value: Any) -> int | None:
    """
    Safely convert value to int.

    Returns:
        int: Converted integer or None if conversion fails
    """
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def safe_float(value: Any) -> float | None:
    """
    Safely convert value to float.

    Returns:
        float: Converted float or None if conversion fails
    """
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
