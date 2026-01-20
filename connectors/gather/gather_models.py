"""Pydantic models for Gather job configurations."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig


class GatherApiBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Gather meetings API backfill root job."""

    source: Literal["gather_api_backfill_root"] = "gather_api_backfill_root"
    space_id: str


class GatherApiBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Gather meetings API backfill job."""

    source: Literal["gather_api_backfill"] = "gather_api_backfill"
    space_id: str
    meetings_data: list[dict[str, Any]]  # Full meeting objects
    start_timestamp: datetime | None = None


class GatherWebhookConfig(BaseModel):
    """Configuration for Gather webhook processing."""

    body: dict[str, Any]
    headers: dict[str, str]
    tenant_id: str
