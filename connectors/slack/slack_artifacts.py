"""Pydantic models for Slack data serialization."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class SlackChannelMetadata(BaseModel):
    """Metadata for a Slack channel artifact."""

    channel_id: str | None = None


class SlackMessageMetadata(BaseModel):
    """Metadata for a Slack message artifact."""

    channel_id: str


class SlackTeamContent(BaseModel):
    """Content structure for a Slack team artifact."""

    id: str
    name: str
    domain: str | None = None
    email_domain: str | None = None
    icon: dict[str, Any] | None = None

    model_config = ConfigDict(extra="allow")  # Allow additional fields from Slack API


class SlackChannelContent(BaseModel):
    """Content structure for a Slack channel artifact."""

    id: str
    name: str
    is_channel: bool | None = None
    is_group: bool | None = None
    is_im: bool | None = None
    is_mpim: bool | None = None
    created: int | None = None
    is_archived: bool | None = None
    is_general: bool | None = None
    is_shared: bool | None = None
    is_org_shared: bool | None = None

    model_config = ConfigDict(extra="allow")  # Allow additional fields from Slack export


class SlackUserContent(BaseModel):
    """Content structure for a Slack user artifact."""

    id: str
    team_id: str | None = None
    name: str | None = None
    real_name: str | None = None
    tz: str | None = None
    tz_label: str | None = None
    tz_offset: int | None = None
    profile: dict[str, Any] | None = None
    is_admin: bool | None = None
    is_owner: bool | None = None
    is_primary_owner: bool | None = None
    is_restricted: bool | None = None
    is_ultra_restricted: bool | None = None
    is_bot: bool | None = None

    model_config = ConfigDict(extra="allow")  # Allow additional fields from Slack export


class SlackMessageContent(BaseModel):
    """Content structure for a Slack message artifact."""

    type: str
    user: str | None = None
    text: str | None = None
    ts: str
    client_msg_id: str | None = None
    team: str | None = None
    blocks: list[dict[str, Any]] | None = None
    attachments: list[dict[str, Any]] | None = None

    model_config = ConfigDict(extra="allow")  # Allow additional fields from Slack export


class SlackTeamArtifact(BaseIngestArtifact):
    """Typed Slack team artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.SLACK_TEAM
    content: SlackTeamContent
    metadata: dict[str, Any] | BaseModel


class SlackChannelArtifact(BaseIngestArtifact):
    """Typed Slack channel artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.SLACK_CHANNEL
    content: SlackChannelContent
    metadata: SlackChannelMetadata | BaseModel


class SlackUserArtifact(BaseIngestArtifact):
    """Typed Slack user artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.SLACK_USER
    content: SlackUserContent
    metadata: dict[str, Any] | BaseModel


class SlackMessageArtifact(BaseIngestArtifact):
    """Typed Slack message artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.SLACK_MESSAGE
    content: SlackMessageContent
    metadata: SlackMessageMetadata | BaseModel
