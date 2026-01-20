"""
Google Drive document classes for structured file representation.
"""

import logging
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource

logger = logging.getLogger(__name__)


class GoogleDriveDocumentMetadata(TypedDict):
    """Metadata for Google Drive file documents."""

    file_id: str | None
    file_name: str | None
    mime_type: str | None
    drive_id: str | None
    drive_name: str | None
    parent_folder_ids: list[str]
    web_view_link: str | None
    size_bytes: int | None
    starred: bool
    source_created_at: str | None
    source_modified_at: str | None
    owners: list[dict[str, Any]]
    last_modifying_user: dict[str, Any] | None
    description: str | None


@dataclass
class GoogleDriveFileChunk(BaseChunk[dict[str, Any]]):
    """Represents a chunk of a Google Drive file."""

    def get_content(self) -> str:
        """Get the formatted chunk content."""
        content = self.raw_data.get("content", "")
        chunk_index = self.raw_data.get("chunk_index", 0)
        total_chunks = self.raw_data.get("total_chunks", 1)

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> dict[str, Any]:
        """Get chunk-specific metadata."""
        metadata = {
            "file_id": self.raw_data.get("file_id"),
            "file_name": self.raw_data.get("file_name"),
            "mime_type": self.raw_data.get("mime_type"),
            "chunk_index": self.raw_data.get("chunk_index", 0),
            "total_chunks": self.raw_data.get("total_chunks", 1),
            "drive_id": self.raw_data.get("drive_id"),
            "drive_name": self.raw_data.get("drive_name"),
            "parent_folder_ids": self.raw_data.get("parent_folder_ids", []),
            "web_view_link": self.raw_data.get("web_view_link"),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_modified_at": self.raw_data.get("source_modified_at"),
        }

        if self.raw_data.get("owners"):
            metadata["owners"] = self.raw_data.get("owners")
        if self.raw_data.get("last_modifying_user"):
            metadata["last_modifying_user"] = self.raw_data.get("last_modifying_user")

        return metadata


@dataclass(
    kw_only=True
)  # kw_only to support adding new required fields without breaking default args in BaseDocument
class GoogleDriveFileDocument(BaseDocument[GoogleDriveFileChunk, GoogleDriveDocumentMetadata]):
    """Represents a complete Google Drive file document."""

    raw_data: dict[str, Any]

    metadata: dict[str, Any]
    source = DocumentSource.GOOGLE_DRIVE

    def get_source_enum(self) -> DocumentSource:
        return self.source

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return "r_google_drive_placeholder_" + self.id

    def to_embedding_chunks(self) -> list[GoogleDriveFileChunk]:
        """Convert document to embedding chunk format using langchain text splitting."""
        full_content = self.get_content()

        if not full_content.strip():
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        text_chunks = text_splitter.split_text(full_content)

        logger.info(
            f"Google Drive file {self.metadata.get('file_name', 'unknown')} created {len(text_chunks)} chunks from {len(full_content)} characters"
        )

        embedding_chunks = []
        base_metadata = self._get_base_chunk_metadata()

        for i, chunk_text in enumerate(text_chunks):
            chunk_data = {
                **base_metadata,
                "content": chunk_text,
                "chunk_index": i,
                "total_chunks": len(text_chunks),
            }

            embedding_chunks.append(
                GoogleDriveFileChunk(
                    document=self,
                    raw_data=chunk_data,
                )
            )

        return embedding_chunks

    def _get_base_chunk_metadata(self) -> dict[str, Any]:
        """Get base metadata that applies to all chunks of this document."""
        return {
            "file_id": self.metadata.get("file_id"),
            "file_name": self.metadata.get("file_name"),
            "mime_type": self.metadata.get("mime_type"),
            "drive_id": self.metadata.get("drive_id"),
            "drive_name": self.metadata.get("drive_name"),
            "parent_folder_ids": self.metadata.get("parent_folder_ids", []),
            "web_view_link": self.metadata.get("web_view_link"),
            "source_created_at": self.metadata.get("source_created_at"),
            "source_modified_at": self.metadata.get("source_modified_at"),
            "owners": self.metadata.get("owners", []),
            "last_modifying_user": self.metadata.get("last_modifying_user"),
        }

    def get_content(self) -> str:
        """Get the full document content."""
        return self.raw_data.get("processed_content", "")

    def get_title(self) -> str:
        """Get the document title."""
        file_name = self.metadata.get("file_name", "Untitled")
        return file_name

    def get_url(self) -> str | None:
        """Get the document URL."""
        return self.metadata.get("web_view_link")

    def format_for_display(self) -> str:
        """Format the document for display."""
        lines = []

        lines.append(f"# {self.get_title()}")
        lines.append("")

        if self.metadata.get("description"):
            lines.append(f"**Description:** {self.metadata['description']}")
            lines.append("")

        if self.metadata.get("last_modifying_user"):
            user = self.metadata["last_modifying_user"]
            user_name = user.get("display_name", "Unknown")
            lines.append(f"**Last modified by:** {user_name}")

        if self.metadata.get("source_modified_at"):
            lines.append(f"**Modified:** {self.metadata['source_modified_at']}")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(self.get_content())

        return "\n".join(lines)

    def get_searchable_content(self) -> str:
        """Get content optimized for search indexing."""
        parts = []

        parts.append(self.metadata.get("file_name", ""))

        if self.metadata.get("description"):
            parts.append(self.metadata["description"])

        parts.append(self.get_content())

        return "\n\n".join(filter(None, parts))

    def get_metadata(self) -> GoogleDriveDocumentMetadata:
        """Get document-level metadata."""
        return GoogleDriveDocumentMetadata(
            file_id=self.metadata.get("file_id"),
            file_name=self.metadata.get("file_name"),
            mime_type=self.metadata.get("mime_type"),
            drive_id=self.metadata.get("drive_id"),
            drive_name=self.metadata.get("drive_name"),
            parent_folder_ids=self.metadata.get("parent_folder_ids", []),
            web_view_link=self.metadata.get("web_view_link"),
            size_bytes=self.metadata.get("size_bytes"),
            starred=self.metadata.get("starred", False),
            source_created_at=self.metadata.get("source_created_at"),
            source_modified_at=self.metadata.get("source_modified_at"),
            owners=self.metadata.get("owners", []),
            last_modifying_user=self.metadata.get("last_modifying_user"),
            description=self.metadata.get("description"),
        )
