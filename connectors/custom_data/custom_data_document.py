"""Document classes for custom data documents."""

import logging
from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource

logger = logging.getLogger(__name__)

# Chunking configuration - matches standard across connectors
CHUNK_SIZE = 6000
CHUNK_OVERLAP = 100


class CustomDataChunkMetadata(TypedDict):
    """Metadata for custom data chunks."""

    slug: str
    item_id: str
    name: str
    chunk_index: int
    total_chunks: int
    # Note: User's custom fields will be merged in dynamically


class CustomDataDocumentMetadata(TypedDict):
    """Metadata for custom data documents."""

    slug: str
    item_id: str
    name: str
    description: str | None
    source: str
    type: str
    source_created_at: str | None
    # Note: User's custom fields will be merged in dynamically


def _format_custom_field_value(value: Any) -> str:
    """Format a custom field value for display in headers."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


@dataclass
class CustomDataChunk(BaseChunk[CustomDataChunkMetadata]):
    """Chunk for custom data documents.

    Custom data documents may be split into multiple chunks for long content,
    using RecursiveCharacterTextSplitter with overlap for context preservation.
    """

    def get_content(self) -> str:
        """Return chunk content with position context if multi-chunk document."""
        content = self.raw_data.get("content", "")
        chunk_index = self.raw_data.get("chunk_index", 0)
        total_chunks = self.raw_data.get("total_chunks", 1)

        # For single-chunk documents, return content as-is
        if total_chunks == 1:
            return content

        # For multi-chunk documents, add position context
        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> CustomDataChunkMetadata:
        """Return chunk metadata with user fields merged."""
        base_metadata: CustomDataChunkMetadata = {
            "slug": self.raw_data.get("slug", ""),
            "item_id": self.raw_data.get("item_id", ""),
            "name": self.raw_data.get("name", ""),
            "chunk_index": self.raw_data.get("chunk_index", 0),
            "total_chunks": self.raw_data.get("total_chunks", 1),
        }

        # Merge user's custom fields
        custom_fields = self.raw_data.get("custom_fields", {})
        merged: CustomDataChunkMetadata = {**base_metadata, **custom_fields}
        return merged


@dataclass
class CustomDataDocument(BaseDocument[CustomDataChunk, CustomDataDocumentMetadata]):
    """Document for custom data documents.

    Custom data documents store user-defined data with required fields:
    - id: User-defined unique identifier
    - name: Display name
    - content: Searchable text content
    - custom_fields: Arbitrary JSON blob with user-defined schema
    """

    raw_data: dict[str, Any]

    def _get_field_description(self, field_name: str) -> str | None:
        """Get the description for a field from the schema."""
        field_schemas = self.raw_data.get("field_schemas", [])
        for field in field_schemas:
            if field.get("name") == field_name:
                return field.get("description")
        return None

    def get_header_content(self) -> str:
        """Get formatted header for the document including custom fields.

        Builds a structured header with:
        - Data type display name and description (if available)
        - Document name
        - Description (if present)
        - All custom fields with their values and field descriptions
        """
        slug = self.raw_data.get("slug", "")
        name = self.raw_data.get("name", "")
        description = self.raw_data.get("description", "")
        custom_fields = self.raw_data.get("custom_fields", {})

        # Schema context from transformer
        data_type_display_name = self.raw_data.get("data_type_display_name")
        data_type_description = self.raw_data.get("data_type_description")

        lines = []

        # Data type header with display name and description for context
        if data_type_display_name:
            lines.append(f"Data Type: {data_type_display_name}")
            if data_type_description:
                lines.append(f"Data Type Description: {data_type_description}")
        else:
            # Fallback to slug if no display name available
            lines.append(f"Data Type: {slug}")

        # Document name and description
        lines.append(f"Name: {name}")
        if description:
            lines.append(f"Description: {description}")

        # Custom fields - format each field with proper display and include field description
        if custom_fields:
            for field_name, field_value in custom_fields.items():
                formatted_value = _format_custom_field_value(field_value)
                if formatted_value:
                    # Convert field_name from snake_case to Title Case for display
                    display_name = field_name.replace("_", " ").title()
                    field_description = self._get_field_description(field_name)
                    if field_description:
                        # Include field description for better semantic search context
                        lines.append(f"{display_name} ({field_description}): {formatted_value}")
                    else:
                        lines.append(f"{display_name}: {formatted_value}")

        return "\n".join(lines)

    def get_content(self) -> str:
        """Return header + user-provided content for better searchability.

        Combines the structured header (with metadata and custom fields)
        with the user-provided content. This ensures that searches can
        match both the metadata and the actual content.
        """
        header = self.get_header_content()
        content = self.raw_data.get("content", "")

        if header and content:
            return f"{header}\n\nContent:\n{content}"
        return content or header

    def get_source_enum(self) -> DocumentSource:
        """Return the CUSTOM_DATA source enum."""
        return DocumentSource.CUSTOM_DATA

    def get_metadata(self) -> CustomDataDocumentMetadata:
        """Return document metadata with user fields merged."""
        base_metadata: CustomDataDocumentMetadata = {
            "slug": self.raw_data.get("slug", ""),
            "item_id": self.raw_data.get("item_id", ""),
            "name": self.raw_data.get("name", ""),
            "description": self.raw_data.get("description"),
            "source": self.get_source(),
            "type": "custom_data_document",
            "source_created_at": self.raw_data.get("source_created_at"),
        }

        # Merge user's custom fields
        custom_fields = self.raw_data.get("custom_fields", {})
        merged: CustomDataDocumentMetadata = {**base_metadata, **custom_fields}
        return merged

    def to_embedding_chunks(self) -> list[CustomDataChunk]:
        """Convert document to embedding chunks with proper splitting for long content.

        Uses RecursiveCharacterTextSplitter with overlap to split long documents
        into multiple chunks while preserving context. Each chunk includes:
        - Header content (metadata + custom fields) for the first chunk
        - Position context [Part X of Y] for multi-chunk documents
        - Chunk index and total chunks in metadata
        """
        # Get full content (header + user content)
        full_content = self.get_content()

        if not full_content.strip():
            return []

        # Use text splitter for long content
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        text_chunks = text_splitter.split_text(full_content)

        logger.info(
            f"Custom data document {self.id} created {len(text_chunks)} chunks "
            f"from {len(full_content)} characters"
        )

        embedding_chunks: list[CustomDataChunk] = []

        for i, chunk_text in enumerate(text_chunks):
            chunk = CustomDataChunk(
                document=self,
                raw_data={
                    "content": chunk_text,
                    "slug": self.raw_data.get("slug", ""),
                    "item_id": self.raw_data.get("item_id", ""),
                    "name": self.raw_data.get("name", ""),
                    "custom_fields": self.raw_data.get("custom_fields", {}),
                    "chunk_index": i,
                    "total_chunks": len(text_chunks),
                },
            )

            # Populate permissions from document
            self.populate_chunk_permissions(chunk)
            embedding_chunks.append(chunk)

        return embedding_chunks
