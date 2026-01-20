"""Pacific Time utilities for handling Slack message timestamps and date boundaries."""

import logging
from datetime import UTC, date, datetime

import pytz

from connectors.base.doc_ids import get_slack_doc_id

logger = logging.getLogger(__name__)

# Pacific timezone
PACIFIC_TZ = pytz.timezone("US/Pacific")


def timestamp_to_pacific_date(timestamp: str | float) -> date:
    """
    Convert a Unix timestamp to a Pacific Time date.

    Args:
        timestamp: Unix timestamp as string or float

    Returns:
        date: Date in Pacific Time

    Raises:
        ValueError: If timestamp cannot be parsed
    """
    try:
        ts_float = float(timestamp) if isinstance(timestamp, str) else timestamp

        # Convert to UTC datetime first
        utc_dt = datetime.fromtimestamp(ts_float, tz=UTC)

        # Convert to Pacific Time
        pacific_dt = utc_dt.astimezone(PACIFIC_TZ)

        return pacific_dt.date()

    except (ValueError, TypeError, OSError) as e:
        raise ValueError(f"Invalid timestamp '{timestamp}': {e}")


def get_pacific_day_boundaries(date_str: str) -> tuple[datetime, datetime]:
    """
    Get the start and end timestamps for a Pacific Time day.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Tuple of (start_utc, end_utc) as UTC datetime objects

    Raises:
        ValueError: If date string is invalid
    """
    try:
        # Parse the date
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

        # Create Pacific Time boundaries
        pacific_start = PACIFIC_TZ.localize(datetime.combine(target_date, datetime.min.time()))
        pacific_end = PACIFIC_TZ.localize(datetime.combine(target_date, datetime.max.time()))

        # Convert to UTC
        utc_start = pacific_start.astimezone(UTC)
        utc_end = pacific_end.astimezone(UTC)

        return utc_start, utc_end

    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_str}'. Expected YYYY-MM-DD: {e}")


def get_pacific_day_boundaries_timestamps(date_str: str) -> tuple[float, float]:
    """
    Get the start and end Unix timestamps for a Pacific Time day.

    Args:
        date_str: Date string in YYYY-MM-DD format

    Returns:
        Tuple of (start_timestamp, end_timestamp) as floats

    Raises:
        ValueError: If date string is invalid
    """
    start_dt, end_dt = get_pacific_day_boundaries(date_str)
    return start_dt.timestamp(), end_dt.timestamp()


def is_timestamp_in_pacific_day(timestamp: str | float, date_str: str) -> bool:
    """
    Check if a timestamp falls within a specific Pacific Time day.

    Args:
        timestamp: Unix timestamp as string or float
        date_str: Date string in YYYY-MM-DD format

    Returns:
        bool: True if timestamp falls within the Pacific day
    """
    try:
        ts_float = float(timestamp) if isinstance(timestamp, str) else timestamp

        start_ts, end_ts = get_pacific_day_boundaries_timestamps(date_str)
        return start_ts <= ts_float <= end_ts

    except (ValueError, TypeError):
        return False


def format_pacific_time(timestamp: str | float) -> str:
    """
    Format a Unix timestamp as a Pacific Time string.

    Args:
        timestamp: Unix timestamp as string or float

    Returns:
        str: Formatted time string like "2025-01-15 14:30:00 PST"

    Raises:
        ValueError: If timestamp cannot be parsed
    """
    try:
        ts_float = float(timestamp) if isinstance(timestamp, str) else timestamp

        # Convert to UTC first
        utc_dt = datetime.fromtimestamp(ts_float, tz=UTC)

        # Convert to Pacific Time
        pacific_dt = utc_dt.astimezone(PACIFIC_TZ)

        # Format with timezone abbreviation
        return pacific_dt.strftime("%Y-%m-%d %H:%M:%S %Z")

    except (ValueError, TypeError, OSError) as e:
        raise ValueError(f"Invalid timestamp '{timestamp}': {e}")


def get_message_pacific_document_id(channel_id: str, timestamp: str | float) -> str:
    """
    Generate a document ID based on a message's Pacific Time date.

    Args:
        channel_id: Slack channel ID
        timestamp: Unix timestamp as string or float

    Returns:
        str: Document ID in format channel_id_YYYY-MM-DD

    Raises:
        ValueError: If timestamp cannot be parsed
    """
    pacific_date = timestamp_to_pacific_date(timestamp)
    return get_slack_doc_id(channel_id, pacific_date.strftime("%Y-%m-%d"))
