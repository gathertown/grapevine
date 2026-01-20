"""Models for Google Email processing in the ingest pipeline."""

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class GoogleEmailMessageContent(BaseModel):
    """Content model for Google Email message artifacts."""

    message_id: str
    thread_id: str
    subject: str
    body: str
    source_created_at: str | None = None
    date: str
    user_id: str
    user_email: str
    from_address: str
    to_addresses: list[str]
    cc_addresses: list[str]
    bcc_addresses: list[str]


class GoogleEmailMessageMetadata(BaseModel):
    """Metadata model for Google Email message artifacts."""

    size_estimate: int
    internal_date: str
    labels: list[str]


class GoogleEmailMessageArtifact(BaseIngestArtifact):
    """Artifact model for Google Drive file data."""

    entity: ArtifactEntity = ArtifactEntity.GOOGLE_EMAIL_MESSAGE
    content: GoogleEmailMessageContent
    metadata: GoogleEmailMessageMetadata
