"""Extractor for custom collection webhooks."""

from datetime import UTC, datetime
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from connectors.base import (
    BaseExtractor,
    TriggerIndexingCallback,
    get_custom_collection_item_entity_id,
)
from connectors.base.document_source import DocumentSource
from connectors.custom.custom_collection_artifacts import (
    CustomCollectionItemArtifact,
    CustomCollectionItemArtifactContent,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CustomCollectionWebhookConfig(BaseModel):
    """Configuration for custom collection webhook processing."""

    body: dict
    tenant_id: str


class CustomCollectionExtractor(BaseExtractor[CustomCollectionWebhookConfig]):
    """Extractor for custom collection webhook events."""

    source_name = "custom_collection"

    async def process_job(
        self,
        job_id: str,
        config: CustomCollectionWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process custom collection webhook.

        Args:
            job_id: Ingest job ID
            config: Webhook configuration with payload
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
        """
        payload = config.body
        tenant_id = config.tenant_id

        # Extract fields
        collection_name = payload["collection_name"]
        item_id = payload["id"]

        logger.info(
            "Processing custom collection item",
            collection_name=collection_name,
            item_id=item_id,
        )

        # Generate entity ID
        entity_id = get_custom_collection_item_entity_id(
            collection_name=collection_name,
            item_id=item_id,
        )

        # Parse timestamp
        source_updated_at = datetime.now(UTC)
        if "source_created_at" in payload:
            try:
                source_updated_at = datetime.fromisoformat(
                    payload["source_created_at"].replace("Z", "+00:00")
                )
            except (ValueError, AttributeError):
                logger.warning("Invalid source_created_at, using current time")

        # Extract content and metadata from payload
        content_text = payload["content"]
        user_metadata = payload.get("metadata", {})

        # Create artifact with simplified structure
        artifact = CustomCollectionItemArtifact(
            entity_id=entity_id,
            ingest_job_id=UUID(job_id),
            content=CustomCollectionItemArtifactContent(content=content_text),
            metadata=user_metadata,  # User's metadata directly at artifact level
            source_updated_at=source_updated_at,
        )

        # Store artifact
        await self.store_artifact(db_pool, artifact)

        logger.info(f"Stored custom collection artifact: {entity_id}")

        # Trigger indexing
        await trigger_indexing(
            entity_ids=[entity_id],
            source=DocumentSource.CUSTOM,
            tenant_id=tenant_id,
        )
