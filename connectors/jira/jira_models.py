"""Pydantic models for Jira job configurations."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig


class JiraApiBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Jira API backfill root job."""

    source: Literal["jira_api_backfill_root"] = "jira_api_backfill_root"
    project_keys: list[str] = []


class JiraProjectBatch(BaseModel):
    """Metadata for a batch of Jira projects to process."""

    project_key: str
    project_id: str
    project_name: str


class JiraApiBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Jira API backfill job."""

    source: Literal["jira_api_backfill"] = "jira_api_backfill"
    project_batches: list[JiraProjectBatch]
    start_timestamp: datetime | None = None


class JiraWebhookConfig(BaseModel):
    """Configuration for Jira webhook processing."""

    body: dict[str, Any]
    tenant_id: str
