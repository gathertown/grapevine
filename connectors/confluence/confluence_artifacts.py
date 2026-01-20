from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class ConfluencePageArtifactMetadata(BaseModel):
    page_id: str
    page_title: str
    page_url: str
    space_id: str
    participants: dict[str, str]  # user_id -> display_name mapping
    parent_page_id: str | None = None
    source_created_at: str
    source_updated_at: str


class ConfluencePageArtifactContent(BaseModel):
    page_data: dict[str, Any]  # Full Confluence page JSON

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class ConfluenceSpaceArtifactMetadata(BaseModel):
    space_id: str  # Internal Confluence space ID
    space_key: str  # e.g., "TEAM"
    space_name: str
    space_type: str | None = None  # "personal" or "global"
    description: str | None = None
    homepage_id: str | None = None  # Page ID of the space homepage
    site_domain: str | None = None


class ConfluenceSpaceArtifactContent(BaseModel):
    """Content for Confluence space artifacts."""

    space_data: dict[str, Any]  # Full Confluence space JSON

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class ConfluencePageArtifact(BaseIngestArtifact):
    """Typed Confluence page artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.CONFLUENCE_PAGE
    content: ConfluencePageArtifactContent
    metadata: ConfluencePageArtifactMetadata


class ConfluenceSpaceArtifact(BaseIngestArtifact):
    """Typed Confluence space artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.CONFLUENCE_SPACE
    content: ConfluenceSpaceArtifactContent
    metadata: ConfluenceSpaceArtifactMetadata
