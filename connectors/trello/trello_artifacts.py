"""Trello artifact models for ingest pipeline."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


# Workspace/Organization artifacts
class TrelloWorkspaceArtifactContent(BaseModel):
    workspace_data: dict[str, Any]

    model_config = ConfigDict(extra="allow")


class TrelloWorkspaceArtifactMetadata(BaseModel):
    workspace_id: str
    workspace_name: str
    display_name: str | None = None
    desc: str | None = None
    desc_data: dict[str, Any] | None = None
    website: str | None = None
    url: str | None = None
    logo_url: str | None = None
    premium_features: list[str] = []


class TrelloWorkspaceArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.TRELLO_WORKSPACE
    content: TrelloWorkspaceArtifactContent
    metadata: TrelloWorkspaceArtifactMetadata


# Board artifacts
class TrelloBoardArtifactContent(BaseModel):
    board_data: dict[str, Any]

    model_config = ConfigDict(extra="allow")


class TrelloBoardArtifactMetadata(BaseModel):
    board_id: str
    board_name: str
    board_desc: str | None = None
    closed: bool = False
    id_organization: str | None = None
    organization_name: str | None = None
    short_url: str | None = None
    url: str | None = None
    starred: bool = False
    id_member_creator: str | None = None
    date_last_activity: str | None = None
    permission_level: str | None = None  # "private", "org", "public"
    member_emails: list[str] = []  # Emails of board members (for private boards)


class TrelloBoardArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.TRELLO_BOARD
    content: TrelloBoardArtifactContent
    metadata: TrelloBoardArtifactMetadata


# Card artifacts
class TrelloCardArtifactContent(BaseModel):
    card_data: dict[str, Any]
    comments: list[dict[str, Any]] = []  # Actions of type commentCard
    checklists: list[dict[str, Any]] = []  # Card checklists with items

    model_config = ConfigDict(extra="allow")


class TrelloCardArtifactMetadata(BaseModel):
    card_id: str
    card_name: str
    desc: str | None = None
    id_list: str  # Reference to parent list
    list_name: str | None = None  # Resolved from list
    id_board: str  # Reference to board
    board_name: str | None = None  # Resolved from board
    id_members: list[str] = []  # Assigned member IDs
    labels: list[dict[str, Any]] = []
    closed: bool = False
    due: str | None = None  # ISO format datetime
    due_complete: bool = False
    start: str | None = None  # ISO format datetime
    pos: float | None = None
    short_url: str | None = None
    url: str | None = None
    date_last_activity: str | None = None
    id_short: int | None = None  # Card number on board
    subscribed: bool = False
    board_permission_level: str | None = None  # "private", "org", "public"
    board_member_emails: list[str] = []  # Board member emails for permission resolution


class TrelloCardArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.TRELLO_CARD
    content: TrelloCardArtifactContent
    metadata: TrelloCardArtifactMetadata


# Webhook configuration models
class TrelloWebhooksConfig(BaseModel):
    """Configuration for Trello member webhook stored in tenant database.

    This is stored in the tenant database config table with key 'TRELLO_WEBHOOKS'.

    Uses a single member-level webhook for complete coverage:
    - Receives ALL events from ALL boards across ALL organizations
    - Includes private boards (when token has admin privileges in those orgs)
    - Receives createBoard events for new board discovery
    - Receives admin lifecycle events (demotion/removal)
    - Much simpler than per-board or per-org webhooks
    """

    webhook_id: str | None = None
    member_id: str | None = None
    member_username: str | None = None
    created_at: str | None = None  # ISO 8601 timestamp

    def to_json(self) -> str:
        """Serialize to JSON string for database storage."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "TrelloWebhooksConfig":
        """Deserialize from JSON string."""
        return cls.model_validate_json(json_str)

    @classmethod
    def empty(cls) -> "TrelloWebhooksConfig":
        """Create an empty webhook config."""
        return cls()

    @property
    def has_webhook(self) -> bool:
        """Check if a webhook is registered."""
        return self.webhook_id is not None
