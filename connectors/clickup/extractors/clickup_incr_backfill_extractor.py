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
from connectors.clickup.extractors.clickup_task_batch_artifactor import ClickupTaskBatchArtifactor
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class ClickupIncrBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["clickup_incr_backfill"] = "clickup_incr_backfill"


class ClickupIncrBackfillExtractor(BaseExtractor[ClickupIncrBackfillConfig]):
    """
    Extractor to incrementally update Clickup tasks updated since some time.
    """

    source_name = "clickup_incr_backfill"

    def __init__(self, ssm_client: SSMClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: ClickupIncrBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)
        logger.info(
            "Started Clickup incremental backfill job",
            backfill_id=backfill_id,
        )

        clickup_client = await get_clickup_client_for_tenant(config.tenant_id, self.ssm_client)

        backfiller = ClickupIncrBackfiller(
            api=clickup_client,
            artifact_repo=ArtifactRepository(db_pool),
            service=ClickupSyncService(db_pool),
            trigger_indexing=trigger_indexing,
            job_id=UUID(job_id),
            tenant_id=config.tenant_id,
            backfill_id=backfill_id,
            suppress_notification=config.suppress_notification,
        )

        with LogContext(backfill_id=backfill_id):
            async with clickup_client:
                await backfiller.backfill()

                duration = time.perf_counter() - start_time
                logger.info(
                    "Clickup incremental backfill complete",
                    backfill_id=backfill_id,
                    duration=duration,
                )


@dataclass
class ClickupIncrBackfiller:
    api: ClickupClient
    artifact_repo: ArtifactRepository
    service: ClickupSyncService
    trigger_indexing: TriggerIndexingCallback
    job_id: UUID
    tenant_id: str
    backfill_id: str
    suppress_notification: bool

    async def backfill(self) -> None:
        workspaces = await self.api.get_authorized_workspaces()

        async with asyncio.TaskGroup() as tg:
            for workspace in workspaces:
                tg.create_task(self._backfill_workspace(workspace))

    async def _backfill_workspace(self, workspace: ClickupWorkspace) -> None:
        task_batch_artifactor = ClickupTaskBatchArtifactor(
            api=self.api,
            artifact_repo=self.artifact_repo,
            job_id=self.job_id,
        )

        synced_until = await self.service.get_incr_tasks_synced_until(workspace.id)
        async for tasks in self.api.get_tasks(workspace.id, updated_gte=synced_until, reverse=True):
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

            # update synced after to the newst task's updated_at
            newest_task = tasks[-1]
            updated_ms = int(newest_task.date_updated)
            updated_s = updated_ms / 1000.0
            updated_dt = datetime.fromtimestamp(updated_s, UTC)
            # one extra millisecond to avoid re-processing the same task. The actual API uses
            # numeric pagination so this is really unlikely to miss tasks
            synced_until = updated_dt + timedelta(milliseconds=1)
            await self.service.set_incr_tasks_synced_until(workspace.id, synced_until)
