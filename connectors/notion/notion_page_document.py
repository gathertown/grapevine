"""
Notion document classes for structured page and block representation.
"""

import html
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.notion.notion_constants import (
    COMMENT_KEY_PREFIX_BLOCK,
    COMMENT_KEY_PREFIX_PAGE,
    NORMALIZED_PARENT_TYPE_BLOCK,
    NORMALIZED_PARENT_TYPE_PAGE,
)
from src.ingest.references.reference_ids import get_notion_page_reference_id


class NotionPageChunkMetadata(TypedDict):
    """Metadata for Notion page chunks."""

    block_type: str | None
    block_ids: list[str]
    content: str | None
    timestamp: str | None
    formatted_time: str | None
    page_id: str | None
    page_title: str | None
    database_id: str | None
    workspace_id: str | None
    language: str | None
    checked: bool | None
    list_number: int | None


class NotionPageDocumentMetadata(TypedDict):
    """Metadata for Notion page documents."""

    page_id: str | None
    page_title: str | None
    page_url: str | None
    database_id: str | None
    workspace_id: str | None
    properties: dict[str, Any] | None
    source: str
    type: str
    block_count: int
    source_created_at: str | None


class SectionData(TypedDict):
    """Type definition for semantic section data."""

    content: list[str]
    block_ids: list[str]
    heading_level: int
    first_block_type: str | None
    section_heading: str | None


@dataclass
class NotionPageChunk(BaseChunk[NotionPageChunkMetadata]):
    """Represents a single Notion page block chunk."""

    # override the corresponding optional BaseChunk field to require specifying it
    notion_block_ids: list[str]

    @classmethod
    def get_content_from_raw_block_data(cls, raw_block_data: Mapping[str, Any]) -> str:
        block_type = raw_block_data.get("block_type", "")
        content = raw_block_data.get("content", "")

        # Clean and format content for display
        cleaned_content = cls._clean_notion_text(content)
        single_line_content = cleaned_content.replace("\n", " ").replace("\r", " ")
        single_line_content = " ".join(single_line_content.split())

        if block_type == "heading_1":
            return f"# {single_line_content}"
        elif block_type == "heading_2":
            return f"## {single_line_content}"
        elif block_type == "heading_3":
            return f"### {single_line_content}"
        elif block_type == "paragraph":
            return single_line_content
        elif block_type == "bulleted_list_item":
            nesting_level = raw_block_data.get("nesting_level", 0)
            indent = "  " * nesting_level  # 2 spaces per level
            return f"{indent}• {single_line_content}"
        elif block_type == "numbered_list_item":
            number = raw_block_data.get("list_number", 1)
            nesting_level = raw_block_data.get("nesting_level", 0)
            indent = "  " * nesting_level  # 2 spaces per level
            return f"{indent}{number}. {single_line_content}"
        elif block_type == "to_do":
            checked = raw_block_data.get("checked", False)
            checkbox = "☑" if checked else "☐"
            nesting_level = raw_block_data.get("nesting_level", 0)
            indent = "  " * nesting_level  # 2 spaces per level
            return f"{indent}{checkbox} {single_line_content}"
        elif block_type == "code":
            language = raw_block_data.get("language", "")
            return f"```{language}\n{cleaned_content}\n```"
        elif block_type == "quote":
            return f"> {single_line_content}"
        else:
            return single_line_content

    def get_content(self) -> str:
        return self.get_content_from_raw_block_data(self.raw_data)

    @classmethod
    def _clean_notion_text(cls, text: str) -> str:
        """Clean up common Notion text formatting issues."""
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

    def get_metadata(self) -> NotionPageChunkMetadata:
        """Get chunk-specific metadata."""
        metadata: NotionPageChunkMetadata = {
            "block_type": self.raw_data.get("block_type"),
            "block_ids": self.notion_block_ids,  # legacy compat, TODO AIVP-496 remove once we only use turbopuffer
            "content": self.raw_data.get("content"),
            "timestamp": self.raw_data.get("timestamp"),
            "formatted_time": self.raw_data.get("formatted_time"),
            "page_id": self.raw_data.get("page_id"),
            "page_title": self.raw_data.get("page_title"),
            "database_id": self.raw_data.get("database_id"),
            "workspace_id": self.raw_data.get("workspace_id"),
            "language": self.raw_data.get("language"),
            "checked": self.raw_data.get("checked"),
            "list_number": self.raw_data.get("list_number"),
        }

        return metadata


