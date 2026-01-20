"""Date validation and conversion utilities for PostgreSQL compatibility."""

from datetime import date, datetime


def parse_date_string(date_string: str) -> date:
    """
    Parse a date string in YYYY-MM-DD format and return a date object.

    Args:
        date_string: Date string in YYYY-MM-DD format

    Returns:
        date: Python date object

    Raises:
        ValueError: If the date string is invalid or not in YYYY-MM-DD format
    """
    if not date_string:
        raise ValueError("Date string cannot be empty")

    try:
        # Parse the date string and return a date object
        parsed_date = datetime.strptime(date_string, "%Y-%m-%d").date()
        return parsed_date
    except ValueError as e:
        raise ValueError(f"Invalid date format '{date_string}'. Expected YYYY-MM-DD format.") from e


def validate_and_convert_date(date_value: str | date | None) -> date | None:
    """
    Validate and convert a date value to a proper date object for PostgreSQL.

    Args:
        date_value: Date string in YYYY-MM-DD format or date object, or None

    Returns:
        date: Python date object or None if input is None

    Raises:
        ValueError: If the date value is invalid
    """
    if date_value is None:
        return None

    if isinstance(date_value, date):
        return date_value

    if isinstance(date_value, str):
        return parse_date_string(date_value)

    raise ValueError(f"Invalid date type: {type(date_value)}. Expected str or date object.")
