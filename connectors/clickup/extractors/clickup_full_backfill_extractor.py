import asyncio
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.base.models import BackfillIngestConfig
from connectors.base.utils.split_even_chunks import split_even_chunks
from connectors.clickup.clickup_sync_service import ClickupSyncService
from connectors.clickup.client.clickup_api_models import ClickupWorkspace
from connectors.clickup.client.clickup_client import ClickupClient
from connectors.clickup.client.clickup_client_factory import get_clickup_client_for_tenant
from connectors.clickup.extractors.clickup_permissions_backfill_extrator import (
    ClickupPermissionsBackfiller,
)
from connectors.clickup.extractors.clickup_task_batch_artifactor import ClickupTaskBatchArtifactor
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class ClickupFullBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["clickup_full_backfill"] = "clickup_full_backfill"

    # How long the backfill job should run for, SQS visibility timeout is 15 mins, undershoot that a bit
    duration_seconds: int = 60 * 13


class ClickupFullBackfillExtractor(BaseExtractor[ClickupFullBackfillConfig]):
    """
    Extractor to make progress on a full Clickup task backfill.
    Make some progress and then enqueue the next job.
    """

    source_name = "clickup_full_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: ClickupFullBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)
        logger.info(
            "Started Clickup full/progress backfill job",
            backfill_id=backfill_id,
            estimated_duration=config.duration_seconds,
        )

        sync_service = ClickupSyncService(db_pool)
        last_permission_sync_completion = (
            await sync_service.get_permissions_latest_sync_completion()
        )
        is_backfill_complete = await sync_service.get_full_tasks_backfill_complete()
        if is_backfill_complete:
            logger.info("Clickup full/progress backfill job already complete, skipping")
            return

        clickup_client = await get_clickup_client_for_tenant(config.tenant_id, self.ssm_client)
        artifact_repo = ArtifactRepository(db_pool)
        permissions_backfiller = ClickupPermissionsBackfiller(
            api=clickup_client,
            artifact_repo=artifact_repo,
            service=sync_service,
            job_id=UUID(job_id),
        )
        full_backfiller = ClickupFullBackfiller(
            api=clickup_client,
            artifact_repo=artifact_repo,
            service=sync_service,
            trigger_indexing=trigger_indexing,
            process_until=datetime.now(UTC) + timedelta(seconds=config.duration_seconds),
            job_id=UUID(job_id),
            tenant_id=config.tenant_id,
            backfill_id=backfill_id,
            suppress_notification=config.suppress_notification,
        )

        with LogContext(backfill_id=backfill_id):
            async with clickup_client:
                if self._should_backfill_permissions(last_permission_sync_completion):
                    await permissions_backfiller.backfill()

                is_complete = await full_backfiller.backfill()
                duration = time.perf_counter() - start_time

                if is_complete:
                    await sync_service.set_full_tasks_backfill_complete(True)
                    logger.info(
                        "Clickup full/progress backfill complete, all workspaces complete no job enqueued",
                        backfill_id=backfill_id,
                        duration=duration,
                    )
                else:
                    # Trigger the same job again, adding backfill_id in case this is the first run
                    await self.sqs_client.send_backfill_ingest_message(
                        backfill_config=ClickupFullBackfillConfig(
                            duration_seconds=config.duration_seconds,
                            backfill_id=backfill_id,
                            tenant_id=config.tenant_id,
                            suppress_notification=config.suppress_notification,
                        )
                    )
                    logger.info(
                        "Clickup full/progress backfill complete, some workspaces incomplete, job enqueued",
                        backfill_id=backfill_id,
                        duration=duration,
                    )

    def _should_backfill_permissions(self, last_completed: datetime | None) -> bool:
        if not last_completed:
            return True

        eight_days_ago = datetime.now(UTC) - timedelta(days=8)
        return last_completed < eight_days_ago


@dataclass
class ClickupFullBackfiller:
    api: ClickupClient
    artifact_repo: ArtifactRepository
    service: ClickupSyncService
    trigger_indexing: TriggerIndexingCallback
    process_until: datetime
    job_id: UUID
    tenant_id: str
    backfill_id: str
    suppress_notification: bool

    async def backfill(self) -> bool:
        workspaces = await self.api.get_authorized_workspaces()

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._backfill_workspace(workspace)) for workspace in workspaces
            ]

        return all(task.result() for task in tasks)

    async def _backfill_workspace(self, workspace: ClickupWorkspace) -> bool:
        task_batch_artifactor = ClickupTaskBatchArtifactor(
            api=self.api,
            artifact_repo=self.artifact_repo,
            job_id=self.job_id,
        )

        synced_after = await self.service.get_full_tasks_synced_after(workspace.id)
        async for tasks in self.api.get_tasks(workspace.id, updated_lte=synced_after):
            artifact_result = await task_batch_artifactor.get_artifacts(workspace, tasks)

            for artifact_chunk in split_even_chunks(artifact_result.all_artifacts(), 1000):
                await self.artifact_repo.upsert_artifacts_batch(artifact_chunk)

            entity_ids = [artifact.entity_id for artifact in artifact_result.task_artifacts]
            await self.trigger_indexing(
                entity_ids=entity_ids,
                source=DocumentSource.CLICKUP_TASK,
                tenant_id=self.tenant_id,
                backfill_id=self.backfill_id,
                suppress_notification=self.suppress_notification,
            )

            # update synced after to the oldest task's updated_at
            oldest_task = tasks[-1]
            updated_ms = int(oldest_task.date_updated)
            updated_s = updated_ms / 1000.0
            updated_dt = datetime.fromtimestamp(updated_s, UTC)
            # one extra millisecond to avoid re-processing the same task. The actual API uses
            # numeric pagination so this is really unlikely to miss tasks
            synced_after = updated_dt - timedelta(milliseconds=1)
            await self.service.set_full_tasks_synced_after(workspace.id, synced_after)

            # exit early if we're out of time, indicate to caller that we're not complete yet
            if datetime.now(UTC) >= self.process_until:
                return False

        return True
