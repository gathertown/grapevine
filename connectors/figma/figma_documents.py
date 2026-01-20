"""
Figma document classes for structured file and comment representation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.figma.figma_models import FigmaCommentArtifact, FigmaFileArtifact
from src.permissions.models import PermissionPolicy

# =============================================================================
# Figma File Document
# =============================================================================


class FigmaFileChunkMetadata(TypedDict, total=False):
    """Metadata for Figma file chunks."""

    file_key: str | None
    file_name: str | None
    chunk_type: str | None
    source: str | None


class FigmaFileDocumentMetadata(TypedDict, total=False):
    """Metadata for Figma file documents."""

    file_key: str | None
    file_name: str | None
    editor_type: str | None
    page_count: int | None
    component_count: int | None
    project_id: str | None
    team_id: str | None
    last_modified: str | None
    source_created_at: str | None
    source: str
    type: str


@dataclass
class FigmaFileChunk(BaseChunk[FigmaFileChunkMetadata]):
    """Chunk representing part of a Figma file."""

    def get_content(self) -> str:
        """Get the chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> FigmaFileChunkMetadata:
        """Get chunk-specific metadata."""
        return {
            "file_key": self.raw_data.get("file_key"),
            "file_name": self.raw_data.get("file_name"),
            "chunk_type": self.raw_data.get("chunk_type", "file"),
            "source": "figma_file",
        }


@dataclass
class FigmaFileDocument(BaseDocument[FigmaFileChunk, FigmaFileDocumentMetadata]):
    """Document representing a Figma design file."""

    raw_data: dict[str, Any]
    metadata: FigmaFileDocumentMetadata | None = None
    chunk_class: type[FigmaFileChunk] = FigmaFileChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: FigmaFileArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "FigmaFileDocument":
        """Create document from artifact."""
        content = artifact.content
        metadata = artifact.metadata

        # Store all content data for document
        raw_data = {
            "file_key": content["file_key"],
            "file_name": content["file_name"],
            "thumbnail_url": content.get("thumbnail_url"),
            "last_modified": content["last_modified"],
            "version": content["version"],
            "editor_type": content["editor_type"],
            "role": content["role"],
            "page_names": content["page_names"],
            "component_names": content["component_names"],
            "component_descriptions": content.get("component_descriptions", []),
            "component_count": content["component_count"],
            "page_count": content["page_count"],
            "document_summary": content["document_summary"],
            "text_content": content.get("text_content", []),
            "project_id": metadata.project_id,
            "team_id": metadata.team_id,
        }

        return cls(
            id=f"figma_file_{content['file_key']}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted file content."""
        lines: list[str] = []

        file_name = self.raw_data.get("file_name", "Untitled")
        editor_type = self.raw_data.get("editor_type", "figma")

        # Header
        type_label = "FigJam" if editor_type == "figjam" else "Figma Design"
        lines.append(f"{type_label}: {file_name}")
        lines.append("")

        # File info
        page_count = self.raw_data.get("page_count", 0)
        component_count = self.raw_data.get("component_count", 0)
        lines.append(f"Pages: {page_count}")
        lines.append(f"Components: {component_count}")

        # Page names
        page_names = self.raw_data.get("page_names", [])
        if page_names:
            lines.append("")
            lines.append("Pages:")
            for name in page_names[:20]:  # Limit to first 20 pages
                lines.append(f"  - {name}")
            if len(page_names) > 20:
                lines.append(f"  ... and {len(page_names) - 20} more")

        # Component names
        component_names = self.raw_data.get("component_names", [])
        if component_names:
            lines.append("")
            lines.append("Components:")
            for name in component_names[:30]:  # Limit to first 30 components
                lines.append(f"  - {name}")
            if len(component_names) > 30:
                lines.append(f"  ... and {len(component_names) - 30} more")

        # Component descriptions (if any)
        component_descriptions = self.raw_data.get("component_descriptions", [])
        if component_descriptions:
            lines.append("")
            lines.append("Component Descriptions:")
            for desc in component_descriptions[:20]:
                lines.append(f"  - {desc}")
            if len(component_descriptions) > 20:
                lines.append(f"  ... and {len(component_descriptions) - 20} more")

        # Text content from the design (actual text in the file)
        text_content = self.raw_data.get("text_content", [])
        if text_content:
            lines.append("")
            lines.append("Text Content:")
            # Deduplicate and limit text content
            unique_texts = list(dict.fromkeys(text_content))  # Preserve order, remove duplicates
            for text in unique_texts[:100]:  # Limit to first 100 unique texts
                # Truncate very long text blocks
                if len(text) > 200:
                    text = text[:200] + "..."
                lines.append(f"  {text}")
            if len(unique_texts) > 100:
                lines.append(f"  ... and {len(unique_texts) - 100} more text elements")

        # Document structure summary
        doc_summary = self.raw_data.get("document_summary", "")
        if doc_summary:
            lines.append("")
            lines.append("Structure:")
            lines.append(doc_summary)

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[FigmaFileChunk]:
        """Create chunks for embedding."""
        chunks: list[FigmaFileChunk] = []

        file_key = self.raw_data.get("file_key", "")
        file_name = self.raw_data.get("file_name", "Untitled")

        # Create a single chunk with the full content
        content = f"[{self.id}]\n" + self.get_content()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "file_key": file_key,
                "file_name": file_name,
                "chunk_type": "file",
            },
        )
        self.populate_chunk_permissions(chunk)
        chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.FIGMA_FILE

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        file_key = self.raw_data.get("file_key", "")
        return f"r_figma_file_{file_key}"

    def get_metadata(self) -> FigmaFileDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        # Use last_modified as source_created_at (Figma doesn't provide a separate creation date)
        last_modified = self.raw_data.get("last_modified")

        return {
            "file_key": self.raw_data.get("file_key"),
            "file_name": self.raw_data.get("file_name"),
            "editor_type": self.raw_data.get("editor_type"),
            "page_count": self.raw_data.get("page_count"),
            "component_count": self.raw_data.get("component_count"),
            "project_id": self.raw_data.get("project_id"),
            "team_id": self.raw_data.get("team_id"),
            "last_modified": last_modified,
            "source_created_at": last_modified,
            "source": self.get_source(),
            "type": "figma_file",
        }


