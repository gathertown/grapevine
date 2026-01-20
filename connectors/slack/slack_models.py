"""Pydantic models for Slack job configurations."""

from typing import Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig


class SlackChannelDayFile(BaseModel):
    """Metadata for a channel-day file with byte range information."""

    channel_name: str
    channel_id: str
    filename: str  # e.g. "2023-01-15.json"
    start_byte: int
    size: int  # compressed size


class SlackExportBackfillRootConfig(BackfillIngestConfig, frozen=True):
    source: Literal["slack_export_backfill_root"] = "slack_export_backfill_root"
    uri: str
    message_limit: int | None = None


class SlackExportBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["slack_export_backfill"] = "slack_export_backfill"
    uri: str  # Original S3 ZIP URI for HTTP Range requests
    channel_day_files: list[SlackChannelDayFile]
    message_limit: int | None = None
