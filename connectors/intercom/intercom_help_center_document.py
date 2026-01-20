"""
Document and chunk definitions for Intercom Help Center articles.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_utils import convert_timestamp_to_iso


class IntercomHelpCenterArticleChunkMetadata(TypedDict, total=False):
    """Metadata stored on each Intercom Help Center article chunk."""

    article_id: str | None
    section: str
    author_name: str | None
    author_email: str | None
    created_at: str | None
    updated_at: str | None
    chunk_index: int | None
    total_chunks: int | None


class IntercomHelpCenterArticleDocumentMetadata(TypedDict, total=False):
    """Metadata stored on Intercom Help Center article documents."""

    article_id: str | int
    title: str
    state: str | None
    url: str | None
    collection_id: str | int | None
    section_id: str | int | None
    author_id: str | int | None
    author_name: str | None
    author_email: str | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str
    workspace_id: str | None


@dataclass
class IntercomHelpCenterArticleChunk(BaseChunk[IntercomHelpCenterArticleChunkMetadata]):
    """Represents a chunk of Intercom Help Center article content."""

    def get_content(self) -> str:
        return self.raw_data.get("content", "")

    def get_metadata(self) -> IntercomHelpCenterArticleChunkMetadata:
        return {
            "article_id": self.raw_data.get("article_id"),
            "section": self.raw_data.get("section", "body"),
            "author_name": self.raw_data.get("author_name"),
            "author_email": self.raw_data.get("author_email"),
            "created_at": self.raw_data.get("created_at"),
            "updated_at": self.raw_data.get("updated_at"),
            "chunk_index": self.raw_data.get("chunk_index"),
            "total_chunks": self.raw_data.get("total_chunks"),
        }


@dataclass
class IntercomHelpCenterArticleDocument(
    BaseDocument[IntercomHelpCenterArticleChunk, IntercomHelpCenterArticleDocumentMetadata]
):
    """Structured representation of an Intercom Help Center article."""

    raw_data: dict[str, Any]
    metadata: IntercomHelpCenterArticleDocumentMetadata | None = None
    chunk_class: type[IntercomHelpCenterArticleChunk] = IntercomHelpCenterArticleChunk

    def get_content(self) -> str:
        return self.raw_data.get("body", "")

    def get_metadata(self) -> IntercomHelpCenterArticleDocumentMetadata:
        if self.metadata is None:
            return {
                "article_id": self.raw_data.get("article_id", self.id),
                "title": str(self.raw_data.get("title", self.id)),
                "state": self.raw_data.get("state"),
                "url": self.raw_data.get("url"),
                "collection_id": self.raw_data.get("collection_id"),
                "section_id": self.raw_data.get("section_id"),
                "author_id": self.raw_data.get("author_id"),
                "author_name": self.raw_data.get("author_name"),
                "author_email": self.raw_data.get("author_email"),
                "source_created_at": convert_timestamp_to_iso(self.raw_data.get("created_at")),
                "source_updated_at": convert_timestamp_to_iso(self.raw_data.get("updated_at")),
                "source": DocumentSource.INTERCOM.value,
                "type": "help_center_article",
            }
        return self.metadata

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.INTERCOM

    def get_reference_id(self) -> str:
        metadata = self.get_metadata()
        article_id = metadata.get("article_id", self.id)
        return str(article_id)

    def get_header_content(self) -> str:
        metadata = self.get_metadata()
        return f"Article: {metadata.get('title', self.id)}"

    def to_embedding_chunks(self) -> list[IntercomHelpCenterArticleChunk]:
        metadata = self.get_metadata()
        content = self.get_content()

        if not content.strip():
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        text_chunks = text_splitter.split_text(content)
        chunks: list[IntercomHelpCenterArticleChunk] = []
        total_chunks = len(text_chunks)

        for chunk_idx, chunk_text in enumerate(text_chunks):
            chunk = self.chunk_class(
                document=self,
                raw_data={
                    "content": chunk_text,
                    "article_id": metadata.get("article_id"),
                    "section": "body" if total_chunks == 1 else f"body_part{chunk_idx + 1}",
                    "author_name": metadata.get("author_name"),
                    "author_email": metadata.get("author_email"),
                    "created_at": metadata.get("source_created_at"),
                    "updated_at": metadata.get("source_updated_at"),
                    "chunk_index": chunk_idx,
                    "total_chunks": total_chunks,
                },
            )
            self.populate_chunk_permissions(chunk)
            chunks.append(chunk)

        return chunks
