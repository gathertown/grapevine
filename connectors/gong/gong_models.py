"""Pydantic models for Gong job configurations."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from connectors.base.models import BackfillIngestConfig


class GongWorkspacePermissions(BaseModel):
    """Pre-fetched workspace-level permission data to avoid redundant API calls in child jobs."""

    workspace_id: str
    users: list[dict[str, Any]]
    permission_profiles: list[dict[str, Any]]
    permission_profile_users: dict[str, list[dict[str, Any]]]  # profile_id -> users
    library_folders: list[dict[str, Any]]
    call_to_folder_ids: dict[str, list[str]]  # call_id -> folder_ids


class GongCallBatch(BaseModel):
    """Metadata for a batch of Gong calls to process."""

    call_ids: list[str]
    workspace_id: str | None = None


class GongCallBackfillRootConfig(BackfillIngestConfig, frozen=True):
    source: Literal["gong_call_backfill_root"] = "gong_call_backfill_root"
    workspace_ids: list[str] | None = None
    from_datetime: str | datetime | None = None
    to_datetime: str | datetime | None = None
    call_limit: int | None = None
    batch_size: int | None = None


class GongCallBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["gong_call_backfill"] = "gong_call_backfill"
    call_batches: list[GongCallBatch]
    from_datetime: str | datetime | None = None
    to_datetime: str | datetime | None = None
    workspace_permissions: GongWorkspacePermissions | None = None


class GongWebhookConfig(BaseModel):
    """Configuration for Gong webhook processing."""

    body: dict[str, Any]
    tenant_id: str
