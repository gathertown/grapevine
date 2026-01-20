"""
Canva document classes for structured design representation.
"""

import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.canva.canva_models import CanvaDesignArtifact
from src.permissions.models import PermissionPolicy

# =============================================================================
# Canva Design Document
# =============================================================================


class CanvaDesignChunkMetadata(TypedDict, total=False):
    """Metadata for Canva design chunks."""

    design_id: str | None
    design_title: str | None
    chunk_type: str | None
    source: str | None


class CanvaDesignDocumentMetadata(TypedDict, total=False):
    """Metadata for Canva design documents."""

    design_id: str | None
    design_title: str | None
    owner_user_id: str | None
    owner_team_id: str | None
    page_count: int | None
    edit_url: str | None
    view_url: str | None
    thumbnail_url: str | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class CanvaDesignChunk(BaseChunk[CanvaDesignChunkMetadata]):
    """Chunk representing part of a Canva design."""

    def get_content(self) -> str:
        """Get the chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> CanvaDesignChunkMetadata:
        """Get chunk-specific metadata."""
        return {
            "design_id": self.raw_data.get("design_id"),
            "design_title": self.raw_data.get("design_title"),
            "chunk_type": self.raw_data.get("chunk_type", "design"),
            "source": "canva_design",
        }


@dataclass
class CanvaDesignDocument(BaseDocument[CanvaDesignChunk, CanvaDesignDocumentMetadata]):
    """Document representing a Canva design."""

    raw_data: dict[str, Any]
    metadata: CanvaDesignDocumentMetadata | None = None
    chunk_class: type[CanvaDesignChunk] = CanvaDesignChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: CanvaDesignArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "CanvaDesignDocument":
        """Create document from artifact."""
        content = artifact.content

        raw_data = {
            "design_id": content["design_id"],
            "title": content["title"],
            "edit_url": content.get("edit_url"),
            "view_url": content.get("view_url"),
            "thumbnail_url": content.get("thumbnail_url"),
            "page_count": content.get("page_count"),
            "owner_user_id": content.get("owner_user_id"),
            "owner_team_id": content.get("owner_team_id"),
            "created_at": content.get("created_at"),
            "updated_at": content.get("updated_at"),
        }

        return cls(
            id=f"canva_design_{content['design_id']}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted design content."""
        lines: list[str] = []

        title = self.raw_data.get("title", "Untitled Design")

        # Header
        lines.append(f"Canva Design: {title}")
        lines.append("")

        # Design info
        page_count = self.raw_data.get("page_count")
        if page_count is not None:
            lines.append(f"Pages: {page_count}")

        # Timestamps
        created_at = self.raw_data.get("created_at")
        updated_at = self.raw_data.get("updated_at")

        if created_at:
            lines.append(f"Created: {self._format_timestamp(created_at)}")
        if updated_at:
            lines.append(f"Last Modified: {self._format_timestamp(updated_at)}")

        return "\n".join(lines)

    def _format_timestamp(self, timestamp: int | None) -> str:
        """Format Unix timestamp to readable format."""
        if timestamp is None:
            return "Unknown"
        try:
            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError, OSError):
            return str(timestamp)

    def to_embedding_chunks(self) -> list[CanvaDesignChunk]:
        """Create chunks for embedding."""
        chunks: list[CanvaDesignChunk] = []

        design_id = self.raw_data.get("design_id", "")
        title = self.raw_data.get("title", "Untitled Design")

        # Create a single chunk with the full content
        content = f"[{self.id}]\n" + self.get_content()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "design_id": design_id,
                "design_title": title,
                "chunk_type": "design",
            },
        )
        self.populate_chunk_permissions(chunk)
        chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.CANVA_DESIGN

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        design_id = self.raw_data.get("design_id", "")
        return f"r_canva_design_{design_id}"

    def get_metadata(self) -> CanvaDesignDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        # Convert timestamps to ISO strings
        created_at = self.raw_data.get("created_at")
        updated_at = self.raw_data.get("updated_at")

        source_created_at_str = None
        source_updated_at_str = None

        if created_at is not None:
            with contextlib.suppress(ValueError, TypeError, OSError):
                source_created_at_str = datetime.fromtimestamp(created_at).isoformat()

        if updated_at is not None:
            with contextlib.suppress(ValueError, TypeError, OSError):
                source_updated_at_str = datetime.fromtimestamp(updated_at).isoformat()

        return {
            "design_id": self.raw_data.get("design_id"),
            "design_title": self.raw_data.get("title"),
            "owner_user_id": self.raw_data.get("owner_user_id"),
            "owner_team_id": self.raw_data.get("owner_team_id"),
            "page_count": self.raw_data.get("page_count"),
            "edit_url": self.raw_data.get("edit_url"),
            "view_url": self.raw_data.get("view_url"),
            "thumbnail_url": self.raw_data.get("thumbnail_url"),
            "source_created_at": source_created_at_str,
            "source_updated_at": source_updated_at_str,
            "source": self.get_source(),
            "type": "canva_design",
        }
