"""Design backfill extractor for processing batches of Canva designs."""

from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.canva.canva_models import (
    CanvaDesignArtifact,
    CanvaDesignBackfillConfig,
)
from connectors.canva.client import get_canva_client_for_tenant
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_done_ingest_jobs

logger = get_logger(__name__)


class CanvaDesignBackfillExtractor(BaseExtractor[CanvaDesignBackfillConfig]):
    """Extractor for processing batches of Canva design IDs.

    Fetches design details for each ID in the batch and creates artifacts.
    """

    source_name = "canva_design_backfill"

    async def process_job(
        self,
        job_id: str,
        config: CanvaDesignBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        tenant_id = config.tenant_id
        design_ids = config.design_ids
        backfill_id = config.backfill_id

        logger.info(
            "Starting Canva design batch backfill",
            tenant_id=tenant_id,
            design_count=len(design_ids),
            backfill_id=backfill_id,
        )

        job_uuid = UUID(job_id)
        repo = ArtifactRepository(db_pool)
        artifacts: list[CanvaDesignArtifact] = []
        entity_ids: list[str] = []

        try:
            async with await get_canva_client_for_tenant(tenant_id) as client:
                for design_id in design_ids:
                    try:
                        # Get detailed design info
                        design = await client.get_design(design_id)

                        # Create artifact from API response
                        artifact = CanvaDesignArtifact.from_api_response(
                            design_data=design.model_dump(),
                            ingest_job_id=job_uuid,
                        )
                        artifacts.append(artifact)
                        entity_ids.append(artifact.entity_id)

                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch design {design_id}: {e}",
                            tenant_id=tenant_id,
                            design_id=design_id,
                        )
                        continue

        except Exception as e:
            logger.error(f"Failed to get Canva client: {e}", tenant_id=tenant_id)
            raise

        # Save artifacts to database
        if artifacts:
            await repo.upsert_artifacts_batch(artifacts)
            logger.info(
                f"Saved {len(artifacts)} Canva design artifacts",
                tenant_id=tenant_id,
            )

            # Trigger indexing for the design documents
            await trigger_indexing(
                entity_ids,
                DocumentSource.CANVA_DESIGN,
                tenant_id,
                backfill_id,
                config.suppress_notification,
            )

        # Track backfill progress (even if no artifacts, to mark job as done)
        if backfill_id:
            await increment_backfill_done_ingest_jobs(backfill_id, tenant_id)

            # Check if all jobs are done and mark backfill complete
            # This is typically handled by the backfill progress tracker

        logger.info(
            "Canva design batch backfill complete",
            tenant_id=tenant_id,
            designs_processed=len(artifacts),
            designs_requested=len(design_ids),
            backfill_id=backfill_id,
        )
