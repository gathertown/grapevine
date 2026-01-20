"""
Abstract base class for Chunk entities.

Provides reusable patterns for processing raw data into structured chunks
across different data sources and entity types.
"""

import hashlib
import json
import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

if TYPE_CHECKING:
    from connectors.base import BaseDocument

from turbopuffer.types import AttributeSchemaParam

from connectors.base.document_source import DocumentSource
from src.permissions.models import PermissionPolicy


def compute_chunk_content_hash(content: str, metadata: Mapping[str, Any]) -> str:
    """Compute a hash of chunk content and metadata for deduplication.

    This hash is used to determine if a chunk has changed and needs re-embedding.
    """
    data = {"content": content, "metadata": dict(metadata)}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def compute_deterministic_chunk_id(document_id: str, unique_key: str) -> uuid.UUID:
    """Generate a deterministic UUID for a chunk based on document_id and a unique key.

    This ensures the same chunk gets the same ID across re-indexing runs,
    allowing us to identify unchanged chunks without re-embedding them.

    Args:
        document_id: The parent document ID
        unique_key: A unique identifier within the document (e.g., message_ts for Slack,
                   block_id for Notion, line number for code, etc.)
    """
    # Use UUID5 with a namespace to generate deterministic UUIDs
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID namespace for URLs
    return uuid.uuid5(namespace, f"{document_id}:{unique_key}")


# Define schema keys as literal type for type safety - we'll reuse this between our schema and
# the BaseChunk method that should match the schema.
TurbopufferChunkKey = Literal[
    "id",
    "document_id",
    "source",
    "vector",
    "content",
    "content_hash",  # Hash of chunk content for incremental indexing
    "metadata",
    "updated_at",
    "source_created_at",
    "slack_channel_id",
    "slack_channel_name",
    "github_repository",
    "linear_team_name",
    "notion_block_ids",
    "permission_policy",
    "permission_allowed_tokens",
]

# Schema definition for chunks in Turbopuffer. All field except `id` are nullable in Turbopuffer.
# This internal schema has stricter typing that needs to be widened below to work with the Turbopuffer client.
_TURBOPUFFER_CHUNK_SCHEMA_INTERNAL: dict[TurbopufferChunkKey, AttributeSchemaParam] = {
    "id": "uuid",
    "document_id": "string",  # Parent document ID
    "source": "string",  # DocumentSource, needed for search filtering
    "vector": {"type": "[3072]f16", "ann": True},  # 3072-dim half-precision float vectors
    # We won't filter on content/metadata in Turbopuffer
    # ---
    "content": {"type": "string", "filterable": False},
    "content_hash": "string",  # Hash of chunk content for incremental indexing deduplication
    "metadata": {
        "type": "string",
        "filterable": False,
    },
    # ---
    "updated_at": "datetime",  # mostly for debug / internal use
    "source_created_at": "datetime",  # needed for search filtering
    # ---
    # Source-specific fields for e.g. provenance search filtering
    "slack_channel_id": "string",
    "slack_channel_name": "string",
    "github_repository": "string",
    "linear_team_name": "string",
    "notion_block_ids": "[]string",
    # ---
    # Permissions fields
    "permission_policy": "string",
    "permission_allowed_tokens": "[]string",
}
# Widen the key typing to work with the Turbopuffer client
TURBOPUFFER_CHUNK_SCHEMA = cast(dict[str, AttributeSchemaParam], _TURBOPUFFER_CHUNK_SCHEMA_INTERNAL)


