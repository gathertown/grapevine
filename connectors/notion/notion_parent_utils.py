"""Utility functions for handling Notion parent structures."""

import logging
from typing import Any, NamedTuple

from connectors.notion.notion_constants import (
    NORMALIZED_PARENT_TYPE_BLOCK,
    NORMALIZED_PARENT_TYPE_PAGE,
    NOTION_PARENT_TYPE_BLOCK,
    NOTION_PARENT_TYPE_BLOCK_ID,
    NOTION_PARENT_TYPE_PAGE,
    NOTION_PARENT_TYPE_PAGE_ID,
)

logger = logging.getLogger(__name__)


class NotionParentInfo(NamedTuple):
    """Structured information about a Notion comment's parent."""

    parent_id: str
    """The ID of the parent (page_id or block_id)"""

    parent_type: str
    """The normalized parent type ('page' or 'block')"""

    is_page: bool
    """True if parent is a page, False if parent is a block"""

    is_block: bool
    """True if parent is a block, False if parent is a page"""


def extract_parent_info(
    parent_data: dict[str, Any], comment_id: str | None = None
) -> NotionParentInfo:
    """Extract and normalize parent information from Notion API parent structure.

    Args:
        parent_data: The parent object from Notion API (e.g., comment_data.get("parent"))
        comment_id: Optional comment ID for logging purposes

    Returns:
        NotionParentInfo with extracted parent_id and normalized parent_type

    Example:
        >>> parent = {"type": "page_id", "page_id": "abc123"}
        >>> info = extract_parent_info(parent)
        >>> info.parent_id
        'abc123'
        >>> info.parent_type
        'page'
        >>> info.is_page
        True
    """
    parent_type_raw = parent_data.get("type", "")

    # Check if parent is a page
    if parent_type_raw in [NOTION_PARENT_TYPE_PAGE_ID, NOTION_PARENT_TYPE_PAGE]:
        parent_id = parent_data.get("page_id", "")
        return NotionParentInfo(
            parent_id=parent_id,
            parent_type=NORMALIZED_PARENT_TYPE_PAGE,
            is_page=True,
            is_block=False,
        )

    # Check if parent is a block
    elif parent_type_raw in [NOTION_PARENT_TYPE_BLOCK_ID, NOTION_PARENT_TYPE_BLOCK]:
        parent_id = parent_data.get("block_id", "")
        return NotionParentInfo(
            parent_id=parent_id,
            parent_type=NORMALIZED_PARENT_TYPE_BLOCK,
            is_page=False,
            is_block=True,
        )

    # Unknown parent type
    else:
        if comment_id:
            logger.warning(f"Unknown parent type '{parent_type_raw}' for comment {comment_id}")
        else:
            logger.warning(f"Unknown parent type '{parent_type_raw}' in parent data")

        return NotionParentInfo(
            parent_id="",
            parent_type="",
            is_page=False,
            is_block=False,
        )
