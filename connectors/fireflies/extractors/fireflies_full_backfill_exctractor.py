import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.base.models import BackfillIngestConfig
from connectors.fireflies.client.fireflies_client import FirefliesClient
from connectors.fireflies.client.fireflies_client_factory import get_fireflies_client_for_tenant
from connectors.fireflies.client.fireflies_models import GetFirefliesTranscriptsReq
from connectors.fireflies.extractors.artifacts.fireflies_transcript_artifact import (
    FirefliesTranscriptArtifact,
)
from connectors.fireflies.fireflies_sync_service import FirefliesSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class FirefliesFullBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["fireflies_full_backfill"] = "fireflies_full_backfill"

    # How long the backfill job should run for, SQS visibility timeout is 15 mins, undershoot that a bit
    duration_seconds: int = 60 * 13


class FirefliesFullBackfillExtractor(BaseExtractor[FirefliesFullBackfillConfig]):
    """
    Extractor to make progress on a full Fireflies transcript backfill.
    Make some progress and then enqueue the next job.
    """

    source_name = "fireflies_full_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: FirefliesFullBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)
        logger.info(
            "Started Fireflies full/progress backfill job",
            backfill_id=backfill_id,
            estimated_duration=config.duration_seconds,
        )

        sync_service = FirefliesSyncService(db_pool)

        is_backfill_complete = await sync_service.get_full_transcripts_backfill_complete()
        if is_backfill_complete:
            logger.info("Fireflies full/progress backfill job already complete, skipping")
            return

        fireflies_client = await get_fireflies_client_for_tenant(config.tenant_id, self.ssm_client)

        sync_service = FirefliesSyncService(db_pool)
        backfiller = FirefliesFullBackfiller(
            artifact_repo=ArtifactRepository(db_pool),
            config=config,
            job_id=UUID(job_id),
            process_until=datetime.now(UTC) + timedelta(seconds=config.duration_seconds),
            trigger_indexing=trigger_indexing,
            service=sync_service,
            api=fireflies_client,
        )

        with LogContext(backfill_id=backfill_id):
            async with fireflies_client:
                is_complete = await backfiller.backfill()

                duration = time.perf_counter() - start_time

                if is_complete:
                    await sync_service.set_full_transcripts_backfill_complete(True)
                    logger.info(
                        "Fireflies full/progress backfill complete, no job enqueued",
                        backfill_id=backfill_id,
                        duration=duration,
                    )
                else:
                    # Trigger the same job again, adding backfill_id in case this is the first run
                    await self.sqs_client.send_backfill_ingest_message(
                        backfill_config=FirefliesFullBackfillConfig(
                            duration_seconds=config.duration_seconds,
                            backfill_id=backfill_id,
                            tenant_id=config.tenant_id,
                            suppress_notification=config.suppress_notification,
                        )
                    )

                    logger.info(
                        "Fireflies full/progress backfill incomplete, job enqueued",
                        backfill_id=backfill_id,
                        duration=duration,
                    )


class FirefliesFullBackfiller:
    def __init__(
        self,
        artifact_repo: ArtifactRepository,
        api: FirefliesClient,
        service: FirefliesSyncService,
        trigger_indexing: TriggerIndexingCallback,
        config: FirefliesFullBackfillConfig,
        job_id: UUID,
        process_until: datetime,
    ) -> None:
        self.artifact_repo = artifact_repo
        self.api = api
        self.service = service
        self.trigger_indexing = trigger_indexing
        self.config = config
        self.job_id = job_id
        self.process_until = process_until

    async def backfill(self) -> bool:
        sync_complete = await self.service.get_full_transcripts_backfill_complete()
        if sync_complete:
            logger.info("Skipping Fireflies transcript backfill, already complete")
            return True

        synced_after = await self.service.get_full_transcripts_synced_after()
        to_date = synced_after - timedelta(milliseconds=1) if synced_after else None
        req = GetFirefliesTranscriptsReq(
            from_date=None,
            to_date=to_date,
        )

        transcripts_processed_count = 0
        async for transcripts in self.api.get_transcripts(req):
            artifacts = [
                FirefliesTranscriptArtifact.from_api_transcript(t, self.job_id) for t in transcripts
            ]

            await self.artifact_repo.upsert_artifacts_batch(artifacts)

            entity_ids = [a.entity_id for a in artifacts]
            await self.trigger_indexing(
                entity_ids,
                source=DocumentSource.FIREFLIES_TRANSCRIPT,
                tenant_id=self.config.tenant_id,
                backfill_id=self.config.backfill_id,
                suppress_notification=self.config.suppress_notification,
            )

            earliest_transcript = transcripts[-1]
            earliest_datetime = datetime.fromisoformat(earliest_transcript.date_string)

            await self.service.set_full_transcripts_synced_after(earliest_datetime)

            logger.info(
                "Backfilled Fireflies transcripts batch",
                count=len(transcripts),
                earliest_transcript_date=earliest_datetime.isoformat(),
            )

            transcripts_processed_count += len(transcripts)

            # exit early if we're out of time, indicate to caller that we're not complete yet
            if datetime.now(UTC) >= self.process_until:
                return False

        return True
