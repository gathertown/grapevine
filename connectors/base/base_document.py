"""
Abstract base class for Document entities.

Provides reusable patterns for processing raw data into structured documents
across different data sources and entity types.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from connectors.base import BaseChunk
from connectors.base.document_source import DocumentSource
from src.permissions.models import PermissionPolicy
from src.permissions.utils import is_valid_permission_token
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class BaseDocument[
    ChunkT: BaseChunk[Any],
    MetadataT: Mapping[str, Any],
](ABC):
    """Abstract base class for structured document entities."""

    id: str
    source_updated_at: datetime

    # Permissions fields
    permission_policy: PermissionPolicy
    permission_allowed_tokens: list[str] | None

    def __post_init__(self) -> None:
        if not self.permission_allowed_tokens:
            return

        for token in self.permission_allowed_tokens:
            if not is_valid_permission_token(token):
                raise ValueError(
                    f"BaseDocument: Invalid permission_allowed_tokens token provided: {token}"
                )

    @abstractmethod
    def to_embedding_chunks(self) -> list[ChunkT]:
        """Convert document to embedding chunk format."""
        pass

    @abstractmethod
    def get_content(self) -> str:
        """Get the full document content."""
        pass

    @abstractmethod
    def get_source_enum(self) -> DocumentSource:
        pass

    def get_source(self) -> str:
        """Get the source identifier string for this document."""
        return self.get_source_enum().value

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return ""

    @abstractmethod
    def get_metadata(self) -> MetadataT:
        """Get document metadata. Override in subclasses for custom metadata."""
        pass

    def get_header_content(self) -> str:
        """Get the formatted header section of the document.
        Override in subclasses to provide document-specific header formatting.
        """
        return ""

    def populate_chunk_permissions(self, chunk: ChunkT) -> None:
        """Populate chunk with document's permission information.

        Args:
            chunk: The chunk to populate with permissions
        """
        chunk.permission_policy = self.permission_policy
        chunk.permission_allowed_tokens = self.permission_allowed_tokens

    # TODO: ideally this would be inverted, where each document's impl of source_created_at lives in this
    # method and metadata relies on that method to populate its source_created_at, instead of the other way around.
    # Things are this way right now for legacy reasons: we originally had metadata define source_created_at inline.
    def get_source_created_at(self) -> datetime:
        """Extract and parse source_created_at from document metadata."""
        metadata = self.get_metadata()
        source_created_at = datetime.now(UTC)

        # Handle dict-like metadata
        if metadata.get("source_created_at"):
            source_created_at_str = metadata["source_created_at"]
            try:
                if isinstance(source_created_at_str, str):
                    source_created_at = datetime.fromisoformat(
                        source_created_at_str.replace("Z", "+00:00")
                    )
                else:
                    source_created_at = source_created_at_str
                logger.debug(f"Using document's source_created_at: {source_created_at}")
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to parse source_created_at '{source_created_at_str}': {e}, using current time"
                )
                source_created_at = datetime.now(UTC)
        else:
            logger.warning("Document missing source_created_at, using current time")
        return source_created_at
