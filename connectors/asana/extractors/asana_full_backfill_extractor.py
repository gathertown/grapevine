import asyncio
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.asana.asana_sync_service import AsanaSyncService
from connectors.asana.client.asana_api_errors import AsanaApiPaymentRequiredError
from connectors.asana.client.asana_api_models import AsanaWorkspace
from connectors.asana.client.asana_client import AsanaClient
from connectors.asana.client.asana_client_factory import get_asana_client_for_tenant
from connectors.asana.extractors.artifacts.asana_task_artifact import asana_task_entity_id
from connectors.asana.extractors.asana_task_batch_backfiller import AsanaTaskBatchBackfiller
from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.base.models import BackfillIngestConfig
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class AsanaFullBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["asana_full_backfill"] = "asana_full_backfill"

    # How long the backfill job should run for, SQS visibility timeout is 15 mins, undershoot that a bit
    duration_seconds: int = 60 * 13


class AsanaFullBackfillExtractor(BaseExtractor[AsanaFullBackfillConfig]):
    """
    Extractor to make progress on a full Asana task backfill.
    Make some progress and then enqueue the next job.
    """

    source_name = "asana_full_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: AsanaFullBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)
        logger.info(
            "Started Asana full/progress backfill job",
            backfill_id=backfill_id,
            estimated_duration=config.duration_seconds,
        )

        asana_client = await get_asana_client_for_tenant(config.tenant_id, self.ssm_client)
        artifact_repo = ArtifactRepository(db_pool)

        with LogContext(backfill_id=backfill_id):
            async with asana_client:
                backfiller = FullBackfiller(
                    client=asana_client,
                    db=artifact_repo,
                    service=AsanaSyncService(db_pool),
                    trigger_indexing=trigger_indexing,
                    process_until=datetime.now(UTC) + timedelta(seconds=config.duration_seconds),
                    tenant_id=config.tenant_id,
                    backfill_id=backfill_id,
                    job_id=UUID(job_id),
                    suppress_notification=config.suppress_notification,
                )

                is_complete = await backfiller.backfill_workspaces()
                duration = time.perf_counter() - start_time

                if is_complete:
                    logger.info(
                        "Asana full/progress backfill complete, all workspaces complete no job enqueued",
                        backfill_id=backfill_id,
                        duration=duration,
                    )
                else:
                    logger.info(
                        "Asana full/progress backfill complete, some workspaces incomplete, job enqueued",
                        backfill_id=backfill_id,
                        duration=duration,
                    )

                    # Trigger the same job again, adding backfill_id in case this is the first run
                    await self.sqs_client.send_backfill_ingest_message(
                        backfill_config=AsanaFullBackfillConfig(
                            duration_seconds=config.duration_seconds,
                            backfill_id=backfill_id,
                            tenant_id=config.tenant_id,
                            suppress_notification=config.suppress_notification,
                        )
                    )


class FullBackfiller:
    def __init__(
        self,
        client: AsanaClient,
        db: ArtifactRepository,
        service: AsanaSyncService,
        trigger_indexing: TriggerIndexingCallback,
        process_until: datetime,
        tenant_id: str,
        backfill_id: str,
        job_id: UUID,
        suppress_notification: bool,
    ) -> None:
        self.client = client
        self.db = db
        self.service = service
        self.trigger_indexing = trigger_indexing
        self.process_until = process_until
        self.tenant_id = tenant_id
        self.backfill_id = backfill_id
        self.job_id = job_id
        self.suppress_notification = suppress_notification

        self.task_batch_backfiller = AsanaTaskBatchBackfiller(client=client, db=db, job_id=job_id)

    async def backfill_workspaces(self) -> bool:
        """Attempt to backfill across all workspaces. Returns True if complete, False if time limit hit."""

        tasks: list[asyncio.Task[bool]] = []
        async for workspace_page in self.client.list_workspaces():
            async with asyncio.TaskGroup() as tg:
                tasks.extend(
                    tg.create_task(self._backfill_workspace(workspace))
                    for workspace in workspace_page.data
                )

        return all(task.result() for task in tasks)

    async def _backfill_workspace(self, workspace: AsanaWorkspace) -> bool:
        """Backfill a single Asana workspace. Returns True if complete, False if time limit hit."""

        logger.info(
            "Starting Asana workspace backfill",
            workspace_gid=workspace.gid,
            workspace_name=workspace.name,
        )

        sync_complete = await self.service.is_full_tasks_backfill_complete(workspace.gid)
        if sync_complete:
            logger.info(
                "Skipping Asana workspace backfill, already complete",
                workspace_gid=workspace.gid,
                workspace_name=workspace.name,
            )
            return True

        synced_after = await self.service.get_full_tasks_synced_after(workspace.gid)

        try:
            tasks_processed_count = 0

            async for task_page in self.client.search_tasks(workspace.gid, synced_after):
                batch_result = await self.task_batch_backfiller.get_artifacts(
                    workspace, task_page.data
                )

                # TODO: Maybe batch these across multiple pages
                await self.db.upsert_artifacts_batch(
                    batch_result.task_artifacts + batch_result.secondary_artifacts
                )
                task_entity_ids = [
                    asana_task_entity_id(artifact.content.task.gid)
                    for artifact in batch_result.task_artifacts
                ]
                if task_entity_ids:
                    await self.trigger_indexing(
                        entity_ids=task_entity_ids,
                        source=DocumentSource.ASANA_TASK,
                        tenant_id=self.tenant_id,
                        backfill_id=self.backfill_id,
                        suppress_notification=self.suppress_notification,
                    )
                    tasks_processed_count += len(task_entity_ids)

                # last task will be the earliest modified_at
                if task_page.data:
                    await self.service.set_full_tasks_synced_after(
                        workspace.gid, datetime.fromisoformat(task_page.data[-1].modified_at)
                    )

                # exit early if we're out of time, indicate to caller that we're not complete yet
                if datetime.now(UTC) >= self.process_until:
                    logger.info(
                        "Asana workspace backfill time limit reached, enqueuing another job",
                        workspace_gid=workspace.gid,
                        workspace_name=workspace.name,
                        tasks_processed_count=tasks_processed_count,
                    )
                    return False
        except AsanaApiPaymentRequiredError as e:
            logger.warning(
                "Skipping Asana workspace due to payment required error, search is a premium feature",
                workspace_gid=workspace.gid,
                workspace_name=workspace.name,
                error=str(e),
            )

        logger.info(
            "Completed Asana workspace backfill, marking complete",
            workspace_gid=workspace.gid,
            workspace_name=workspace.name,
        )

        # Made it through all pages of tasks or payment error occurred, mark as complete
        await self.service.set_full_tasks_backfill_complete(workspace.gid, True)
        return True
