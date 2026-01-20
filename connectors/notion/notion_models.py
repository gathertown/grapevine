"""Pydantic models for Notion job configurations and document data structures."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from connectors.base.models import BackfillIngestConfig


class NotionApiBackfillRootConfig(BackfillIngestConfig, frozen=True):
    source: Literal["notion_api_backfill_root"] = "notion_api_backfill_root"
    page_limit: int | None = None


class NotionApiBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["notion_api_backfill"] = "notion_api_backfill"
    page_ids: list[str]
    start_timestamp: datetime | None = None


class NotionUserRefreshConfig(BackfillIngestConfig, frozen=True):
    source: Literal["notion_user_refresh"] = "notion_user_refresh"


class NotionBlockData(BaseModel):
    """Model for a single Notion block."""

    block_id: str
    block_type: str
    content: str = ""
    timestamp: str | None = None
    formatted_time: str | None = None
    page_id: str
    page_title: str
    database_id: str | None = None
    workspace_id: str | None = None
    last_edited_by: str | None = None
    last_edited_by_name: str | None = None
    language: str | None = None  # For code blocks
    checked: bool | None = None  # For to-do blocks
    list_number: int | None = None  # For numbered lists
    nesting_level: int = 0  # For nested lists

    model_config = ConfigDict(extra="allow")  # Allow additional fields


class NotionCommentData(BaseModel):
    """Model for a single Notion comment."""

    comment_id: str
    content: str = ""
    created_time: str | None = None
    last_edited_time: str | None = None
    created_by: str | None = None
    created_by_name: str | None = None
    parent_id: str | None = None
    parent_type: str | None = None

    model_config = ConfigDict(extra="allow")  # Allow additional fields


class NotionPageProperties(BaseModel):
    """Model for Notion page properties."""

    model_config = ConfigDict(extra="allow")  # Allow any property fields


class NotionPageDocumentData(BaseModel):
    """Model for NotionPageDocument raw_data structure."""

    page_id: str
    page_title: str
    page_url: str = ""
    database_id: str | None = None
    workspace_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)
    blocks: list[NotionBlockData] = Field(default_factory=list)
    comments: list[NotionCommentData] = Field(default_factory=list)
    page_created_time: str | None = None
    created_time: str | None = None
    last_edited_time: str | None = None


class NotionPageMetadataOutput(BaseModel):
    """Model for NotionPageDocument metadata output."""

    page_id: str
    page_title: str
    page_url: str
    database_id: str | None = None
    workspace_id: str | None = None
    properties: dict[str, Any]
    source: str
    type: str = "notion_page_document"
    block_count: int
    source_created_at: str | None = None
