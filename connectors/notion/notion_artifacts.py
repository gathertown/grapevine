from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class NotionPageArtifactMetadata(BaseModel):
    page_id: str
    page_title: str
    database_id: str | None = None
    workspace_id: str | None = None


class NotionPageArtifactContent(BaseModel):
    source: Literal["notion_api"] = "notion_api"
    page_data: dict[str, Any]
    blocks: list[dict[str, Any]]
    comments: list[dict[str, Any]] = []

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class NotionPageArtifact(BaseIngestArtifact):
    """Typed Notion page artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.NOTION_PAGE
    content: NotionPageArtifactContent
    metadata: NotionPageArtifactMetadata


class NotionUserArtifactContent(BaseModel):
    id: str
    type: str = "unknown"
    name: str | None = ""
    avatar_url: str | None = ""
    object: str = "user"
    email: str | None = None
    owner_type: str | None = None
    owner_id: str | None = None

    model_config = ConfigDict(extra="allow")  # Allow additional fields from Notion API


class NotionUserArtifactMetadata(BaseModel):
    user_id: str
    user_name: str | None = None


class NotionUserArtifact(BaseIngestArtifact):
    """Typed Notion user artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.NOTION_USER
    content: NotionUserArtifactContent
    metadata: NotionUserArtifactMetadata
