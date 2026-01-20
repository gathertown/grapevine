"""Pydantic models for Confluence job configurations."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig


class ConfluenceApiBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Confluence API backfill root job."""

    source: Literal["confluence_api_backfill_root"] = "confluence_api_backfill_root"
    space_keys: list[str] = []


class ConfluenceSpaceBatch(BaseModel):
    """Metadata for a batch of Confluence spaces to process."""

    space_key: str
    space_id: str
    space_name: str


class ConfluenceApiBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Confluence API backfill job."""

    source: Literal["confluence_api_backfill"] = "confluence_api_backfill"
    space_batches: list[ConfluenceSpaceBatch]
    start_timestamp: datetime | None = None


class ConfluenceWebhookConfig(BaseModel):
    """Configuration for Confluence webhook processing."""

    body: dict[str, Any]
    tenant_id: str
