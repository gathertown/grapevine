"""Pydantic models for Monday.com job configurations."""

from datetime import datetime
from typing import Literal

from connectors.base.models import BackfillIngestConfig


class MondayBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Root config that triggers all Monday.com backfill jobs."""

    source: Literal["monday_backfill_root"] = "monday_backfill_root"


class MondayBoardBackfillConfig(BackfillIngestConfig, frozen=True):
    """Config for Monday.com board backfill batch job."""

    source: Literal["monday_board_backfill"] = "monday_board_backfill"
    board_ids: list[int]  # Required - batch of board IDs to process
    start_timestamp: datetime | None = None  # For rate-limited delayed processing


class MondayItemBackfillConfig(BackfillIngestConfig, frozen=True):
    """Config for Monday.com item backfill batch job.

    Items are fetched per board to maintain context and enable efficient querying.
    """

    source: Literal["monday_item_backfill"] = "monday_item_backfill"
    board_id: int  # Board to fetch items from
    item_ids: list[int]  # Required - batch of item IDs to process
    start_timestamp: datetime | None = None  # For rate-limited delayed processing
