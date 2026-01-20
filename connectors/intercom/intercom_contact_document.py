"""
Document and chunk definitions for Intercom contacts.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_utils import convert_timestamp_to_iso


class IntercomContactChunkMetadata(TypedDict, total=False):
    """Metadata stored on each Intercom contact chunk."""

    contact_id: str | None
    email: str | None
    name: str | None
    role: str | None
    created_at: str | None
    updated_at: str | None
    chunk_index: int | None
    total_chunks: int | None


class IntercomContactDocumentMetadata(TypedDict, total=False):
    """Metadata stored on Intercom contact documents."""

    contact_id: str
    email: str | None
    name: str | None
    role: str | None
    phone: str | None
    location: dict[str, Any] | None
    custom_attributes: dict[str, Any] | None
    companies: list[str] | None
    tags: list[str] | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str
    workspace_id: str | None


@dataclass
class IntercomContactChunk(BaseChunk[IntercomContactChunkMetadata]):
    """Represents a chunk of Intercom contact content."""

    def get_content(self) -> str:
        """Return the formatted contact content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> IntercomContactChunkMetadata:
        return {
            "contact_id": self.raw_data.get("contact_id"),
            "email": self.raw_data.get("email"),
            "name": self.raw_data.get("name"),
            "role": self.raw_data.get("role"),
            "created_at": self.raw_data.get("created_at"),
            "updated_at": self.raw_data.get("updated_at"),
            "chunk_index": self.raw_data.get("chunk_index"),
            "total_chunks": self.raw_data.get("total_chunks"),
        }


@dataclass
class IntercomContactDocument(BaseDocument[IntercomContactChunk, IntercomContactDocumentMetadata]):
    """Structured representation of an Intercom contact."""

    raw_data: dict[str, Any]
    metadata: IntercomContactDocumentMetadata | None = None
    chunk_class: type[IntercomContactChunk] = IntercomContactChunk

    def get_content(self) -> str:
        # Build a text representation of the contact
        contact_data = self.raw_data.get("contact_data", self.raw_data)
        parts = []
        if contact_data.get("name"):
            parts.append(f"Name: {contact_data.get('name')}")
        if contact_data.get("email"):
            parts.append(f"Email: {contact_data.get('email')}")
        if contact_data.get("phone"):
            parts.append(f"Phone: {contact_data.get('phone')}")
        if contact_data.get("role"):
            parts.append(f"Role: {contact_data.get('role')}")
        if contact_data.get("description"):
            parts.append(f"Description: {contact_data.get('description')}")

        # Add custom attributes if available
        custom_attrs = contact_data.get("custom_attributes", {})
        if custom_attrs:
            parts.append("Custom Attributes:")
            for key, value in custom_attrs.items():
                if value:
                    parts.append(f"  {key}: {value}")

        return "\n".join(parts) if parts else "Contact information"

    def get_metadata(self) -> IntercomContactDocumentMetadata:
        if self.metadata is None:
            contact_data = self.raw_data.get("contact_data", self.raw_data)

            # Extract companies list
            companies = []
            companies_data = contact_data.get("companies", {})
            if isinstance(companies_data, dict):
                companies_list = companies_data.get("data", [])
                if isinstance(companies_list, list):
                    companies = [str(c.get("id", "")) for c in companies_list if c.get("id")]

            # Extract tags list
            tags = []
            tags_data = contact_data.get("tags", {})
            if isinstance(tags_data, dict):
                tags_list = tags_data.get("data", [])
                if isinstance(tags_list, list):
                    tags = [str(t.get("name", "")) for t in tags_list if t.get("name")]

            return {
                "contact_id": contact_data.get("id", self.id),
                "email": contact_data.get("email"),
                "name": contact_data.get("name"),
                "role": contact_data.get("role"),
                "phone": contact_data.get("phone"),
                "location": contact_data.get("location"),
                "custom_attributes": contact_data.get("custom_attributes", {}),
                "companies": companies,
                "tags": tags,
                "source_created_at": convert_timestamp_to_iso(contact_data.get("created_at")),
                "source_updated_at": convert_timestamp_to_iso(contact_data.get("updated_at")),
                "source": DocumentSource.INTERCOM.value,
                "type": "contact",
            }
        return self.metadata

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.INTERCOM

    def get_reference_id(self) -> str:
        metadata = self.get_metadata()
        return metadata.get("contact_id", self.id)

    def get_header_content(self) -> str:
        metadata = self.get_metadata()
        name = metadata.get("name") or metadata.get("email") or "Unknown Contact"
        return f"Contact: {name} ({metadata.get('contact_id', self.id)})"

    def to_embedding_chunks(self) -> list[IntercomContactChunk]:
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
        chunks: list[IntercomContactChunk] = []
        total_chunks = len(text_chunks)

        for chunk_idx, chunk_text in enumerate(text_chunks):
            chunk = self.chunk_class(
                document=self,
                raw_data={
                    "contact_id": metadata.get("contact_id"),
                    "name": metadata.get("name"),
                    "email": metadata.get("email"),
                    "role": metadata.get("role"),
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
