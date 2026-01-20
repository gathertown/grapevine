"""
Confluence document classes for structured page and content representation.
"""

import html
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from src.ingest.references.reference_ids import get_confluence_page_reference_id


class ConfluencePageChunkMetadata(TypedDict):
    """Metadata for Confluence page chunks."""

    content_type: str | None  # "header", "content", "comment"
    page_id: str | None
    page_title: str | None
    space_id: str | None
    space_name: str | None
    space_key: str | None
    version_number: int | None
    last_modified: str | None
    formatted_time: str | None
    author_id: str | None
    author_name: str | None
    comment_id: str | None  # For comment chunks
    parent_page_id: str | None
    page_status: str | None  # "current", "deleted", "trashed"


class ConfluencePageDocumentMetadata(TypedDict):
    """Metadata for Confluence page documents."""

    page_id: str  # Confluence page ID
    page_title: str  # Page title
    page_url: str  # Full URL to the page
    space_id: str  # Space ID
    participants: dict[str, str]  # User ID to display name mapping
    parent_page_id: str | None  # Parent page ID if this is a child page
    source_created_at: str | None  # Page creation timestamp
    source_updated_at: str | None  # Page last modified timestamp


class SectionData(TypedDict):
    """Type definition for semantic section data."""

    content: list[str]
    heading_level: int
    first_content_type: str | None
    section_heading: str | None


@dataclass
class ConfluencePageChunk(BaseChunk[ConfluencePageChunkMetadata]):
    """Represents a single Confluence page content chunk."""

    @classmethod
    def get_content_from_raw_content_data(cls, raw_content_data: Mapping[str, Any]) -> str:
        content_type = raw_content_data.get("content_type", "")
        content = raw_content_data.get("content", "")

        # Clean and format content for display
        cleaned_content = cls._clean_confluence_text(content)

        if content_type == "header" or content_type == "content":
            return cleaned_content
        else:
            return cleaned_content

    def get_content(self) -> str:
        return self.get_content_from_raw_content_data(self.raw_data)

    @classmethod
    def _clean_confluence_text(cls, text: str) -> str:
        """Clean up common Confluence text formatting issues."""
        if not text:
            return text

        # Decode HTML entities
        text = html.unescape(text)

        # Fix UTF-8 bytes that were incorrectly decoded as Latin-1
        try:
            if any(char in text for char in ["â€", "Â"]):
                text = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        return text

    def get_metadata(self) -> ConfluencePageChunkMetadata:
        """Get chunk-specific metadata."""
        metadata: ConfluencePageChunkMetadata = {
            "content_type": self.raw_data.get("content_type"),
            "page_id": self.raw_data.get("page_id"),
            "page_title": self.raw_data.get("page_title"),
            "space_id": self.raw_data.get("space_id"),
            "space_name": self.raw_data.get("space_name"),
            "space_key": self.raw_data.get("space_key"),
            "version_number": self.raw_data.get("version_number"),
            "last_modified": self.raw_data.get("last_modified"),
            "formatted_time": self.raw_data.get("formatted_time"),
            "author_id": self.raw_data.get("author_id"),
            "author_name": self.raw_data.get("author_name"),
            "comment_id": self.raw_data.get("comment_id"),
            "parent_page_id": self.raw_data.get("parent_page_id"),
            "page_status": self.raw_data.get("page_status"),
        }
        return metadata

    def get_reference_id(self) -> str:
        """Generate a reference ID for this chunk."""
        page_id = self.raw_data.get("page_id")
        if not page_id:
            return f"confluence_page_chunk_{id(self)}"

        content_type = self.raw_data.get("content_type", "content")
        if content_type == "header":
            return f"confluence_page_{page_id}_header"
        else:
            return f"confluence_page_{page_id}_content_{id(self)}"