# =============================================================================
# Figma Comment Document
# =============================================================================


class FigmaCommentChunkMetadata(TypedDict, total=False):
    """Metadata for Figma comment chunks."""

    comment_id: str | None
    file_key: str | None
    chunk_type: str | None
    is_reply: bool | None
    source: str | None


class FigmaCommentDocumentMetadata(TypedDict, total=False):
    """Metadata for Figma comment documents."""

    comment_id: str | None
    file_key: str | None
    file_name: str | None
    editor_type: str | None
    user_handle: str | None
    user_email: str | None
    is_reply: bool | None
    is_resolved: bool | None
    parent_id: str | None
    created_at: str | None
    resolved_at: str | None
    reply_count: int | None
    source_created_at: str | None
    source: str
    type: str


@dataclass
class FigmaCommentChunk(BaseChunk[FigmaCommentChunkMetadata]):
    """Chunk representing a Figma comment."""

    def get_content(self) -> str:
        """Get the chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> FigmaCommentChunkMetadata:
        """Get chunk-specific metadata."""
        return {
            "comment_id": self.raw_data.get("comment_id"),
            "file_key": self.raw_data.get("file_key"),
            "chunk_type": self.raw_data.get("chunk_type", "comment"),
            "is_reply": self.raw_data.get("is_reply"),
            "source": "figma_comment",
        }


@dataclass
class FigmaCommentDocument(BaseDocument[FigmaCommentChunk, FigmaCommentDocumentMetadata]):
    """Document representing a Figma comment."""

    raw_data: dict[str, Any]
    metadata: FigmaCommentDocumentMetadata | None = None
    chunk_class: type[FigmaCommentChunk] = FigmaCommentChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: FigmaCommentArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
    ) -> "FigmaCommentDocument":
        """Create document from artifact."""
        content = artifact.content
        metadata = artifact.metadata

        raw_data = {
            "comment_id": content["comment_id"],
            "file_key": content["file_key"],
            "file_name": content["file_name"],
            "editor_type": content.get("editor_type"),
            "parent_id": content.get("parent_id"),
            "user_id": content["user_id"],
            "user_handle": content["user_handle"],
            "user_email": content.get("user_email"),
            "created_at": content["created_at"],
            "resolved_at": content.get("resolved_at"),
            "message": content["message"],
            "reply_count": content.get("reply_count", 0),
            "is_reply": metadata.is_reply,
            "is_resolved": metadata.is_resolved,
        }

        return cls(
            id=f"figma_comment_{content['comment_id']}",
            raw_data=raw_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def get_content(self) -> str:
        """Generate formatted comment content."""
        lines: list[str] = []

        file_name = self.raw_data.get("file_name", "Unknown File")
        user_handle = self.raw_data.get("user_handle", "Unknown User")
        message = self.raw_data.get("message", "")
        is_reply = self.raw_data.get("is_reply", False)
        is_resolved = self.raw_data.get("is_resolved", False)
        created_at = self.raw_data.get("created_at", "")

        # Format header
        comment_type = "Reply" if is_reply else "Comment"
        status = " [Resolved]" if is_resolved else ""
        lines.append(f"{comment_type} on {file_name}{status}")
        lines.append("")

        # Author and date
        lines.append(f"By: {user_handle}")
        if created_at:
            lines.append(f"Date: {self._format_date(created_at)}")

        # Message content
        lines.append("")
        lines.append(message)

        # Reply count for parent comments
        reply_count = self.raw_data.get("reply_count", 0)
        if not is_reply and reply_count > 0:
            lines.append("")
            lines.append(f"Replies: {reply_count}")

        return "\n".join(lines)

    def _format_date(self, date_str: str) -> str:
        """Format ISO date string to readable format."""
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return date_str

    def to_embedding_chunks(self) -> list[FigmaCommentChunk]:
        """Create chunks for embedding."""
        chunks: list[FigmaCommentChunk] = []

        comment_id = self.raw_data.get("comment_id", "")
        file_key = self.raw_data.get("file_key", "")
        is_reply = self.raw_data.get("is_reply", False)

        # Create a single chunk with the full content
        content = f"[{self.id}]\n" + self.get_content()

        chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": content,
                "comment_id": comment_id,
                "file_key": file_key,
                "chunk_type": "comment",
                "is_reply": is_reply,
            },
        )
        self.populate_chunk_permissions(chunk)
        chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.FIGMA_COMMENT

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        comment_id = self.raw_data.get("comment_id", "")
        return f"r_figma_comment_{comment_id}"

    def get_metadata(self) -> FigmaCommentDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        created_at = self.raw_data.get("created_at")

        return {
            "comment_id": self.raw_data.get("comment_id"),
            "file_key": self.raw_data.get("file_key"),
            "file_name": self.raw_data.get("file_name"),
            "editor_type": self.raw_data.get("editor_type"),
            "user_handle": self.raw_data.get("user_handle"),
            "user_email": self.raw_data.get("user_email"),
            "is_reply": self.raw_data.get("is_reply"),
            "is_resolved": self.raw_data.get("is_resolved"),
            "parent_id": self.raw_data.get("parent_id"),
            "created_at": created_at,
            "resolved_at": self.raw_data.get("resolved_at"),
            "reply_count": self.raw_data.get("reply_count"),
            "source_created_at": created_at,
            "source": self.get_source(),
            "type": "figma_comment",
        }
