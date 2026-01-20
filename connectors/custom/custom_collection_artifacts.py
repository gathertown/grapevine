"""Custom collection artifact models."""

from typing import Any

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class CustomCollectionItemArtifactContent(BaseModel):
    """Content for custom collection item artifacts.

    Stores just the text content to be embedded.
    """

    content: str


class CustomCollectionItemArtifact(BaseIngestArtifact):
    """Typed custom collection item artifact with validated content and metadata.

    The metadata field stores the user's arbitrary metadata directly.
    Collection name and item ID can be derived from entity_id if needed.
    """

    entity: ArtifactEntity = ArtifactEntity.CUSTOM_COLLECTION_ITEM
    content: CustomCollectionItemArtifactContent
    metadata: dict[str, Any]
