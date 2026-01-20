"""
Monday.com item document classes for indexing.
Single-chunk approach for item data with updates embedded.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.base.utils import convert_timestamp_to_iso
from connectors.monday.client import MONDAY_ITEM_DOC_ID_PREFIX
from connectors.monday.extractors.artifacts import MondayItemArtifact
from src.permissions.models import PermissionPolicy


class MondayItemChunkMetadata(TypedDict, total=False):
    """Metadata for Monday.com item chunks."""

    item_id: int | None
    item_name: str | None
    board_id: int | None
    board_name: str | None
    created_at: str | None
    updated_at: str | None


class MondayItemDocumentMetadata(TypedDict, total=False):
    """Metadata for Monday.com item documents."""

    item_id: int
    item_name: str | None
    board_id: int
    board_name: str | None
    workspace_id: int | None
    workspace_name: str | None
    group_id: str | None
    group_title: str | None
    state: str
    creator_id: int | None
    creator_name: str | None
    subscriber_ids: list[int] | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class MondayItemChunk(BaseChunk[MondayItemChunkMetadata]):
    """Single chunk representing entire Monday.com item."""

    def get_content(self) -> str:
        """Return the formatted item content."""
        parts = []
        if self.raw_data.get("name"):
            parts.append(f"Item: {self.raw_data.get('name')}")
        if self.raw_data.get("board_name"):
            parts.append(f"Board: {self.raw_data.get('board_name')}")
        if self.raw_data.get("group_title"):
            parts.append(f"Group: {self.raw_data.get('group_title')}")

        # Add column values
        column_values = self.raw_data.get("column_values", [])
        if column_values:
            parts.append("")
            parts.append("Fields:")
            for cv in column_values:
                if cv.get("text"):
                    parts.append(f"  {cv.get('title', 'Field')}: {cv.get('text')}")

        # Add updates/comments
        updates = self.raw_data.get("updates", [])
        if updates:
            parts.append("")
            parts.append("Updates:")
            for update in updates:
                creator = update.get("creator_name", "Unknown")
                text = update.get("text_body", "")
                if text:
                    parts.append(f"  [{creator}]: {text}")

        return "\n".join(parts) if parts else "Monday.com item"

    def get_metadata(self) -> MondayItemChunkMetadata:
        """Get chunk metadata."""
        return {
            "item_id": self.raw_data.get("item_id"),
            "item_name": self.raw_data.get("name"),
            "board_id": self.raw_data.get("board_id"),
            "board_name": self.raw_data.get("board_name"),
            "created_at": self.raw_data.get("created_at"),
            "updated_at": self.raw_data.get("updated_at"),
        }


@dataclass
class MondayItemDocument(BaseDocument[MondayItemChunk, MondayItemDocumentMetadata]):
    """Monday.com item document with formatted content."""

    raw_data: dict[str, Any]
    metadata: MondayItemDocumentMetadata | None = None
    chunk_class: type[MondayItemChunk] = MondayItemChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: MondayItemArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "MondayItemDocument":
        """Create document from artifact."""
        content = artifact.content
        item_id = content.item_id

        raw_data = {
            "item_id": item_id,
            "name": content.name,
            "state": content.state.value,
            "board_id": content.board.id,
            "board_name": content.board.name,
            "board_description": content.board.description,
            "board_kind": content.board.board_kind.value,
            "workspace_id": content.workspace.id if content.workspace else None,
            "workspace_name": content.workspace.name if content.workspace else None,
            "group_id": content.group.id if content.group else None,
            "group_title": content.group.title if content.group else None,
            "column_values": [cv.model_dump() for cv in content.column_values],
            "updates": [u.model_dump() for u in content.updates],
            "creator_id": content.creator.id if content.creator else None,
            "creator_name": content.creator.name if content.creator else None,
            "subscriber_ids": [s.id for s in content.subscribers],
            "relative_link": content.relative_link,
            "created_at": artifact.metadata.source_created_at,  # Already ISO string
            "updated_at": artifact.source_updated_at.isoformat(),
        }

        return cls(
            id=f"{MONDAY_ITEM_DOC_ID_PREFIX}{item_id}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted item content."""
        lines: list[str] = []

        # Header
        name = self.raw_data.get("name") or "Unnamed Item"
        item_id = self.raw_data.get("item_id", self.id.replace(MONDAY_ITEM_DOC_ID_PREFIX, ""))
        lines.append(f"Monday.com Item: {name} (#{item_id})")
        lines.append("")

        # Item Overview Section
        lines.append("=== ITEM OVERVIEW ===")
        lines.append(f"Name: {name}")

        state = self.raw_data.get("state", "active")
        if state != "active":
            lines.append(f"State: {state}")

        board_name = self.raw_data.get("board_name")
        if board_name:
            lines.append(f"Board: {board_name}")

        group_title = self.raw_data.get("group_title")
        if group_title:
            lines.append(f"Group: {group_title}")

        workspace_name = self.raw_data.get("workspace_name")
        if workspace_name:
            lines.append(f"Workspace: {workspace_name}")

        lines.append("")

        # Column Values Section
        column_values = self.raw_data.get("column_values", [])
        if column_values:
            lines.append("=== FIELDS ===")
            for cv in column_values:
                text = cv.get("text")
                if text:
                    title = cv.get("title", "Field")
                    lines.append(f"{title}: {text}")
            lines.append("")

        # Updates Section
        updates = self.raw_data.get("updates", [])
        if updates:
            lines.append("=== UPDATES ===")
            for update in updates:
                creator = update.get("creator_name", "Unknown")
                text = update.get("text_body", "")
                created = update.get("created_at", "")
                if text:
                    date_str = self._format_date(created) if created else ""
                    lines.append(f"[{creator}] ({date_str}): {text}")
            lines.append("")

        # Metadata Section
        lines.append("=== METADATA ===")

        creator_name = self.raw_data.get("creator_name")
        if creator_name:
            lines.append(f"Creator: {creator_name}")

        create_date = self.raw_data.get("created_at")
        if create_date:
            lines.append(f"Created: {self._format_date(create_date)}")

        modified_date = self.raw_data.get("updated_at")
        if modified_date:
            lines.append(f"Last modified: {self._format_date(modified_date)}")

        lines.append(f"Monday.com Item ID: {item_id}")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[MondayItemChunk]:
        """Create single chunk for the entire item."""
        metadata = self.get_metadata()

        chunk_data = {
            "item_id": metadata.get("item_id"),
            "name": metadata.get("item_name"),
            "board_id": metadata.get("board_id"),
            "board_name": metadata.get("board_name"),
            "group_title": metadata.get("group_title"),
            "column_values": self.raw_data.get("column_values", []),
            "updates": self.raw_data.get("updates", []),
            "created_at": metadata.get("source_created_at"),
            "updated_at": metadata.get("source_updated_at"),
        }

        chunk = self.chunk_class(
            document=self,
            raw_data=chunk_data,
        )
        self.populate_chunk_permissions(chunk)

        return [chunk]

    def get_metadata(self) -> MondayItemDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        state = self.raw_data.get("state", "active")

        return {
            "item_id": self.raw_data.get("item_id", 0),
            "item_name": self.raw_data.get("name"),
            "board_id": self.raw_data.get("board_id", 0),
            "board_name": self.raw_data.get("board_name"),
            "workspace_id": self.raw_data.get("workspace_id"),
            "workspace_name": self.raw_data.get("workspace_name"),
            "group_id": self.raw_data.get("group_id"),
            "group_title": self.raw_data.get("group_title"),
            "state": state,
            "creator_id": self.raw_data.get("creator_id"),
            "creator_name": self.raw_data.get("creator_name"),
            "subscriber_ids": self.raw_data.get("subscriber_ids"),
            "source_created_at": convert_timestamp_to_iso(self.raw_data.get("created_at")),
            "source_updated_at": convert_timestamp_to_iso(self.raw_data.get("updated_at")),
            "source": DocumentSource.MONDAY_ITEM.value,
            "type": "monday_item",
        }

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.MONDAY_ITEM

    def get_reference_id(self) -> str:
        """Get reference ID for this document."""
        item_id = self.raw_data.get("item_id", self.id.replace(MONDAY_ITEM_DOC_ID_PREFIX, ""))
        return f"r_monday_item_{item_id}"

    def get_header_content(self) -> str:
        """Get header content for display."""
        metadata = self.get_metadata()
        name = metadata.get("item_name") or "Unknown Item"
        board = metadata.get("board_name") or "Unknown Board"
        return f"Monday.com Item: {name} in {board}"

    def _format_date(self, date_str: str) -> str:
        """Format ISO date string to readable format."""
        if not date_str:
            return ""
        try:
            if "T" in date_str:
                date_str = date_str.split("T")[0]
            return date_str
        except Exception:
            return date_str
