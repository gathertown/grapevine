"""Pydantic models for Trello job configurations."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig


class TrelloApiBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Trello API backfill root job."""

    source: Literal["trello_api_backfill_root"] = "trello_api_backfill_root"


class TrelloBoardBatch(BaseModel):
    """Metadata for a batch of Trello boards to process."""

    board_id: str
    board_name: str


class TrelloApiBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Trello API backfill child job."""

    source: Literal["trello_api_backfill"] = "trello_api_backfill"
    board_batches: list[TrelloBoardBatch]
    start_timestamp: datetime | None = None


class TrelloWebhookConfig(BaseModel):
    """Configuration for Trello webhook processing."""

    body: dict[str, Any]
    tenant_id: str


class TrelloIncrementalSyncConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Trello incremental sync job.

    This job fetches actions from all boards since the last sync timestamp
    and re-indexes cards that have been modified. This provides an alternative
    to webhooks for keeping data up-to-date through periodic polling.
    """

    source: Literal["trello_incremental_sync"] = "trello_incremental_sync"
