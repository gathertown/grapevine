"""Transformer for custom data artifacts."""

from datetime import UTC, datetime
from typing import Any

import asyncpg

from connectors.base import ArtifactEntity, BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.custom_data.custom_data_document import CustomDataDocument
from src.utils.logging import get_logger

logger = get_logger(__name__)


class DataTypeSchema:
    """Schema information for a custom data type."""

    def __init__(
        self,
        display_name: str,
        description: str | None,
        fields: list[dict[str, Any]],
    ):
        self.display_name = display_name
        self.description = description
        self.fields = fields  # List of {name, type, description, required}

    def get_field_description(self, field_name: str) -> str | None:
        """Get the description for a specific field."""
        for field in self.fields:
            if field.get("name") == field_name:
                return field.get("description")
        return None


class CustomDataTransformer(BaseTransformer[CustomDataDocument]):
    """Transformer for custom data artifacts into documents."""

    def __init__(self):
        super().__init__(DocumentSource.CUSTOM_DATA)

    async def _fetch_data_type_schemas(
        self,
        slugs: set[str],
        conn: asyncpg.Connection,
    ) -> dict[str, DataTypeSchema]:
        """Fetch data type schemas for the given slugs.

        Returns a dict mapping slug -> DataTypeSchema.
        """
        if not slugs:
            return {}

        rows = await conn.fetch(
            """
            SELECT slug, display_name, description, custom_fields
            FROM custom_data_types
            WHERE slug = ANY($1::text[]) AND state = 'enabled'
            """,
            list(slugs),
        )

        schemas: dict[str, DataTypeSchema] = {}
        for row in rows:
            custom_fields = row["custom_fields"] or {}
            fields = custom_fields.get("fields", [])
            schemas[row["slug"]] = DataTypeSchema(
                display_name=row["display_name"],
                description=row["description"],
                fields=fields,
            )

        return schemas

    async def transform_artifacts(
        self,
        entity_ids: list[str],
        readonly_db_pool: asyncpg.Pool,
    ) -> list[CustomDataDocument]:
        """Transform custom data artifacts into searchable documents.

        Args:
            entity_ids: List of entity IDs to transform (format: {slug}::{item_id})
            readonly_db_pool: Database connection pool

        Returns:
            List of CustomDataDocument instances
        """

        logger.info(f"Transforming {len(entity_ids)} custom data artifacts")

        async with readonly_db_pool.acquire() as conn:
            # Fetch artifacts from database
            rows = await conn.fetch(
                """
                SELECT entity_id, content, metadata, source_updated_at
                FROM ingest_artifact
                WHERE entity = $1 AND entity_id = ANY($2::text[])
                """,
                ArtifactEntity.CUSTOM_DATA_DOCUMENT.value,
                entity_ids,
            )

            if not rows:
                logger.warning(f"No artifacts found for entity_ids: {entity_ids}")
                return []

            # Extract unique slugs to fetch their schemas
            slugs: set[str] = set()
            for row in rows:
                entity_id = row["entity_id"]
                slug = entity_id.split("::", 1)[0]
                slugs.add(slug)

            # Fetch data type schemas for context
            schemas = await self._fetch_data_type_schemas(slugs, conn)

        documents = []
        for row in rows:
            # Parse entity_id to get slug and item_id
            # Format: {slug}::{item_id}
            entity_id = row["entity_id"]
            slug, item_id = entity_id.split("::", 1)

            # Extract content and metadata from artifact
            artifact_content = row["content"]
            content_text = artifact_content.get("content", "")
            metadata = row["metadata"] or {}

            # Get schema for this data type (if available)
            schema = schemas.get(slug)

            # Build document raw_data
            raw_data = {
                "content": content_text,
                "slug": slug,
                "item_id": item_id,
                "name": metadata.get("name", ""),
                "description": metadata.get("description"),
                "custom_fields": {
                    k: v
                    for k, v in metadata.items()
                    if k not in ("name", "description", "slug", "item_id")
                },
                "source_created_at": row["source_updated_at"].isoformat()
                if row["source_updated_at"]
                else None,
                # Schema context for richer document headers
                "data_type_display_name": schema.display_name if schema else None,
                "data_type_description": schema.description if schema else None,
                "field_schemas": schema.fields if schema else [],
            }

            # Generate document ID: custom_data_{slug}_{item_id}
            document_id = f"custom_data_{slug}_{item_id}"

            # Create document
            # Custom data is uploaded by the tenant and should be accessible to all tenant users
            doc = CustomDataDocument(
                id=document_id,
                raw_data=raw_data,
                source_updated_at=row["source_updated_at"] or datetime.now(UTC),
                permission_policy="tenant",
                permission_allowed_tokens=None,
            )

            documents.append(doc)

            logger.debug(
                "Created document for custom data",
                document_id=document_id,
                slug=slug,
                item_id=item_id,
            )

        logger.info(f"Transformed {len(documents)} custom data documents")
        return documents
