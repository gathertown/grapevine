"""Incremental backfill extractor for Canva.

Since Canva doesn't support updated_after filtering, we:
1. Fetch the most recently modified designs (sorted by modified_descending)
2. Compare against our last synced timestamp
3. Upsert designs that have been modified since last sync
"""

from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.canva.canva_models import (
    CanvaDesignArtifact,
    CanvaIncrementalBackfillConfig,
)
from connectors.canva.canva_sync_service import CanvaSyncService
from connectors.canva.client import get_canva_client_for_tenant
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CanvaIncrementalBackfillExtractor(BaseExtractor[CanvaIncrementalBackfillConfig]):
    """Extractor for incremental Canva sync.

    Since Canva doesn't support updated_after, this extractor:
    1. Fetches the N most recently modified designs (sorted by modified_descending)
    2. Filters to those modified after our last sync time
    3. Upserts the changed designs
    4. Updates the sync cursor
    """

    source_name = "canva_incremental_backfill"

    async def process_job(
        self,
        job_id: str,
        config: CanvaIncrementalBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        tenant_id = config.tenant_id
        check_count = config.check_count

        logger.info(
            "Starting Canva incremental backfill",
            tenant_id=tenant_id,
            check_count=check_count,
        )

        job_uuid = UUID(job_id)
        repo = ArtifactRepository(db_pool)
        sync_service = CanvaSyncService(db_pool, tenant_id)

        # Get the last sync timestamp
        last_synced = await sync_service.get_designs_synced_until()
        if last_synced is None:
            # If no previous sync, use a default lookback
            last_synced = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            logger.info(
                "No previous sync timestamp, using start of today",
                tenant_id=tenant_id,
                last_synced=last_synced.isoformat(),
            )

        # Convert to Unix timestamp for comparison
        last_synced_timestamp = int(last_synced.timestamp())

        artifacts: list[CanvaDesignArtifact] = []
        entity_ids: list[str] = []
        newest_timestamp: int | None = None
        designs_checked = 0
        designs_modified = 0

        try:
            async with await get_canva_client_for_tenant(tenant_id) as client:
                # Fetch designs sorted by modification time (most recent first)
                async for design in client.iter_all_designs(
                    ownership="any",
                    sort_by="modified_descending",
                ):
                    designs_checked += 1

                    # Track the newest timestamp we see
                    if design.updated_at is not None and (
                        newest_timestamp is None or design.updated_at > newest_timestamp
                    ):
                        newest_timestamp = design.updated_at

                    # Check if design was modified after our last sync
                    design_updated_at = design.updated_at or 0
                    if design_updated_at > last_synced_timestamp:
                        # Fetch detailed design info
                        try:
                            detailed_design = await client.get_design(design.id)
                            artifact = CanvaDesignArtifact.from_api_response(
                                design_data=detailed_design.model_dump(),
                                ingest_job_id=job_uuid,
                            )
                            artifacts.append(artifact)
                            entity_ids.append(artifact.entity_id)
                            designs_modified += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to fetch design {design.id}: {e}",
                                tenant_id=tenant_id,
                                design_id=design.id,
                            )
                    else:
                        # Once we hit designs older than our cursor, we can stop
                        # (since they're sorted by modified_descending)
                        break

                    # Limit how many we check
                    if designs_checked >= check_count:
                        break

        except Exception as e:
            logger.error(f"Failed to get Canva client: {e}", tenant_id=tenant_id)
            raise

        # Save artifacts to database
        if artifacts:
            await repo.upsert_artifacts_batch(artifacts)
            logger.info(
                f"Saved {len(artifacts)} modified Canva design artifacts",
                tenant_id=tenant_id,
            )

            # Trigger indexing
            await trigger_indexing(
                entity_ids,
                DocumentSource.CANVA_DESIGN,
                tenant_id,
            )

        # Update sync cursor to the newest timestamp we saw
        if newest_timestamp is not None:
            new_cursor = datetime.fromtimestamp(newest_timestamp, tz=UTC)
            await sync_service.set_designs_synced_until(new_cursor)
            logger.info(
                "Updated Canva sync cursor",
                tenant_id=tenant_id,
                new_cursor=new_cursor.isoformat(),
            )

        logger.info(
            "Canva incremental backfill complete",
            tenant_id=tenant_id,
            designs_checked=designs_checked,
            designs_modified=designs_modified,
        )
