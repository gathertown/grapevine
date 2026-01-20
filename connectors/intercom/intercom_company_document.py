"""
Document and chunk definitions for Intercom companies.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_utils import convert_timestamp_to_iso


class IntercomCompanyChunkMetadata(TypedDict, total=False):
    """Metadata stored on each Intercom company chunk."""

    company_id: str | None
    name: str | None
    created_at: str | None
    updated_at: str | None
    chunk_index: int | None
    total_chunks: int | None


class IntercomCompanyDocumentMetadata(TypedDict, total=False):
    """Metadata stored on Intercom company documents."""

    company_id: str
    name: str | None
    website: str | None
    industry: str | None
    plan: str | None
    size: int | None
    custom_attributes: dict[str, Any] | None
    tags: list[str] | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str
    workspace_id: str | None


@dataclass
class IntercomCompanyChunk(BaseChunk[IntercomCompanyChunkMetadata]):
    """Represents a chunk of Intercom company content."""

    def get_content(self) -> str:
        """Return the formatted company content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> IntercomCompanyChunkMetadata:
        return {
            "company_id": self.raw_data.get("company_id"),
            "name": self.raw_data.get("name"),
            "created_at": self.raw_data.get("created_at"),
            "updated_at": self.raw_data.get("updated_at"),
            "chunk_index": self.raw_data.get("chunk_index"),
            "total_chunks": self.raw_data.get("total_chunks"),
        }


@dataclass
class IntercomCompanyDocument(BaseDocument[IntercomCompanyChunk, IntercomCompanyDocumentMetadata]):
    """Structured representation of an Intercom company."""

    raw_data: dict[str, Any]
    metadata: IntercomCompanyDocumentMetadata | None = None
    chunk_class: type[IntercomCompanyChunk] = IntercomCompanyChunk

    def get_content(self) -> str:
        # Build a text representation of the company
        company_data = self.raw_data.get("company_data", self.raw_data)
        parts = []
        if company_data.get("name"):
            parts.append(f"Company Name: {company_data.get('name')}")
        if company_data.get("website"):
            parts.append(f"Website: {company_data.get('website')}")
        if company_data.get("industry"):
            parts.append(f"Industry: {company_data.get('industry')}")
        if company_data.get("plan"):
            parts.append(f"Plan: {company_data.get('plan')}")
        if company_data.get("size"):
            parts.append(f"Size: {company_data.get('size')} employees")
        if company_data.get("description"):
            parts.append(f"Description: {company_data.get('description')}")

        # Add custom attributes if available
        custom_attrs = company_data.get("custom_attributes", {})
        if custom_attrs:
            parts.append("Custom Attributes:")
            for key, value in custom_attrs.items():
                if value:
                    parts.append(f"  {key}: {value}")

        return "\n".join(parts) if parts else "Company information"

    def get_metadata(self) -> IntercomCompanyDocumentMetadata:
        if self.metadata is None:
            company_data = self.raw_data.get("company_data", self.raw_data)

            # Extract tags list
            tags = []
            tags_data = company_data.get("tags", {})
            if isinstance(tags_data, dict):
                tags_list = tags_data.get("data", [])
                if isinstance(tags_list, list):
                    tags = [str(t.get("name", "")) for t in tags_list if t.get("name")]

            return {
                "company_id": company_data.get("id", self.id),
                "name": company_data.get("name"),
                "website": company_data.get("website"),
                "industry": company_data.get("industry"),
                "plan": company_data.get("plan", {}).get("name")
                if isinstance(company_data.get("plan"), dict)
                else company_data.get("plan"),
                "size": company_data.get("size"),
                "custom_attributes": company_data.get("custom_attributes", {}),
                "tags": tags,
                "source_created_at": convert_timestamp_to_iso(company_data.get("created_at")),
                "source_updated_at": convert_timestamp_to_iso(company_data.get("updated_at")),
                "source": DocumentSource.INTERCOM.value,
                "type": "company",
            }
        return self.metadata

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.INTERCOM

    def get_reference_id(self) -> str:
        metadata = self.get_metadata()
        return metadata.get("company_id", self.id)

    def get_header_content(self) -> str:
        metadata = self.get_metadata()
        name = metadata.get("name") or "Unknown Company"
        return f"Company: {name} ({metadata.get('company_id', self.id)})"

    def to_embedding_chunks(self) -> list[IntercomCompanyChunk]:
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
        chunks: list[IntercomCompanyChunk] = []
        total_chunks = len(text_chunks)

        for chunk_idx, chunk_text in enumerate(text_chunks):
            chunk = self.chunk_class(
                document=self,
                raw_data={
                    "company_id": metadata.get("company_id"),
                    "name": metadata.get("name"),
                    "content": chunk_text,
                    "created_at": metadata.get("source_created_at"),
                    "updated_at": metadata.get("source_updated_at"),
                    "chunk_index": chunk_idx,
                    "total_chunks": total_chunks,
                },
            )
            self.populate_chunk_permissions(chunk)
            chunks.append(chunk)

        return chunks
