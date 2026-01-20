"""Custom Data Ingest Extractor.

Processes custom data ingest jobs where documents are passed directly in the message payload.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import asyncpg

from connectors.base import BaseExtractor, BaseIngestArtifact, TriggerIndexingCallback
from connectors.base.base_ingest_artifact import ArtifactEntity
from connectors.base.document_source import DocumentSource
from connectors.custom_data.custom_data_models import CustomDataIngestConfig
from src.utils.logging import get_logger

logger = get_logger(__name__)


def get_custom_data_document_entity_id(*, slug: str, item_id: str) -> str:
    """Generate entity ID for custom data document artifacts."""
    return f"{slug}::{item_id}"


class CustomDataIngestExtractor(BaseExtractor[CustomDataIngestConfig]):
    """
    Extractor for custom data ingest jobs.

    Unlike other extractors that fetch data from external APIs, this extractor
    receives document payloads directly in the job configuration and stores them
    as artifacts for indexing.
    """

    source_name = "custom_data_ingest"

    async def process_job(
        self,
        job_id: str,
        config: CustomDataIngestConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process a custom data ingest job.

        Args:
            job_id: The ingest job ID
            config: Job configuration containing documents to ingest
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
        """
        logger.info(
            f"Processing custom data ingest job for slug '{config.slug}' "
            f"with {len(config.documents)} documents",
            slug=config.slug,
            document_count=len(config.documents),
            tenant_id=config.tenant_id,
        )

        if not config.documents:
            logger.info("No documents to process")
            return

        # Convert document payloads to artifacts
        artifacts: list[BaseIngestArtifact] = []
        entity_ids: list[str] = []
        now = datetime.now(UTC)
        ingest_job_id = UUID(job_id) if job_id else uuid4()

        for doc in config.documents:
            # Build entity_id in format: {slug}::{item_id}
            entity_id = get_custom_data_document_entity_id(slug=config.slug, item_id=doc.id)
            entity_ids.append(entity_id)

            # Content structure matches TypeScript: { content: document.content }
            content = {"content": doc.content}

            # Metadata includes all document fields for search and display
            # Matches TypeScript: { name, description, slug, item_id, ...customFields }
            metadata = {
                "name": doc.name,
                "description": doc.description,
                "slug": config.slug,
                "item_id": doc.id,
                **(doc.custom_fields or {}),
            }

            artifact = BaseIngestArtifact(
                entity=ArtifactEntity.CUSTOM_DATA_DOCUMENT,
                entity_id=entity_id,
                ingest_job_id=ingest_job_id,
                content=content,
                metadata=metadata,
                source_updated_at=now,
            )
            artifacts.append(artifact)

        # Store all artifacts in batch
        await self.store_artifacts_batch(db_pool, artifacts)

        logger.info(
            f"Stored {len(entity_ids)} custom data artifacts",
            slug=config.slug,
            entity_count=len(entity_ids),
        )

        # Trigger indexing for all stored documents
        await trigger_indexing(
            entity_ids=entity_ids,
            source=DocumentSource.CUSTOM_DATA,
            tenant_id=config.tenant_id,
            backfill_id=config.backfill_id,
            suppress_notification=config.suppress_notification,
        )

        logger.info(
            f"Triggered indexing for {len(entity_ids)} custom data documents",
            slug=config.slug,
            entity_count=len(entity_ids),
        )
