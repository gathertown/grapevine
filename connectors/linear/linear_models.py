"""Pydantic models for Linear job configurations."""

from datetime import datetime
from typing import Literal

from connectors.base.models import BackfillIngestConfig


class LinearApiBackfillRootConfig(BackfillIngestConfig, frozen=True):
    source: Literal["linear_api_backfill_root"] = "linear_api_backfill_root"


class LinearApiBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["linear_api_backfill"] = "linear_api_backfill"
    issue_ids: list[str]
    start_timestamp: datetime | None = None
