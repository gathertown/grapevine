"""
Google Email document classes for structured message representation.
"""

import logging
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource

logger = logging.getLogger(__name__)


class GoogleEmailMessageDocumentMetadata(TypedDict):
    """Metadata for Google Email message documents."""

    message_id: str | None
    thread_id: str | None
    subject: str | None
    date: str | None
    source_created_at: str | None
    user_id: str | None
    user_email: str | None
    from_address: str | None
    to_addresses: list[str] | None
    cc_addresses: list[str] | None
    bcc_addresses: list[str] | None
    labels: list[str] | None
    size_estimate: int | None
    internal_date: str | None


@dataclass
class GoogleEmailMessageChunk(BaseChunk[dict[str, Any]]):
    """Represents a chunk of a Google Email message."""

    def get_content(self) -> str:
        """Get the formatted chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> dict[str, Any]:
        """Get chunk-specific metadata."""
        return {
            "message_id": self.raw_data.get("message_id"),
            "thread_id": self.raw_data.get("thread_id"),
            "subject": self.raw_data.get("subject"),
            "date": self.raw_data.get("date"),
            "source_created_at": self.raw_data.get("source_created_at"),
            "user_id": self.raw_data.get("user_id"),
            "user_email": self.raw_data.get("user_email"),
            "from_address": self.raw_data.get("from_address"),
            "to_addresses": self.raw_data.get("to_addresses"),
            "cc_addresses": self.raw_data.get("cc_addresses"),
            "bcc_addresses": self.raw_data.get("bcc_addresses"),
            "labels": self.raw_data.get("labels"),
            "size_estimate": self.raw_data.get("size_estimate"),
            "internal_date": self.raw_data.get("internal_date"),
        }


@dataclass(
    kw_only=True
)  # kw_only to support adding new required fields without breaking default args in BaseDocument
class GoogleEmailMessageDocument(
    BaseDocument[GoogleEmailMessageChunk, GoogleEmailMessageDocumentMetadata]
):
    """Represents a complete Google Email message document."""

    metadata: dict[str, Any]
    raw_data: dict[str, Any]
    source = DocumentSource.GOOGLE_EMAIL

    def get_source_enum(self) -> DocumentSource:
        return self.source

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return "r_google_email_message_" + self.id

    def to_embedding_chunks(self) -> list[GoogleEmailMessageChunk]:
        """Convert document to embedding chunk format using langchain text splitting."""
        full_content = self.get_content()
        if not full_content.strip():
            logger.warning(
                f"Google Email message {self.metadata.get('message_id', 'unknown')} has no content"
            )
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        text_chunks = text_splitter.split_text(full_content)

        logger.info(
            f"Google Email message {self.metadata.get('message_id', 'unknown')} created {len(text_chunks)} chunks from {len(full_content)} characters"
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
                GoogleEmailMessageChunk(
                    document=self,
                    raw_data=chunk_data,
                )
            )

        return embedding_chunks

    def _get_base_chunk_metadata(self) -> dict[str, Any]:
        """Get base metadata that applies to all chunks of this document."""
        return {
            "message_id": self.metadata.get("message_id"),
            "thread_id": self.metadata.get("thread_id"),
            "subject": self.metadata.get("subject"),
            "date": self.metadata.get("date"),
            "source_created_at": self.metadata.get("source_created_at"),
            "user_id": self.metadata.get("user_id"),
            "user_email": self.metadata.get("user_email"),
            "from_address": self.metadata.get("from_address"),
            "to_addresses": self.metadata.get("to_addresses"),
            "cc_addresses": self.metadata.get("cc_addresses"),
            "bcc_addresses": self.metadata.get("bcc_addresses"),
            "labels": self.metadata.get("labels"),
            "size_estimate": self.metadata.get("size_estimate"),
            "internal_date": self.metadata.get("internal_date"),
        }

    def get_content(self) -> str:
        """Get the full document content."""
        return self.raw_data.get("processed_content", "")

    def get_title(self) -> str:
        """Get the document title."""
        return self.raw_data.get("subject", "Untitled")

    def get_url(self) -> str | None:
        """Get the document URL."""
        return None

    def get_metadata(self) -> GoogleEmailMessageDocumentMetadata:
        """Get document-level metadata."""
        return GoogleEmailMessageDocumentMetadata(
            message_id=self.metadata.get("message_id"),
            thread_id=self.metadata.get("thread_id"),
            subject=self.metadata.get("subject"),
            date=self.metadata.get("date"),
            source_created_at=self.metadata.get("source_created_at"),
            user_id=self.metadata.get("user_id"),
            user_email=self.metadata.get("user_email"),
            from_address=self.metadata.get("from_address"),
            to_addresses=self.metadata.get("to_addresses"),
            cc_addresses=self.metadata.get("cc_addresses"),
            bcc_addresses=self.metadata.get("bcc_addresses"),
            labels=self.metadata.get("labels"),
            size_estimate=self.metadata.get("size_estimate"),
            internal_date=self.metadata.get("internal_date"),
        )
