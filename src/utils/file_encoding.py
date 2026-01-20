"""Utilities for handling file encoding issues."""

import json
from pathlib import Path
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)


def read_json_file_safe(file_path: Path | str, file_description: str = "") -> dict | list[Any]:
    """
    Read JSON file with automatic encoding detection and detailed logging.

    Args:
        file_path: Path to the JSON file
        file_description: Human-readable description for logging

    Returns:
        Parsed JSON content as dict or list

    Raises:
        json.JSONDecodeError: If the file is not valid JSON
        FileNotFoundError: If the file doesn't exist
    """
    from charset_normalizer import from_path

    file_path = Path(file_path)
    desc = file_description or str(file_path.name)

    try:
        # Fast path: try UTF-8 first (most common)
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except UnicodeDecodeError as e:
        # Log the exact error details
        logger.warning(
            f"UTF-8 decode failed for {desc} at byte 0x{e.object[e.start]:02x} "
            f"position {e.start}. Attempting automatic encoding detection..."
        )

        # Use charset-normalizer for detection
        detection_results = from_path(file_path)

        if not detection_results:
            logger.error(f"Could not detect encoding for {desc}")
            # Fall back to UTF-8 with replacement
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
                replacement_count = content.count("�")
                if replacement_count > 0:
                    logger.warning(
                        f"Using UTF-8 with replacement for {desc}. "
                        f"Replaced {replacement_count} invalid bytes."
                    )
                return json.loads(content)

        # Get the best match from charset-normalizer
        best_match = detection_results.best()
        if not best_match:
            logger.error(f"No encoding match found for {desc}")
            # Fall back to UTF-8 with replacement
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
                replacement_count = content.count("�")
                if replacement_count > 0:
                    logger.warning(
                        f"Using UTF-8 with replacement for {desc}. "
                        f"Replaced {replacement_count} invalid bytes."
                    )
                return json.loads(content)

        # Log detection results
        logger.info(
            f"Detected encoding for {desc}: {best_match.encoding} "
            f"(confidence: {best_match.coherence:.2%}, "
            f"language: {best_match.language or 'unknown'})"
        )

        # Read with detected encoding
        try:
            with open(file_path, encoding=best_match.encoding) as f:
                return json.load(f)
        except (UnicodeDecodeError, LookupError) as err:
            logger.error(
                f"Failed to read {desc} with detected encoding {best_match.encoding}: {err}. "
                f"Falling back to UTF-8 with replacement."
            )
            with open(file_path, encoding="utf-8", errors="replace") as f:
                content = f.read()
                replacement_count = content.count("�")
                if replacement_count > 0:
                    logger.warning(f"Replaced {replacement_count} invalid bytes in fallback.")
                return json.loads(content)


def decode_file_content(binary_content: bytes, file_path: str | None = None) -> str:
    """Decode binary file content with automatic encoding detection.

    This function attempts to decode binary content using multiple common encodings,
    falling back to lossy UTF-8 decoding if all attempts fail. This ensures we can
    always return some content for indexing, even when the encoding is non-standard
    or corrupted.

    The function tries encodings in order of likelihood:
    1. UTF-8 (most common for modern files)
    2. Latin-1 (common for Western European languages)
    3. CP1252 (Windows default for Western languages)
    4. ISO-8859-1 (older standard, similar to Latin-1)

    Args:
        binary_content: Raw bytes to decode
        file_path: Optional file path for logging purposes

    Returns:
        Decoded string content. If all encodings fail, returns content with
        Unicode replacement characters (�) for undecodable bytes.
    """
    # Try common encodings in order of likelihood
    encodings_to_try = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]

    for encoding in encodings_to_try:
        try:
            return binary_content.decode(encoding)
        except UnicodeDecodeError:
            continue

    # If all encodings fail, use lossy UTF-8 decoding
    # This replaces invalid bytes with the Unicode replacement character (�)
    if file_path:
        logger.warning(f"File {file_path} had encoding issues, using lossy UTF-8 decoding")
    else:
        logger.warning("Binary content had encoding issues, using lossy UTF-8 decoding")

    return binary_content.decode("utf-8", errors="replace")
