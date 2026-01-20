"""Monday.com artifact definitions.

Artifacts represent the raw data structure from Monday.com API before
transformation into searchable documents.
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import (
    ArtifactEntity,
    BaseIngestArtifact,
    get_monday_item_entity_id,
)


class MondayItemState(str, Enum):
    """Monday.com item states."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class MondayBoardKind(str, Enum):
    """Monday.com board types."""

    PUBLIC = "public"
    PRIVATE = "private"
    SHARE = "share"


class MondayColumnValue(BaseModel):
    """A column value for a Monday.com item."""

    id: str
    title: str
    type: str
    text: str | None = None
    value: Any | None = None  # JSON value varies by column type


class MondayUpdate(BaseModel):
    """A comment/update on a Monday.com item."""

    id: int
    body: str
    text_body: str  # Plain text version of body
    creator_id: int | None = None
    creator_name: str | None = None
    created_at: str  # ISO format string for JSON serialization
    updated_at: str | None = None  # ISO format string for JSON serialization


class MondayUser(BaseModel):
    """A Monday.com user reference."""

    id: int
    name: str
    email: str | None = None


class MondayGroup(BaseModel):
    """A group within a Monday.com board."""

    id: str
    title: str
    color: str | None = None


class MondayBoardInfo(BaseModel):
    """Basic board information embedded in items."""

    id: int
    name: str
    description: str | None = None
    board_kind: MondayBoardKind


class MondayWorkspaceInfo(BaseModel):
    """Basic workspace information."""

    id: int
    name: str
    description: str | None = None


class MondayItemArtifactContent(BaseModel):
    """Content data for a Monday.com item artifact."""

    item_id: int
    name: str
    state: MondayItemState
    board: MondayBoardInfo
    group: MondayGroup | None = None
    workspace: MondayWorkspaceInfo | None = None
    column_values: list[MondayColumnValue] = []
    updates: list[MondayUpdate] = []
    creator: MondayUser | None = None
    subscribers: list[MondayUser] = []
    relative_link: str | None = None  # URL path for deep linking


class MondayItemArtifactMetadata(BaseModel):
    """Metadata for a Monday.com item artifact."""

    item_id: int
    board_id: int
    board_name: str
    workspace_id: int | None = None
    workspace_name: str | None = None
    group_id: str | None = None
    group_title: str | None = None
    state: MondayItemState
    creator_id: int | None = None
    creator_name: str | None = None
    subscriber_ids: list[int] = []
    source_created_at: str  # ISO format string for JSON serialization


class MondayItemArtifact(BaseIngestArtifact):
    """Complete Monday.com item artifact.

    Inherits from BaseIngestArtifact to integrate with the standard
    artifact storage and indexing pipeline.
    """

    entity: ArtifactEntity = ArtifactEntity.MONDAY_ITEM
    content: MondayItemArtifactContent
    metadata: MondayItemArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        item_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> "MondayItemArtifact":
        """Create artifact from Monday.com API response.

        Args:
            item_data: Raw item data from Monday.com GraphQL API
            ingest_job_id: The ingest job ID for tracking

        Returns:
            MondayItemArtifact instance
        """
        item_id = int(item_data["id"])
        name = item_data.get("name", "")
        state_str = item_data.get("state", "active")
        state = MondayItemState(state_str) if state_str else MondayItemState.ACTIVE

        # Parse board info
        board_data = item_data.get("board", {})
        board_id = int(board_data.get("id", 0))
        board_kind_str = board_data.get("board_kind", "public")
        board = MondayBoardInfo(
            id=board_id,
            name=board_data.get("name", ""),
            description=board_data.get("description"),
            board_kind=MondayBoardKind(board_kind_str),
        )

        # Parse group info
        group = None
        group_data = item_data.get("group")
        if group_data:
            group = MondayGroup(
                id=group_data.get("id", ""),
                title=group_data.get("title", ""),
                color=group_data.get("color"),
            )

        # Parse workspace info
        workspace = None
        workspace_data = board_data.get("workspace")
        if workspace_data:
            workspace = MondayWorkspaceInfo(
                id=int(workspace_data.get("id", 0)),
                name=workspace_data.get("name", ""),
                description=workspace_data.get("description"),
            )

        # Parse column values
        column_values = []
        for cv in item_data.get("column_values", []):
            column_values.append(
                MondayColumnValue(
                    id=cv.get("id", ""),
                    title=cv.get("title", cv.get("column", {}).get("title", "")),
                    type=cv.get("type", ""),
                    text=cv.get("text"),
                    value=cv.get("value"),
                )
            )

        # Parse updates (comments)
        updates = []
        for update in item_data.get("updates", []):
            creator_data = update.get("creator")
            updates.append(
                MondayUpdate(
                    id=int(update.get("id", 0)),
                    body=update.get("body", ""),
                    text_body=update.get("text_body", ""),
                    creator_id=int(creator_data.get("id", 0)) if creator_data else None,
                    creator_name=creator_data.get("name") if creator_data else None,
                    created_at=update.get("created_at", ""),  # Keep as ISO string
                    updated_at=update.get("updated_at"),  # Keep as ISO string
                )
            )

        # Parse creator
        creator = None
        creator_data = item_data.get("creator")
        if creator_data:
            creator = MondayUser(
                id=int(creator_data.get("id", 0)),
                name=creator_data.get("name", ""),
                email=creator_data.get("email"),
            )

        # Parse subscribers
        subscribers = []
        for sub in item_data.get("subscribers", []):
            subscribers.append(
                MondayUser(
                    id=int(sub.get("id", 0)),
                    name=sub.get("name", ""),
                    email=sub.get("email"),
                )
            )

        # Parse timestamps
        created_at_str = item_data.get("created_at", "")
        updated_at_str = item_data.get("updated_at", "")

        # Store as ISO string in metadata for JSON serialization
        source_created_at_str = created_at_str if created_at_str else datetime.now(UTC).isoformat()

        # Parse to datetime for BaseIngestArtifact.source_updated_at
        source_updated_at = (
            datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            if updated_at_str
            else (
                datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if created_at_str
                else datetime.now(UTC)
            )
        )

        content = MondayItemArtifactContent(
            item_id=item_id,
            name=name,
            state=state,
            board=board,
            group=group,
            workspace=workspace,
            column_values=column_values,
            updates=updates,
            creator=creator,
            subscribers=subscribers,
            relative_link=item_data.get("relative_link"),
        )

        metadata = MondayItemArtifactMetadata(
            item_id=item_id,
            board_id=board_id,
            board_name=board.name,
            workspace_id=workspace.id if workspace else None,
            workspace_name=workspace.name if workspace else None,
            group_id=group.id if group else None,
            group_title=group.title if group else None,
            state=state,
            creator_id=creator.id if creator else None,
            creator_name=creator.name if creator else None,
            subscriber_ids=[s.id for s in subscribers],
            source_created_at=source_created_at_str,
        )

        return cls(
            entity_id=get_monday_item_entity_id(item_id=item_id),
            ingest_job_id=ingest_job_id,
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
        )