@dataclass
class NotionPageDocument(BaseDocument[NotionPageChunk, NotionPageDocumentMetadata]):
    """Represents a complete Notion page with all its blocks."""

    raw_data: dict[str, Any]

    def _group_comments_by_parent(self) -> dict[str, list[dict[str, Any]]]:
        """Group comments by their parent (block_id or page_id)."""
        comments = self.raw_data.get("comments", [])
        page_id = self.raw_data.get("page_id", "")
        comments_by_parent: dict[str, list[dict[str, Any]]] = {}

        for comment in comments:
            parent_type = comment.get("parent_type", "")
            parent_id = comment.get("parent_id", "")

            if parent_type == NORMALIZED_PARENT_TYPE_PAGE:
                key = f"{COMMENT_KEY_PREFIX_PAGE}{page_id}"
            elif parent_type == NORMALIZED_PARENT_TYPE_BLOCK and parent_id:
                key = f"{COMMENT_KEY_PREFIX_BLOCK}{parent_id}"
            else:
                key = f"{COMMENT_KEY_PREFIX_PAGE}{page_id}"

            if key not in comments_by_parent:
                comments_by_parent[key] = []
            comments_by_parent[key].append(comment)

        return comments_by_parent

    def get_header_content(self) -> str:
        """Get the formatted header section of the document."""
        page_id = self.raw_data.get("page_id", "")
        page_title = self.raw_data.get("page_title", "")
        page_url = self.raw_data.get("page_url", "")
        database_id = self.raw_data.get("database_id", "")
        workspace_id = self.raw_data.get("workspace_id", "")
        blocks = self.raw_data.get("blocks", [])
        properties = self.raw_data.get("properties", {})

        # Build contributors list from blocks with most recent user per user_id
        user_map = {}
        for block in reversed(blocks):
            user_id = block.get("last_edited_by", "")
            user_name = block.get("last_edited_by_name", user_id)  # Use name if provided
            if user_id and user_id not in user_map:
                user_map[user_id] = f"<@{user_id}|@{user_name}>"

        contributors_list = list(user_map.values())

        lines = [f"Page: <{page_id}|{page_title}>", f"URL: {page_url}"]

        if database_id:
            lines.append(f"Database: {database_id}")
        if workspace_id:
            lines.append(f"Workspace: {workspace_id}")
        if contributors_list:
            # This contributor formatting is actually significant for reference detection, so we can
            # detect that these contributors are _users_ and not other notion pages
            # See find_references.py for more
            lines.append(f"Contributors: {', '.join(contributors_list)}")

        # Add properties if they exist
        if properties:
            lines.append("")
            lines.append("Properties:")
            for prop_name, prop_value in properties.items():
                if prop_value:
                    lines.append(f"  {prop_name}: {prop_value}")

        return "\n".join(lines)

    def get_page_comments(self, comments_by_parent: dict[str, list[dict[str, Any]]]) -> str:
        """Get formatted page-level comments."""
        page_id = self.raw_data.get("page_id", "")
        page_comments = comments_by_parent.get(f"{COMMENT_KEY_PREFIX_PAGE}{page_id}", [])

        if not page_comments:
            return ""

        lines = ["", "", "Page Comments:", ""]
        for comment in page_comments:
            comment_content = comment.get("content", "")
            if comment_content.strip():
                created_by_name = comment.get("created_by_name", "Unknown")
                created_time = comment.get("created_time", "")
                lines.append(f"[{created_by_name}, {created_time}]: {comment_content}")

        return "\n".join(lines)

    def get_block_content(self, comments_by_parent: dict[str, list[dict[str, Any]]]) -> str:
        """Get formatted block content with block-level comments."""
        blocks = self.raw_data.get("blocks", [])
        lines = []

        for block_data in blocks:
            content = NotionPageChunk.get_content_from_raw_block_data(block_data)
            if content.strip():
                lines.append(content)

                # Add any comments on this block
                block_id = block_data.get("block_id", "")
                block_comments = comments_by_parent.get(f"{COMMENT_KEY_PREFIX_BLOCK}{block_id}", [])
                if block_comments:
                    for comment in block_comments:
                        comment_content = comment.get("content", "")
                        if comment_content.strip():
                            created_by_name = comment.get("created_by_name", "Unknown")
                            created_time = comment.get("created_time", "")
                            lines.append(
                                f"  [{created_by_name}, {created_time}]: {comment_content}"
                            )

        return "\n".join(lines)

    def get_content(self) -> str:
        """Get the full formatted document content."""
        comments_by_parent = self._group_comments_by_parent()

        parts = [
            self.get_header_content(),
            self.get_page_comments(comments_by_parent),
            "",
            "",
            "Content:",
            "",
            self.get_block_content(comments_by_parent),
        ]

        return "\n".join(parts)

    def to_embedding_chunks(self) -> list[NotionPageChunk]:
        """Convert to embedding chunk format using semantic chunking."""
        chunks: list[NotionPageChunk] = []
        blocks = self.raw_data.get("blocks", [])

        # Add header chunk
        header_chunk = NotionPageChunk(
            document=self,
            notion_block_ids=[],  # empty for the header chunk - all block_ids will be covered below
            raw_data={
                "content": self.get_header_content(),
                "page_id": self.raw_data.get("page_id"),
                "page_title": self.raw_data.get("page_title"),
                "page_url": self.raw_data.get("page_url"),
                "database_id": self.raw_data.get("database_id"),
                "workspace_id": self.raw_data.get("workspace_id"),
                "properties": self.raw_data.get("properties"),
                "source": self.get_source(),
                "type": "notion_page_header",
                "chunk_type": "header",
                "block_count": len(blocks),
                "language": self.raw_data.get("language"),
                "checked": self.raw_data.get("checked"),
                "list_number": self.raw_data.get("list_number"),
            },
        )
        chunks.append(header_chunk)

        # Create semantic chunks from blocks
        semantic_chunks = self._create_semantic_chunks(blocks)
        chunks.extend(semantic_chunks)

        return chunks

    def _create_semantic_chunks(self, blocks: list[dict[str, Any]]) -> list[NotionPageChunk]:
        """Create semantic chunks that preserve document structure and context."""
        if not blocks:
            return []

        chunks = []
        current_section: SectionData = {
            "content": [],
            "block_ids": [],
            "heading_level": 0,
            "first_block_type": None,
            "section_heading": None,
        }

        # Track list continuity
        in_list = False
        list_type = None

        for i, block_data in enumerate(blocks):
            block_type = block_data.get("block_type", "")
            content = NotionPageChunk.get_content_from_raw_block_data(block_data)
            if not content.strip():
                continue

            # Determine if we should start a new chunk
            should_split = False

            # Check heading levels
            if block_type in ["heading_1", "heading_2", "heading_3"]:
                heading_level = int(block_type.split("_")[1])
                # Start new chunk for same or higher level headings
                if (
                    current_section["content"]
                    and heading_level <= current_section["heading_level"]
                    or block_type == "heading_1"
                    and current_section["content"]
                ):
                    should_split = True

            # Check list continuity
            elif block_type in ["bulleted_list_item", "numbered_list_item"]:
                if not in_list or (in_list and list_type != block_type):
                    # Start new chunk if we have non-list content
                    if current_section["content"] and current_section["first_block_type"] not in [
                        "bulleted_list_item",
                        "numbered_list_item",
                    ]:
                        should_split = True
                    in_list = True
                    list_type = block_type
            else:
                # Non-list item
                if in_list:
                    in_list = False
                    list_type = None
                    # Don't split if next block is related (e.g., paragraph after list)
                    if i + 1 < len(blocks):
                        next_block_type = blocks[i + 1].get("block_type", "")
                        if next_block_type not in ["heading_1", "heading_2", "heading_3"]:
                            # Keep paragraph with previous list
                            pass
                        else:
                            should_split = True

            # Check size constraints (approximate token count)
            current_size = sum(len(c.split()) for c in current_section["content"])
            block_size = len(content.split())
            if current_size + block_size > 150:  # ~150 words per chunk
                should_split = True

            # Create chunk if needed
            if should_split and current_section["content"]:
                chunks.append(self._finalize_semantic_chunk(current_section))
                current_section = {
                    "content": [],
                    "block_ids": [],
                    "heading_level": 0,
                    "first_block_type": None,
                    "section_heading": None,
                }

            # Add block to current section
            current_section["content"].append(content)
            current_section["block_ids"].append(block_data.get("block_id", ""))

            # Update section metadata
            if not current_section["first_block_type"]:
                current_section["first_block_type"] = block_type

            # Track heading info
            if block_type in ["heading_1", "heading_2", "heading_3"]:
                current_section["heading_level"] = int(block_type.split("_")[1])
                current_section["section_heading"] = content

        # Don't forget the last section
        if current_section["content"]:
            chunks.append(self._finalize_semantic_chunk(current_section))

        return chunks

    def _finalize_semantic_chunk(self, section: SectionData) -> NotionPageChunk:
        """Finalize a semantic chunk with proper formatting and metadata."""
        # Join content with appropriate spacing
        content = "\n\n".join(section["content"])

        return NotionPageChunk(
            document=self,
            notion_block_ids=section["block_ids"],
            raw_data={
                "content": content,
                "page_id": self.raw_data.get("page_id"),
                "page_title": self.raw_data.get("page_title"),
                "chunk_type": "semantic",
                "source": self.get_source(),
                "type": "notion_page_content",
                "block_count": len(section["block_ids"]),
                "block_ids": section["block_ids"],
                "language": self.raw_data.get("language"),
                "checked": self.raw_data.get("checked"),
                "list_number": self.raw_data.get("list_number"),
            },
        )

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.NOTION

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        page_id = self.raw_data.get("page_id", "")
        return get_notion_page_reference_id(page_uuid=page_id)

    def get_metadata(self) -> NotionPageDocumentMetadata:
        """Get document metadata."""
        blocks = self.raw_data.get("blocks", [])

        # Calculate source_created_at as the page creation time
        source_created_at = None

        # First try to get page creation time from page metadata
        page_created_time = self.raw_data.get("page_created_time") or self.raw_data.get(
            "created_time"
        )
        if page_created_time:
            try:
                from datetime import datetime

                created_dt = datetime.fromisoformat(page_created_time.replace("Z", "+00:00"))
                source_created_at = created_dt.isoformat()
            except (ValueError, TypeError):
                pass

        # If no page creation time, use earliest block timestamp
        if not source_created_at and blocks:
            earliest_ts = None
            for block in blocks:
                timestamp_str = block.get("timestamp") or block.get("created_time")
                if timestamp_str:
                    try:
                        from datetime import datetime

                        block_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        if earliest_ts is None or block_dt < earliest_ts:
                            earliest_ts = block_dt
                    except (ValueError, TypeError):
                        continue

            if earliest_ts:
                source_created_at = earliest_ts.isoformat()

        metadata: NotionPageDocumentMetadata = {
            "page_id": self.raw_data.get("page_id"),
            "page_title": self.raw_data.get("page_title"),
            "page_url": self.raw_data.get("page_url"),
            "database_id": self.raw_data.get("database_id"),
            "workspace_id": self.raw_data.get("workspace_id"),
            "properties": self.raw_data.get("properties"),
            "source": self.get_source(),
            "type": "notion_page_document",
            "block_count": len(blocks),
            "source_created_at": source_created_at,
        }

        return metadata
