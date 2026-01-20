from datetime import datetime

from pydantic import BaseModel, ConfigDict

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact
from connectors.intercom.intercom_api_types import (
    IntercomArticleData,
    IntercomCompanyData,
    IntercomContactData,
    IntercomConversationData,
)


class IntercomConversationArtifactContent(BaseModel):
    """Full conversation data from Intercom API."""

    conversation_data: IntercomConversationData

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class IntercomConversationArtifactMetadata(BaseModel):
    """Metadata for Intercom conversation artifact."""

    conversation_id: str
    state: str
    created_at: str  # ISO timestamp string from Intercom API
    updated_at: str | None = None
    workspace_id: str | None = None


class IntercomConversationArtifact(BaseIngestArtifact):
    """Typed Intercom conversation artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.INTERCOM_CONVERSATION
    content: IntercomConversationArtifactContent
    metadata: IntercomConversationArtifactMetadata


class IntercomHelpCenterArticleArtifactContent(BaseModel):
    """Full Help Center article data from Intercom API."""

    article_data: IntercomArticleData

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class IntercomHelpCenterArticleArtifactMetadata(BaseModel):
    """Metadata for Intercom Help Center article artifact."""

    article_id: str
    title: str
    state: str
    created_at: str  # ISO timestamp string from Intercom API
    updated_at: str | None = None
    workspace_id: str | None = None


class IntercomHelpCenterArticleArtifact(BaseIngestArtifact):
    """Typed Intercom Help Center article artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.INTERCOM_HELP_CENTER_ARTICLE
    content: IntercomHelpCenterArticleArtifactContent
    metadata: IntercomHelpCenterArticleArtifactMetadata


class IntercomContactArtifactContent(BaseModel):
    """Full contact data from Intercom API."""

    contact_data: IntercomContactData

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class IntercomContactArtifactMetadata(BaseModel):
    """Metadata for Intercom contact artifact."""

    contact_id: str
    email: str | None = None
    name: str | None = None
    role: str | None = None
    created_at: str  # ISO timestamp string from Intercom API
    updated_at: str | None = None
    workspace_id: str | None = None


class IntercomContactArtifact(BaseIngestArtifact):
    """Typed Intercom contact artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.INTERCOM_CONTACT
    content: IntercomContactArtifactContent
    metadata: IntercomContactArtifactMetadata


class IntercomCompanyArtifactContent(BaseModel):
    """Full company data from Intercom API."""

    company_data: IntercomCompanyData

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class IntercomCompanyArtifactMetadata(BaseModel):
    """Metadata for Intercom company artifact."""

    company_id: str
    name: str | None = None
    created_at: str  # ISO timestamp string from Intercom API
    updated_at: str | None = None
    workspace_id: str | None = None


class IntercomCompanyArtifact(BaseIngestArtifact):
    """Typed Intercom company artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.INTERCOM_COMPANY
    content: IntercomCompanyArtifactContent
    metadata: IntercomCompanyArtifactMetadata