@dataclass
class ConfluencePageDocument(BaseDocument[ConfluencePageChunk, ConfluencePageDocumentMetadata]):
    """Represents a complete Confluence page with its content and metadata."""

    raw_data: dict[str, Any]

    def get_header_content(self) -> str:
        """Get the formatted header section following the desired format."""
        page_id = self.raw_data.get("page_id", "")
        page_title = self.raw_data.get("page_title", "")
        page_url = self.raw_data.get("page_url", "")
        space_id = self.raw_data.get("space_id", "")

        # Build contributors list from participants
        participants = self.raw_data.get("participants", {})
        contributors_list = []
        for user_id, user_name in participants.items():
            contributors_list.append(f"<@{user_id}|@{user_name}>")

        # Build header in the desired format
        header_lines = [
            f"Page: <{page_id}|{page_title}>",
            f"URL: {page_url}",
        ]

        if contributors_list:
            header_lines.append(f"Contributors: {', '.join(contributors_list)}")

        # Add space information
        header_lines.append(f"Space: <{space_id}>")

        # Add parent page if exists
        parent_page_id = self.raw_data.get("parent_page_id")
        if parent_page_id:
            header_lines.append(f"Parent Page: <{parent_page_id}>")

        return "\n".join(header_lines)

    def get_content(self) -> str:
        """Get the formatted document content."""
        header = self.get_header_content()

        # Get page body content
        page_content = self.raw_data.get("body_content", "")
        if page_content:
            page_content = self._clean_confluence_text(page_content)

        # Build full content
        lines = [header]
        lines.extend(["", "", "Content:", ""])

        if page_content:
            lines.append(page_content)

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[ConfluencePageChunk]:
        """Convert to embedding chunk format using semantic chunking."""
        chunks: list[ConfluencePageChunk] = []

        # Add header chunk
        header_chunk = ConfluencePageChunk(
            document=self,
            raw_data={
                "content": self.get_header_content(),
                "content_type": "header",
                "page_id": self.raw_data.get("page_id"),
                "page_title": self.raw_data.get("page_title"),
                "space_id": self.raw_data.get("space_id"),
                "space_name": self.raw_data.get("space_name"),
                "space_key": self.raw_data.get("space_key"),
                "version_number": self.raw_data.get("version_number"),
                "last_modified": self.raw_data.get("last_modified"),
                "formatted_time": self.raw_data.get("formatted_time"),
                "page_status": self.raw_data.get("status"),
            },
        )
        chunks.append(header_chunk)

        # Add content chunk if body content exists
        page_content = self.raw_data.get("body_content", "")
        if page_content and page_content.strip():
            content_chunk = ConfluencePageChunk(
                document=self,
                raw_data={
                    "content": self._clean_confluence_text(page_content),
                    "content_type": "content",
                    "page_id": self.raw_data.get("page_id"),
                    "page_title": self.raw_data.get("page_title"),
                    "space_id": self.raw_data.get("space_id"),
                    "space_name": self.raw_data.get("space_name"),
                    "space_key": self.raw_data.get("space_key"),
                    "version_number": self.raw_data.get("version_number"),
                    "last_modified": self.raw_data.get("last_modified"),
                    "formatted_time": self.raw_data.get("formatted_time"),
                    "page_status": self.raw_data.get("status"),
                },
            )
            chunks.append(content_chunk)

        return chunks

    @classmethod
    def _clean_confluence_text(cls, text: str) -> str:
        """Clean up common Confluence text formatting issues."""
        if not text:
            return text

        # Decode HTML entities
        text = html.unescape(text)

        # Fix UTF-8 bytes that were incorrectly decoded as Latin-1
        try:
            if any(char in text for char in ["â€", "Â"]):
                text = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        return text

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.CONFLUENCE

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        page_id = self.raw_data.get("page_id", "")
        return get_confluence_page_reference_id(page_id=page_id)

    def get_metadata(self) -> ConfluencePageDocumentMetadata:
        """Get document metadata."""
        metadata: ConfluencePageDocumentMetadata = {
            "page_id": self.raw_data.get("page_id", ""),
            "page_title": self.raw_data.get("page_title", ""),
            "page_url": self.raw_data.get("page_url", ""),
            "space_id": self.raw_data.get("space_id", ""),
            "participants": self.raw_data.get("participants", {}),
            "parent_page_id": self.raw_data.get("parent_page_id"),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_updated_at": self.raw_data.get("source_updated_at"),
        }
        return metadata
