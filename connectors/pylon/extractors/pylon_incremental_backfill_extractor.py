"""Pylon incremental backfill extractor for syncing recently updated issues."""

import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.base.models import BackfillIngestConfig
from connectors.pylon.client.pylon_client_factory import get_pylon_client_for_tenant
from connectors.pylon.extractors.pylon_artifacts import PylonIssueArtifact
from connectors.pylon.pylon_sync_service import PylonSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class PylonIncrementalBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Pylon incremental backfill job."""

    source: Literal["pylon_incremental_backfill"] = "pylon_incremental_backfill"

    # How far back to look for updated issues (default: 2 hours for some overlap)
    lookback_hours: int = 2


class PylonIncrementalBackfillExtractor(BaseExtractor[PylonIncrementalBackfillConfig]):
    """
    Extractor to sync recently updated Pylon issues.

    This runs periodically (e.g., every 15 minutes) to catch any issues
    that were created or updated since the last sync.
    """

    source_name = "pylon_incremental_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: PylonIncrementalBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = secrets.token_hex(8)
        logger.info(
            "Started Pylon incremental backfill job",
            backfill_id=backfill_id,
            lookback_hours=config.lookback_hours,
        )

        sync_service = PylonSyncService(db_pool)
        artifact_repo = ArtifactRepository(db_pool)

        pylon_client = await get_pylon_client_for_tenant(config.tenant_id, self.ssm_client)

        with LogContext(backfill_id=backfill_id):
            async with pylon_client:
                # Determine the time window
                # Use the last synced time if available, otherwise use lookback_hours
                last_synced_until = await sync_service.get_incr_issues_synced_until()

                if last_synced_until:
                    # Add 1 second overlap to avoid missing updates at boundary
                    start_window = last_synced_until - timedelta(seconds=1)
                else:
                    # First incremental run - look back from now
                    start_window = datetime.now(UTC) - timedelta(hours=config.lookback_hours)

                end_window = datetime.now(UTC)

                logger.info(
                    "Pylon incremental backfill window",
                    start_window=start_window.isoformat(),
                    end_window=end_window.isoformat(),
                )

                # Pylon API requires windows of <= 30 days
                # If incremental sync hasn't run for >30 days, chunk into 30-day windows
                max_window_days = 30
                issues_processed = 0

                # Process in 30-day chunks if needed
                chunk_start = start_window
                while chunk_start < end_window:
                    chunk_end = min(chunk_start + timedelta(days=max_window_days), end_window)

                    logger.info(
                        "Processing incremental chunk",
                        chunk_start=chunk_start.isoformat(),
                        chunk_end=chunk_end.isoformat(),
                    )

                    issues_batch = []
                    async for issue in pylon_client.iterate_issues(
                        start_time=chunk_start,
                        end_time=chunk_end,
                    ):
                        issues_batch.append(issue)

                        # Process in batches of 50
                        if len(issues_batch) >= 50:
                            await self._process_issues_batch(
                                issues_batch=issues_batch,
                                artifact_repo=artifact_repo,
                                trigger_indexing=trigger_indexing,
                                config=config,
                                job_id=UUID(job_id),
                                backfill_id=backfill_id,
                            )
                            issues_processed += len(issues_batch)
                            issues_batch = []

                    # Process remaining issues in this chunk
                    if issues_batch:
                        await self._process_issues_batch(
                            issues_batch=issues_batch,
                            artifact_repo=artifact_repo,
                            trigger_indexing=trigger_indexing,
                            config=config,
                            job_id=UUID(job_id),
                            backfill_id=backfill_id,
                        )
                        issues_processed += len(issues_batch)

                    # Move to next chunk
                    chunk_start = chunk_end

                # Update the sync timestamp
                await sync_service.set_incr_issues_synced_until(end_window)

                duration = time.perf_counter() - start_time
                logger.info(
                    "Pylon incremental backfill complete",
                    backfill_id=backfill_id,
                    issues_processed=issues_processed,
                    duration=duration,
                )

    async def _process_issues_batch(
        self,
        issues_batch: list,
        artifact_repo: ArtifactRepository,
        trigger_indexing: TriggerIndexingCallback,
        config: PylonIncrementalBackfillConfig,
        job_id: UUID,
        backfill_id: str,
    ) -> None:
        """Process a batch of issues."""
        artifacts = [PylonIssueArtifact.from_api_issue(issue, job_id) for issue in issues_batch]

        await artifact_repo.upsert_artifacts_batch(artifacts)

        entity_ids = [a.entity_id for a in artifacts]
        await trigger_indexing(
            entity_ids,
            source=DocumentSource.PYLON_ISSUE,
            tenant_id=config.tenant_id,
            backfill_id=backfill_id,
            suppress_notification=config.suppress_notification,
        )

        logger.info(
            "Processed Pylon incremental issues batch",
            count=len(issues_batch),
        )
