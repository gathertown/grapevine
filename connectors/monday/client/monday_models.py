"""Pydantic models for Monday.com API responses.

Based on: https://developer.monday.com/api-reference/docs/introduction-to-graphql
"""

from enum import StrEnum

from pydantic import BaseModel


class BoardKind(StrEnum):
    """Monday.com board visibility types.

    Source: https://developer.monday.com/api-reference/reference/boards#board-kind
    """

    PUBLIC = "public"
    PRIVATE = "private"
    SHARE = "share"


# Allowlist of board kinds that should be indexed
# Only public boards for now - share boards excluded until per-item permissions are implemented
INDEXABLE_BOARD_KINDS = {BoardKind.PUBLIC}


class MondayBoard(BaseModel):
    """Monday.com board metadata."""

    id: int
    name: str
    description: str | None = None
    board_kind: str  # Use str to handle unknown values from API gracefully
    workspace_id: int | None = None
    workspace_name: str | None = None
    item_count: int = 0

    def is_indexable(self) -> bool:
        """Check if this board should be indexed (public or shareable only)."""
        return self.board_kind in INDEXABLE_BOARD_KINDS


class MondayItem(BaseModel):
    """Monday.com item (basic info for listing)."""

    id: int
    name: str
    board_id: int
    state: str  # active, archived, deleted
