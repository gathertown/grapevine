"""Attio deal backfill extractor."""

import math
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
import requests

from connectors.attio.attio_artifacts import AttioDealArtifact, AttioObjectType
from connectors.attio.attio_models import AttioDealBackfillConfig
from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from src.clients.attio import AttioClient, get_attio_client_for_tenant
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


class AttioDealBackfillExtractor(BaseExtractor[AttioDealBackfillConfig]):
    """Extractor for processing Attio deal backfill batch jobs.

    Each job processes a specific batch of record IDs provided by the root extractor.
    Supports delayed processing via start_timestamp for rate limiting.
    Deals include embedded notes and tasks for richer context.
    """

    source_name = "attio_deal_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: AttioDealBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process a batch of Attio deals for a tenant."""
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
        except requests.exceptions.HTTPError as e:
            # Check if this is a "standard_object_disabled" error
            if self._is_standard_object_disabled_error(e):
                logger.warning(
                    "Deals object is not enabled in this Attio workspace - skipping deals batch",
                    tenant_id=config.tenant_id,
                )
                # Mark backfill as complete even though we skipped
                if config.backfill_id:
                    await increment_backfill_done_ingest_jobs(
                        config.backfill_id, config.tenant_id, 1
                    )
                return
            logger.error(f"Failed to process Attio deals batch: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Failed to process Attio deals batch: {e}", exc_info=True)
            raise
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )

    def _is_standard_object_disabled_error(self, error: requests.exceptions.HTTPError) -> bool:
        """Check if the HTTP error is due to a disabled standard object."""
        try:
            if error.response is not None and error.response.status_code == 400:
                response_json = error.response.json()
                return response_json.get("code") == "standard_object_disabled"
        except Exception:
            pass
        return False

    async def _process_batch(
        self,
        attio_client: AttioClient,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        config: AttioDealBackfillConfig,
    ) -> None:
        """Process a batch of deal records by ID."""
        tenant_id = config.tenant_id
        record_ids = config.record_ids

        logger.info(
            f"Processing batch of {len(record_ids)} Attio deal records",
            tenant_id=tenant_id,
            backfill_id=config.backfill_id,
            include_notes=config.include_notes,
            include_tasks=config.include_tasks,
        )

        artifacts: list[AttioDealArtifact] = []
        entity_ids: list[str] = []

        for record_id in record_ids:
            try:
                record = attio_client.get_record(
                    object_slug=AttioObjectType.DEALS.value,
                    record_id=record_id,
                )

                # Fetch notes and tasks for this deal
                notes: list[dict[str, Any]] = []
                tasks: list[dict[str, Any]] = []

                if config.include_notes:
                    try:
                        notes = attio_client.get_notes_for_record(
                            object_slug=AttioObjectType.DEALS.value,
                            record_id=record_id,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch notes for deal {record_id}: {e}",
                            record_id=record_id,
                        )

                if config.include_tasks:
                    try:
                        tasks = attio_client.get_tasks_for_record(
                            object_slug=AttioObjectType.DEALS.value,
                            record_id=record_id,
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch tasks for deal {record_id}: {e}",
                            record_id=record_id,
                        )

                artifact = AttioDealArtifact.from_api_response(
                    record_data=record,
                    ingest_job_id=UUID(job_id),
                    notes=notes,
                    tasks=tasks,
                )
                artifacts.append(artifact)
                entity_ids.append(artifact.entity_id)

            except Exception as e:
                logger.error(
                    f"Failed to fetch deal record {record_id}: {e}",
                    tenant_id=tenant_id,
                    record_id=record_id,
                )
                continue

        # Store all artifacts in batch
        if artifacts:
            logger.info(f"Storing {len(artifacts)} deal artifacts in batch")
            await self.store_artifacts_batch(db_pool, artifacts)

        # Trigger indexing for all processed records
        if entity_ids:
            logger.info(f"Triggering indexing for {len(entity_ids)} deals")

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
                    DocumentSource.ATTIO_DEAL,
                    tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

        logger.info(
            f"Completed Attio deals batch: {len(artifacts)} processed",
            tenant_id=tenant_id,
            records_processed=len(artifacts),
            records_failed=len(record_ids) - len(artifacts),
        )

        if config.backfill_id:
            await increment_backfill_done_ingest_jobs(config.backfill_id, tenant_id, 1)
