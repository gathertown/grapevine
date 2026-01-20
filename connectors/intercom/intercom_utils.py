"""Shared utilities for Intercom connector."""

from datetime import UTC, datetime
from typing import Any


def normalize_timestamp(value: Any | None) -> tuple[str, datetime]:
    """Normalize Intercom timestamp fields which may be ints, floats, or strings.

    Handles:
    - Unix timestamps (int or float)
    - ISO-format strings
    - Numeric strings representing Unix timestamps

    Args:
        value: The timestamp value to normalize

    Returns:
        tuple of (string representation, datetime object)
    """
    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=UTC)
        return str(int(value)), dt

    if isinstance(value, str):
        try:
            # Attempt to parse ISO-style strings
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value, dt
        except ValueError:
            # Fall back to treating numeric strings as epoch seconds
            try:
                epoch = int(value)
                dt = datetime.fromtimestamp(epoch, tz=UTC)
                return str(epoch), dt
            except ValueError:
                pass

    # Fallback: use current time
    now = datetime.now(tz=UTC)
    return str(int(now.timestamp())), now


def convert_timestamp_to_iso(value: Any | None) -> str | None:
    """Convert a timestamp value to ISO format string.

    Handles:
    - Unix timestamps (int or float)
    - ISO-format strings (returned as-is after validation)
    - Numeric strings representing Unix timestamps

    Args:
        value: The timestamp value to convert

    Returns:
        ISO format string or None if value is None
    """
    if value is None:
        return None

    if isinstance(value, str):
        # Already ISO format (has T or -)
        if "T" in value or "-" in value:
            return value
        # Try to parse as epoch
        try:
            epoch = int(value)
            dt = datetime.fromtimestamp(epoch, tz=UTC)
            return dt.isoformat()
        except (ValueError, TypeError):
            return value

    if isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=UTC)
        return dt.isoformat()

    return str(value)
