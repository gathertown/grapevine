"""Base models for connector job configurations."""

from typing import Literal

from pydantic import BaseModel


class BackfillIngestConfig(BaseModel, frozen=True):
    """Base class for all backfill ingest job configurations."""

    message_type: Literal["backfill"] = "backfill"
    tenant_id: str
    source: str  # Source identifier (e.g., "linear_api_backfill", "github_pr_backfill")
    # If included, the backfill_id will be used to track the # total and done index jobs for the backfill
    # and we'll send a backfill complete notification to the Slack bot when the backfill is complete.
    # Root backfill jobs ignore this field and generate their own backfill_id.
    backfill_id: str | None = None
    # If True, suppress sending the completion notification to Slack (e.g., for periodic cron jobs)
    suppress_notification: bool = False
    # If True, force update artifacts even if source_updated_at hasn't changed
    # Useful for metadata updates like GDPR profile changes where content timestamps don't reflect changes
    force_update: bool = False
