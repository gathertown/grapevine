import asyncio
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.base.models import BackfillIngestConfig
from connectors.base.utils.split_even_chunks import split_even_chunks
from connectors.fireflies.client.fireflies_client import FirefliesClient
from connectors.fireflies.client.fireflies_client_factory import get_fireflies_client_for_tenant
from connectors.fireflies.client.fireflies_errors import FirefliesObjectNotFoundException
from connectors.fireflies.client.fireflies_models import (
    FirefliesTranscript,
    GetFirefliesTranscriptsReq,
)
from connectors.fireflies.extractors.artifacts.fireflies_transcript_artifact import (
    FirefliesTranscriptArtifact,
)
from connectors.fireflies.fireflies_sync_service import FirefliesSyncService
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class FirefliesIncrBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["fireflies_incr_backfill"] = "fireflies_incr_backfill"


class FirefliesIncrBackfillExtractor(BaseExtractor[FirefliesIncrBackfillConfig]):
    """
    Extractor to incrementally backfill since last synced. Fallback to getting the last hour.
    """

    source_name = "fireflies_incr_backfill"

    def __init__(self, ssm_client: SSMClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: FirefliesIncrBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)

        logger.info("Started Fireflies incremental backfill job", backfill_id=backfill_id)

        fireflies_client = await get_fireflies_client_for_tenant(config.tenant_id, self.ssm_client)

        backfiller = IncrBackfiller(
            artifact_repo=ArtifactRepository(db_pool),
            client=fireflies_client,
            service=FirefliesSyncService(db_pool),
            config=config,
            job_id=UUID(job_id),
            trigger_indexing=trigger_indexing,
        )

        with LogContext(backfill_id=backfill_id):
            async with fireflies_client:
                await backfiller.backfill()
                duration = time.perf_counter() - start_time
                logger.info("Fireflies incremental backfill complete", duration=duration)


class IncrBackfiller:
    def __init__(
        self,
        artifact_repo: ArtifactRepository,
        client: FirefliesClient,
        service: FirefliesSyncService,
        config: FirefliesIncrBackfillConfig,
        job_id: UUID,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        self.artifact_repo = artifact_repo
        self.api = client
        self.service = service
        self.config = config
        self.job_id = job_id
        self.trigger_indexing = trigger_indexing

    async def backfill(self) -> None:
        await self._backfill_new()
        await self._retry_processing_transcripts()

    async def _backfill_new(self) -> None:
        synced_until = await self.service.get_incr_transcripts_synced_until()
        hour_ago = datetime.now(UTC) - timedelta(hours=1)

        from_date = synced_until + timedelta(milliseconds=1) if synced_until else hour_ago
        req = GetFirefliesTranscriptsReq(from_date=from_date, to_date=None)

        latest_transcript: FirefliesTranscript | None = None
        async for transcripts in self.api.get_transcripts(req):
            if not latest_transcript:
                latest_transcript = transcripts[0]

            await self._persist_batch(transcripts)

        if latest_transcript:
            latest_datetime = datetime.fromisoformat(latest_transcript.date_string)
            await self.service.set_incr_transcripts_synced_until(latest_datetime)

    async def _persist_batch(self, transcripts: list[FirefliesTranscript]) -> None:
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

        logger.info(
            "Incremental Backfilled Fireflies transcripts batch",
            count=len(transcripts),
        )

    async def _retry_processing_transcripts(self) -> None:
        """
        Retry transcripts that are recent and in processing state to try to also get a summary.
        """
        now = datetime.now(UTC)
        six_hours_ago = now - timedelta(hours=6)
        last_six_hours = (six_hours_ago, now)

        processing_transcript_artifacts = await self.artifact_repo.get_artifacts_by_metadata_filter(
            FirefliesTranscriptArtifact,
            metadata_filter={"summary_status": "processing"},
            ranges={"date_string": last_six_hours},
        )

        for batch in split_even_chunks(processing_transcript_artifacts, 10):
            ids = [artifact.metadata.transcript_id for artifact in batch]
            await self._retry_processing_transcripts_batch(ids)

    async def _retry_processing_transcripts_batch(self, transcript_ids: list[str]) -> None:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._get_transcript_fallible(transcript_id))
                for transcript_id in transcript_ids
            ]

        results = [task.result() for task in tasks if task.result()]
        await self._persist_batch([r for r in results if r is not None])

    async def _get_transcript_fallible(self, transcript_id: str) -> FirefliesTranscript | None:
        try:
            return await self.api.get_transcript(transcript_id)
        except FirefliesObjectNotFoundException as e:
            logger.warning("Failed to get Fireflies transcript during retry", error=e)

        return None
