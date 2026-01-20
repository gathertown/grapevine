"""Transformer for custom collection artifacts."""

from datetime import UTC, datetime

import asyncpg

from connectors.base import ArtifactEntity, BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.custom.custom_collection_document import CustomCollectionDocument
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CustomCollectionTransformer(BaseTransformer[CustomCollectionDocument]):
    """Transformer for custom collection artifacts into documents."""

    def __init__(self):
        super().__init__(DocumentSource.CUSTOM)

    async def transform_artifacts(
        self,
        entity_ids: list[str],
        readonly_db_pool: asyncpg.Pool,
    ) -> list[CustomCollectionDocument]:
        """Transform custom collection artifacts into searchable documents.

        Args:
            entity_ids: List of entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of CustomCollectionDocument instances
        """

        logger.info(f"Transforming {len(entity_ids)} custom collection artifacts")

        # Fetch artifacts from database
        async with readonly_db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT entity_id, content, metadata, source_updated_at
                FROM ingest_artifact
                WHERE entity = $1 AND entity_id = ANY($2::text[])
                """,
                ArtifactEntity.CUSTOM_COLLECTION_ITEM.value,
                entity_ids,
            )

        if not rows:
            logger.warning(f"No artifacts found for entity_ids: {entity_ids}")
            return []

        documents = []
        for row in rows:
            # Parse entity_id to get collection_name and item_id
            # Format: {collection_name}::{item_id}
            entity_id = row["entity_id"]
            collection_name, item_id = entity_id.split("::", 1)

            # Extract content and metadata from artifact
            artifact_content = row["content"]
            content_text = artifact_content.get("content", "")
            user_metadata = row["metadata"] or {}

            # Build document raw_data in the format expected by CustomCollectionDocument
            raw_data = {
                "id": item_id,
                "content": content_text,
                "metadata": user_metadata,
                "collection_name": collection_name,
                "source_created_at": row["source_updated_at"].isoformat()
                if row["source_updated_at"]
                else None,
            }

            # Generate document ID: custom_{collection_name}_{item_id}
            document_id = f"custom_{collection_name}_{item_id}"

            # Create document
            doc = CustomCollectionDocument(
                id=document_id,
                raw_data=raw_data,
                source_updated_at=row["source_updated_at"] or datetime.now(UTC),
                permission_policy="private",
                permission_allowed_tokens=None,
            )

            documents.append(doc)

            logger.debug(
                "Created document for custom collection",
                document_id=document_id,
                collection_name=collection_name,
                item_id=item_id,
            )

        logger.info(f"Transformed {len(documents)} custom collection documents")
        return documents
