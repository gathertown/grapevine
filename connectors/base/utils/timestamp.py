"""Timestamp parsing utilities for connectors."""

from datetime import UTC, datetime
from typing import Any


def parse_iso_timestamp(timestamp: str) -> datetime:
    """Parse ISO 8601 timestamp, handling Z suffix.

    Python's fromisoformat() doesn't handle 'Z' suffix until Python 3.11+,
    so we normalize it to '+00:00' for compatibility.
    """
    if timestamp.endswith("Z"):
        timestamp = timestamp[:-1] + "+00:00"
    return datetime.fromisoformat(timestamp)


def convert_timestamp_to_iso(value: Any | None) -> str | None:
    """Convert various timestamp formats to ISO 8601 string.

    Handles:
    - None -> None
    - ISO 8601 strings (with T) -> passed through
    - Date-time strings with space (YYYY-MM-DD HH:MM:SS) -> converted to ISO with T
    - Unix epoch strings -> converted to ISO
    - Unix epoch numbers (int/float) -> converted to ISO
    - Other values -> converted to string
    """
    if value is None:
        return None
    if isinstance(value, str):
        # Already valid ISO 8601 with T separator
        if "T" in value:
            return value
        # Handle "YYYY-MM-DD HH:MM:SS" format (e.g., from Pipedrive)
        # Replace space with T to make it valid ISO 8601
        if "-" in value and " " in value:
            return value.replace(" ", "T")
        # Handle date-only strings
        if "-" in value:
            return value
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
