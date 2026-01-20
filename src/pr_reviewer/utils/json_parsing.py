"""Generic JSON parsing utilities for LLM outputs.

This module provides robust JSON parsing with multiple fallback strategies
to handle various LLM output formats.
"""

import json
import logging
import re
from collections.abc import Callable
from typing import Any, TypeVar

from json_repair import repair_json

logger = logging.getLogger(__name__)

T = TypeVar("T", dict[str, Any], list[dict[str, Any]])


def parse_llm_json(
    text: str,
    *,
    expected_type: type[T],
    validator: Callable[[T], T | None] | None = None,
    log_errors: bool = True,
) -> T:
    """Parse JSON from LLM output with multiple fallback strategies.

    Tries the following strategies in order:
    1. Direct JSON parsing
    2. Extract from markdown code blocks (```json...```)
    3. Extract from first { to last } (or [ to ])
    4. Use json-repair library to fix malformed JSON

    Args:
        text: Response text from LLM
        expected_type: Expected return type (dict or list)
        validator: Optional validation function that returns validated data or None
        log_errors: Whether to log errors when parsing fails (default True).
                    Set to False when using this as part of a fallback chain.

    Returns:
        Parsed and validated JSON data

    Raises:
        ValueError: If all parsing strategies fail
    """

    def try_parse(json_text: str) -> T | None:
        """Try parsing JSON and return parsed data or None."""
        try:
            data = json.loads(json_text)
            # Check if the parsed data matches the expected type
            if (
                expected_type is dict
                and isinstance(data, dict)
                or expected_type is list
                and isinstance(data, list)
            ):
                return data  # type: ignore[return-value]
            return None
        except json.JSONDecodeError:
            return None

    def validate_data(data: T) -> T | None:
        """Run validator if provided, otherwise return data as-is."""
        if validator:
            return validator(data)
        return data

    # Strategy 1: Try parsing text directly
    parsed = try_parse(text.strip())
    if parsed is not None:
        validated = validate_data(parsed)
        if validated is not None:
            logger.debug("Successfully parsed JSON directly")
            return validated

    # Strategy 2: Strip markdown code blocks and retry
    markdown_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if markdown_match:
        parsed = try_parse(markdown_match.group(1).strip())
        if parsed is not None:
            validated = validate_data(parsed)
            if validated is not None:
                logger.debug("Successfully parsed JSON from markdown code block")
                return validated

    # Strategy 3: Extract from first brace/bracket to last brace/bracket
    if expected_type is dict:
        open_char, close_char = "{", "}"
    else:  # list
        open_char, close_char = "[", "]"

    first_idx = text.find(open_char)
    last_idx = text.rfind(close_char)
    if first_idx != -1 and last_idx != -1 and last_idx > first_idx:
        parsed = try_parse(text[first_idx : last_idx + 1])
        if parsed is not None:
            validated = validate_data(parsed)
            if validated is not None:
                logger.debug(f"Successfully parsed JSON by extracting {open_char}...{close_char}")
                return validated

    # Strategy 4: Use json-repair to fix malformed JSON
    try:
        # Try repairing the full text first
        repaired = repair_json(text)
        parsed = try_parse(repaired)
        if parsed is not None:
            validated = validate_data(parsed)
            if validated is not None:
                logger.info("Successfully repaired malformed JSON (full text)")
                return validated

        # If full text repair didn't work, try repairing the extracted portion
        if first_idx != -1 and last_idx != -1:
            extracted = text[first_idx : last_idx + 1]
            repaired = repair_json(extracted)
            parsed = try_parse(repaired)
            if parsed is not None:
                validated = validate_data(parsed)
                if validated is not None:
                    logger.info("Successfully repaired malformed JSON (extracted portion)")
                    return validated
    except Exception as e:
        logger.debug(f"json-repair failed: {e}")

    # If all strategies failed
    if log_errors:
        logger.error(f"Could not parse JSON: No valid {expected_type.__name__} found in response")
        logger.error(f"Response text:\n{text}")
    raise ValueError(f"No valid {expected_type.__name__} found in LLM response")