@dataclass(
    # necessary to allow subclasses to define required fields, since this class has optional ones
    kw_only=True
)
class BaseChunk[ChunkMetadataT: Mapping[str, Any]](ABC):
    """Abstract base class for document chunk entities."""

    # Chunks are always part of a document
    document: "BaseDocument[Any, Any]"

    # Misc data, e.g. to generate `metadata`
    raw_data: Mapping[str, Any]

    # Default to random UUID, but subclasses should override get_unique_key()
    # to enable deterministic IDs for incremental indexing
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    # Optional source-specific fields
    slack_channel_id: str | None = None
    slack_channel_name: str | None = None
    github_repository: str | None = None  # repo name, e.g. "corporate-context"
    linear_team_name: str | None = None
    notion_block_ids: list[str] | None = None

    # Permissions fields
    permission_policy: PermissionPolicy | None = None
    permission_allowed_tokens: list[str] | None = None

    # Cached content hash (computed lazily)
    _content_hash: str | None = field(default=None, repr=False)

    @property
    def document_id(self) -> str:
        """Get the document ID this chunk belongs to."""
        return self.document.id

    @property
    def source(self) -> DocumentSource:
        """Get the DocumentSource for this chunk."""
        return self.document.get_source_enum()

    @property
    def source_created_at(self) -> datetime:
        """Get the source creation datetime from the document."""
        return self.document.get_source_created_at()

    def get_unique_key(self) -> str | None:
        """Get a unique key for this chunk within its document.

        Override this method in subclasses to enable deterministic chunk IDs.
        Return None to use random UUIDs (legacy behavior).

        Examples:
            - Slack: message_ts (timestamp)
            - Notion: block_id
            - Jira: activity_id or "header"
            - Code: file_path:line_start:line_end
        """
        return None

    def get_deterministic_id(self) -> uuid.UUID:
        """Get a deterministic ID for this chunk if possible.

        If get_unique_key() returns a value, generates a deterministic UUID.
        Otherwise, returns the existing (random) ID.
        """
        unique_key = self.get_unique_key()
        if unique_key is not None:
            return compute_deterministic_chunk_id(self.document_id, unique_key)
        return self.id

    def get_content_hash(self) -> str:
        """Get the content hash for this chunk.

        Used for incremental indexing - if the hash hasn't changed,
        we can skip re-embedding this chunk.
        """
        if self._content_hash is None:
            # Use object.__setattr__ to bypass frozen dataclass restriction
            object.__setattr__(
                self,
                "_content_hash",
                compute_chunk_content_hash(self.get_content(), self.get_metadata()),
            )
        return self._content_hash  # type: ignore[return-value]

    def to_turbopuffer_chunk(self, embedding: list[float]) -> dict[str, object]:
        """Convert to a Turbopuffer chunk matching TURBOPUFFER_CHUNK_SCHEMA."""
        # Use deterministic ID if available
        chunk_id = self.get_deterministic_id()

        # First define the chunk with strict key typing
        chunk: dict[TurbopufferChunkKey, object] = {
            "id": str(chunk_id),  # turbopuffer client typing doesn't support uuids
            "document_id": self.document_id,
            "source": self.source,
            "vector": embedding,
            "content": self.get_content(),
            "content_hash": self.get_content_hash(),
            "metadata": json.dumps(self.get_metadata()),  # serialize metadata to JSON string
            "updated_at": datetime.now(UTC).isoformat(),
            "source_created_at": self.source_created_at,
        }

        # Only include optional source-specific fields if they have values
        # to avoid sending null values to Turbopuffer
        if self.slack_channel_id:
            chunk["slack_channel_id"] = self.slack_channel_id
        if self.slack_channel_name:
            chunk["slack_channel_name"] = self.slack_channel_name
        if self.github_repository:
            chunk["github_repository"] = self.github_repository
        if self.linear_team_name:
            chunk["linear_team_name"] = self.linear_team_name
        if self.notion_block_ids:
            chunk["notion_block_ids"] = self.notion_block_ids

        chunk["permission_policy"] = self.permission_policy
        chunk["permission_allowed_tokens"] = self.permission_allowed_tokens

        # Then return with widened key typing to work with the Turbopuffer client
        return cast(dict[str, object], chunk)

    @abstractmethod
    def get_content(self) -> str:
        """Get the text content of this chunk."""
        pass

    @abstractmethod
    def get_metadata(self) -> ChunkMetadataT:
        """Get chunk-specific metadata."""
        pass
