"""
Document and chunk definitions for Intercom conversations.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource


class IntercomConversationChunkMetadata(TypedDict, total=False):
    """Metadata stored on each Intercom conversation chunk."""

    conversation_id: str | None
    section: str
    part_index: int | None
    author_name: str | None
    author_email: str | None
    created_at: str | None
    ai_from_agent: bool | None
    ai_is_answer: bool | None
    chunk_index: int | None
    total_chunks: int | None


class IntercomConversationDocumentMetadata(TypedDict, total=False):
    """Metadata stored on Intercom conversation documents."""

    conversation_id: str
    title: str
    state: str | None
    priority: str | None
    tags: list[str]
    contacts: list[str]
    teammates: list[str]
    participants: list[str]
    topics: list[str]
    linked_objects: list[str]
    source_created_at: str | None
    source: str
    type: str
    workspace_id: str | None


@dataclass
class IntercomConversationChunk(BaseChunk[IntercomConversationChunkMetadata]):
    """Represents a chunk of Intercom conversation content."""

    def get_content(self) -> str:
        return self.raw_data.get("markdown", "")

    def get_metadata(self) -> IntercomConversationChunkMetadata:
        return {
            "conversation_id": self.raw_data.get("conversation_id"),
            "section": self.raw_data.get("section", "full_conversation"),
            "part_index": self.raw_data.get("part_index"),
            "author_name": self.raw_data.get("author_name"),
            "author_email": self.raw_data.get("author_email"),
            "created_at": self.raw_data.get("created_at"),
            "ai_from_agent": self.raw_data.get("ai_flags", {}).get("from_ai_agent"),
            "ai_is_answer": self.raw_data.get("ai_flags", {}).get("is_ai_answer"),
            "chunk_index": self.raw_data.get("chunk_index"),
            "total_chunks": self.raw_data.get("total_chunks"),
        }


@dataclass
class IntercomConversationDocument(
    BaseDocument[IntercomConversationChunk, IntercomConversationDocumentMetadata]
):
    """Structured representation of an Intercom conversation."""

    raw_data: dict[str, Any]
    metadata: IntercomConversationDocumentMetadata | None = None
    chunk_class: type[IntercomConversationChunk] = IntercomConversationChunk

    def get_content(self) -> str:
        return self.raw_data.get("markdown", "")

    def get_metadata(self) -> IntercomConversationDocumentMetadata:
        if self.metadata is None:
            return {
                "conversation_id": self.raw_data.get("conversation_id", self.id),
                "title": str(self.raw_data.get("title", self.id)),
                "state": None,
                "priority": None,
                "tags": [],
                "contacts": [],
                "teammates": [],
                "participants": [],
                "topics": [],
                "linked_objects": [],
                "source_created_at": None,
                "source": DocumentSource.INTERCOM.value,
                "type": "conversation",
            }
        return self.metadata

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.INTERCOM

    def get_reference_id(self) -> str:
        metadata = self.get_metadata()
        return metadata.get("conversation_id", self.id)

    def get_header_content(self) -> str:
        metadata = self.get_metadata()
        return f"Conversation ID: {metadata.get('conversation_id', self.id)}"

    def to_embedding_chunks(self) -> list[IntercomConversationChunk]:
        metadata = self.get_metadata()
        sections = self.raw_data.get("sections") or []

        if not sections:
            sections = [
                {
                    "section_type": "full_conversation",
                    "markdown": self.get_content(),
                    "part_index": None,
                }
            ]

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        chunks: list[IntercomConversationChunk] = []
        for section in sections:
            section_markdown = section.get("markdown", "")
            if not section_markdown.strip():
                continue

            text_chunks = text_splitter.split_text(section_markdown)
            section_type = section.get("section_type", "conversation_part")
            total_chunks = len(text_chunks)

            for chunk_idx, chunk_text in enumerate(text_chunks):
                chunk = self.chunk_class(
                    document=self,
                    raw_data={
                        "markdown": chunk_text,
                        "conversation_id": metadata.get("conversation_id"),
                        "section": section_type
                        if total_chunks == 1
                        else f"{section_type}_part{chunk_idx + 1}",
                        "part_index": section.get("part_index"),
                        "author_name": section.get("author_name"),
                        "author_email": section.get("author_email"),
                        "created_at": section.get("created_at"),
                        "ai_flags": section.get("ai_flags", {}),
                        "chunk_index": chunk_idx,
                        "total_chunks": total_chunks,
                    },
                )
                self.populate_chunk_permissions(chunk)
                chunks.append(chunk)

        return chunks
