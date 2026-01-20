"""Attio company backfill extractor."""

import math
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.attio.attio_artifacts import AttioCompanyArtifact, AttioObjectType
from connectors.attio.attio_models import AttioCompanyBackfillConfig
from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from src.clients.attio import get_attio_client_for_tenant
from src.clients.sqs import cap_sqs_visibility_timeout
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.logging import get_logger
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = get_logger(__name__)


class AttioCompanyBackfillExtractor(BaseExtractor[AttioCompanyBackfillConfig]):
    """Extractor for processing Attio company backfill batch jobs.

    Each job processes a specific batch of record IDs provided by the root extractor.
    Supports delayed processing via start_timestamp for rate limiting.
    """

    source_name = "attio_company_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: AttioCompanyBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process a batch of Attio companies for a tenant."""
        # Check if we should start processing yet (for rate limiting)
        if config.start_timestamp:
            current_time = datetime.now(UTC)
            if current_time < config.start_timestamp:
                # Not time to start yet - extend visibility timeout until start_timestamp
                delay_seconds = cap_sqs_visibility_timeout(
                    3 + int((config.start_timestamp - current_time).total_seconds())
                )

                logger.info(
                    f"Delaying batch processing until {config.start_timestamp.isoformat()} "
                    f"(current time: {current_time.isoformat()}, delay: {delay_seconds}s)"
                )

                raise ExtendVisibilityException(
                    visibility_timeout_seconds=delay_seconds,
                    message=f"Delaying processing until {config.start_timestamp.isoformat()}",
                )

        try:
            attio_client = await get_attio_client_for_tenant(config.tenant_id, self.ssm_client)
            await self._process_batch(
                attio_client=attio_client,
                db_pool=db_pool,
                job_id=job_id,
                trigger_indexing=trigger_indexing,
                config=config,
            )
        except ExtendVisibilityException:
            raise
        except Exception as e:
            logger.error(f"Failed to process Attio companies batch: {e}", exc_info=True)
            raise
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )

    async def _process_batch(
        self,
        attio_client,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        config: AttioCompanyBackfillConfig,
    ) -> None:
        """Process a batch of company records by ID."""
        tenant_id = config.tenant_id
        record_ids = config.record_ids

        logger.info(
            f"Processing batch of {len(record_ids)} Attio company records",
            tenant_id=tenant_id,
            backfill_id=config.backfill_id,
        )

        artifacts: list[AttioCompanyArtifact] = []
        entity_ids: list[str] = []

        for record_id in record_ids:
            try:
                record = attio_client.get_record(
                    object_slug=AttioObjectType.COMPANIES.value,
                    record_id=record_id,
                )

                artifact = AttioCompanyArtifact.from_api_response(
                    record_data=record,
                    ingest_job_id=UUID(job_id),
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

            except Exception as e:
                logger.error(
                    f"Failed to fetch company record {record_id}: {e}",
                    tenant_id=tenant_id,
                    record_id=record_id,
                )
                continue

        # Store all artifacts in batch
        if artifacts:
            logger.info(f"Storing {len(artifacts)} company artifacts in batch")
            await self.store_artifacts_batch(db_pool, artifacts)

        # Trigger indexing for all processed records
        if entity_ids:
            logger.info(f"Triggering indexing for {len(entity_ids)} companies")

            # Calculate total number of index batches and track them upfront
            total_index_batches = math.ceil(len(entity_ids) / DEFAULT_INDEX_BATCH_SIZE)
            if config.backfill_id and total_index_batches > 0:
                await increment_backfill_total_index_jobs(
                    config.backfill_id, tenant_id, total_index_batches
                )

            for i in range(0, len(entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch = entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    DocumentSource.ATTIO_COMPANY,
                    tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

        logger.info(
            f"Completed Attio companies batch: {len(artifacts)} processed",
            tenant_id=tenant_id,
            records_processed=len(artifacts),
            records_failed=len(record_ids) - len(artifacts),
        )

        if config.backfill_id:
            await increment_backfill_done_ingest_jobs(config.backfill_id, tenant_id, 1)
