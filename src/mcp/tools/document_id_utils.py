"""Utility functions for document ID processing and candidate generation."""

import json
from typing import Any


def get_candidate_document_ids(document_id: str) -> list[str]:
    """
    and fixed version (slashes → underscores). Otherwise return just original.

    Args:
        document_id: The original document ID

    Returns:
        List of candidate document IDs to try, with original ID first
    """
    candidates = [document_id]

    return candidates


def parse_metadata(metadata: Any) -> dict[str, Any]:
    """Parse metadata from various formats into a dictionary.

    Args:
        metadata: Metadata in various formats (dict, JSON string, None, etc.)

    Returns:
        Dictionary of metadata, empty dict if parsing fails
    """
    if isinstance(metadata, dict):
        return metadata
    elif isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except json.JSONDecodeError:
            return {}
    elif metadata is None:
        return {}
    else:
        # For any other unexpected types
        return {}
