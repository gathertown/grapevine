"""Document classes for custom collection items."""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource


class CustomCollectionChunkMetadata(TypedDict):
    """Metadata for custom collection chunks."""

    collection_name: str
    item_id: str
    # Note: User's metadata fields will be merged in dynamically


class CustomCollectionDocumentMetadata(TypedDict):
    """Metadata for custom collection documents."""

    collection_name: str
    item_id: str
    source: str
    type: str
    source_created_at: str | None
    # Note: User's metadata fields will be merged in dynamically


@dataclass
class CustomCollectionChunk(BaseChunk[CustomCollectionChunkMetadata]):
    """Chunk for custom collection documents.

    Custom collections use single-chunk documents (no splitting).
    """

    def get_content(self) -> str:
        """Return the user-provided content field."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> CustomCollectionChunkMetadata:
        """Return chunk metadata with user fields merged."""
        base_metadata: CustomCollectionChunkMetadata = {
            "collection_name": self.raw_data.get("collection_name", ""),
            "item_id": self.raw_data.get("item_id", ""),
        }

        # Merge user's metadata - mypy accepts this as TypedDict is flexible enough
        user_metadata = self.raw_data.get("user_metadata", {})
        merged: CustomCollectionChunkMetadata = {**base_metadata, **user_metadata}
        return merged


@dataclass
class CustomCollectionDocument(
    BaseDocument[CustomCollectionChunk, CustomCollectionDocumentMetadata]
):
    """Document for custom collection items.

    Custom collections store arbitrary user data with required fields:
    - id: User-defined unique identifier
    - content: Searchable text content
    - metadata: Arbitrary JSON blob
    """

    raw_data: dict[str, Any]

    def get_content(self) -> str:
        """Return the user-provided content field."""
        return self.raw_data.get("content", "")

    def get_source_enum(self) -> DocumentSource:
        """Return the CUSTOM source enum."""
        return DocumentSource.CUSTOM

    def get_metadata(self) -> CustomCollectionDocumentMetadata:
        """Return document metadata with user fields merged."""
        base_metadata: CustomCollectionDocumentMetadata = {
            "collection_name": self.raw_data.get("collection_name", ""),
            "item_id": self.raw_data.get("id", ""),
            "source": self.get_source(),
            "type": "custom_collection_document",
            "source_created_at": self.raw_data.get("source_created_at"),
        }

        # Merge user's metadata - mypy accepts this as TypedDict is flexible enough
        user_metadata = self.raw_data.get("metadata", {})
        merged: CustomCollectionDocumentMetadata = {**base_metadata, **user_metadata}
        return merged

    def to_embedding_chunks(self) -> list[CustomCollectionChunk]:
        """Convert to single chunk (no splitting for custom content).

        Custom collections are treated as atomic units - the entire
        content field is indexed as a single chunk.
        """
        chunk = CustomCollectionChunk(
            document=self,
            raw_data={
                "content": self.raw_data.get("content", ""),
                "collection_name": self.raw_data.get("collection_name", ""),
                "item_id": self.raw_data.get("id", ""),
                "user_metadata": self.raw_data.get("metadata", {}),
            },
        )

        # Populate permissions from document
        self.populate_chunk_permissions(chunk)

        return [chunk]

    def get_header_content(self) -> str:
        """Get formatted header for the document.

        Override to provide collection-specific header.
        """
        collection_name = self.raw_data.get("collection_name", "")
        item_id = self.raw_data.get("id", "")

        # Try to extract a title from metadata if present
        metadata = self.raw_data.get("metadata", {})
        title = metadata.get("title", item_id)

        return f"Collection: {collection_name}\nID: {item_id}\nTitle: {title}"
