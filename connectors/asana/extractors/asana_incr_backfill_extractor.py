import asyncio
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg
import httpx

from connectors.asana.asana_pruner import AsanaPruner, AsanaPruneResult
from connectors.asana.asana_sync_service import AsanaSyncService
from connectors.asana.client.asana_api_errors import (
    AsanaApiInvalidSyncTokenError,
    AsanaApiServiceAccountOnlyError,
)
from connectors.asana.client.asana_api_models import (
    AsanaEvent,
    AsanaProject,
    AsanaTask,
    AsanaWorkspace,
)
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


@dataclass(frozen=True)
class EventPageResult:
    added_task_gids: set[str]
    deleted_task_gids: set[str]
    updated_task_gids: set[str]


class AsanaIncrBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["asana_incr_backfill"] = "asana_incr_backfill"


class AsanaIncrBackfillExtractor(BaseExtractor[AsanaIncrBackfillConfig]):
    """
    Extractor to incrementally backfill since last sync token. Fallback to getting the last 10 mins
    if fetch with sync token fails (first run or expired).
    """

    source_name = "asana_incr_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: AsanaIncrBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)
        base_config = AsanaIncrBackfillConfig(
            tenant_id=config.tenant_id,
            suppress_notification=config.suppress_notification,
            backfill_id=backfill_id,
        )

        logger.info("Started Asana incremental backfill job", backfill_id=backfill_id)

        asana_client = await get_asana_client_for_tenant(config.tenant_id, self.ssm_client)

        with LogContext(backfill_id=backfill_id):
            async with asana_client:
                backfiller = IncrBackfiller(
                    client=asana_client,
                    db_pool=db_pool,
                    service=AsanaSyncService(db_pool),
                    base_config=base_config,
                    job_id=UUID(job_id),
                    trigger_indexing=trigger_indexing,
                )

                await backfiller.backfill_workspaces()

                duration = time.perf_counter() - start_time
                logger.info("Asana incremental backfill complete", duration=duration)


class IncrBackfiller:
    def __init__(
        self,
        client: AsanaClient,
        db_pool: asyncpg.Pool,
        service: AsanaSyncService,
        base_config: AsanaIncrBackfillConfig,
        job_id: UUID,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        self.client = client
        self.db_pool = db_pool
        self.artifact_repo = ArtifactRepository(db_pool)
        self.service = service
        self.base_config = base_config
        self.task_batch_backfiller = AsanaTaskBatchBackfiller(
            client=client, db=self.artifact_repo, job_id=job_id
        )
        self.trigger_indexing = trigger_indexing

    async def backfill_workspaces(self) -> None:
        async for workspace_page in self.client.list_workspaces():
            async with asyncio.TaskGroup() as tg:
                for workspace in workspace_page.data:
                    tg.create_task(self._backfill_workspace(workspace))

    async def _backfill_workspace(self, workspace: AsanaWorkspace) -> None:
        """Backfill a single Asana workspace. Attempt to use the workspace events endpoint, if only_service_account_can_access, move down to projects."""

        logger.info(
            "Backfilling Asana workspace (incremental)",
            workspace_gid=workspace.gid,
            workspace_name=workspace.name,
        )

        workspace_sync_token = await self.service.get_incr_workspace_sync_token(workspace.gid)

        try:
            sync_token: str | None = None
            all_events: list[AsanaEvent] = []
            async for event_page in self.client.list_workspace_events(
                workspace.gid, workspace_sync_token
            ):
                all_events.extend(event_page.data)
                sync_token = event_page.sync

            await self._handle_events(workspace, all_events)
            if sync_token:
                await self.service.set_incr_workspace_sync_token(workspace.gid, sync_token)

        except AsanaApiInvalidSyncTokenError as e:
            logger.info(
                "Workspace events sync token invalid or expired, falling back to last 10 minutes via search api",
                workspace_gid=workspace.gid,
            )
            await self.service.set_incr_workspace_sync_token(workspace.gid, e.response.sync)

            ten_mins_ago = datetime.now(UTC) - timedelta(minutes=10)
            async for task_page in self.client.search_tasks(
                workspace_gid=workspace.gid, modified_at_after=ten_mins_ago
            ):
                await self._handle_task_page(workspace, task_page.data)

        except AsanaApiServiceAccountOnlyError:
            logger.info(
                "Workspace events not accessible with OAuth token, falling back to project-level incremental backfill",
                workspace_gid=workspace.gid,
            )
            await self._backfill_projects(workspace)

    async def _backfill_projects(self, workspace: AsanaWorkspace) -> None:
        async for project_page in self.client.list_projects(workspace.gid):
            async with asyncio.TaskGroup() as tg:
                for project in project_page.data:
                    tg.create_task(self._backfill_project(workspace, project))

    async def _backfill_project(self, workspace: AsanaWorkspace, project: AsanaProject) -> None:
        logger.info(
            "Backfilling Asana project (incremental)",
            workspace_gid=workspace.gid,
            workspace_name=workspace.name,
            project_gid=project.gid,
            project_name=project.name,
        )

        project_sync_token = await self.service.get_incr_project_sync_token(project.gid)

        try:
            sync_token: str | None = None
            all_events: list[AsanaEvent] = []
            async for event_page in self.client.list_project_events(
                project.gid, project_sync_token
            ):
                all_events.extend(event_page.data)
                sync_token = event_page.sync

            await self._handle_events(workspace, all_events)
            if sync_token:
                await self.service.set_incr_project_sync_token(project.gid, sync_token)

        except AsanaApiInvalidSyncTokenError as e:
            logger.info(
                "Project events sync token invalid or expired, falling back to last 10 minutes via search api",
                project_gid=project.gid,
            )
            await self.service.set_incr_project_sync_token(project.gid, e.response.sync)

            ten_mins_ago = datetime.now(UTC) - timedelta(minutes=10)
            async for task_page in self.client.search_tasks(
                workspace_gid=workspace.gid, project_gid=project.gid, modified_at_after=ten_mins_ago
            ):
                await self._handle_task_page(workspace, task_page.data)

    async def _handle_events(self, workspace: AsanaWorkspace, events: list[AsanaEvent]) -> None:
        result = self._process_events(events)

        # filter out tasks that were both added and deleted in the same set of events
        added_and_deleted_gids = result.added_task_gids.intersection(result.deleted_task_gids)

        refresh_gids = result.added_task_gids.union(result.updated_task_gids).difference(
            added_and_deleted_gids
        )
        delete_gids = result.deleted_task_gids.difference(added_and_deleted_gids)

        async with asyncio.TaskGroup() as tg:
            if refresh_gids:
                tg.create_task(self._refresh_tasks(workspace, list(refresh_gids)))
            if delete_gids:
                tg.create_task(self._delete_tasks(list(delete_gids)))

    def _process_events(self, events: list[AsanaEvent]) -> EventPageResult:
        deleted_task_gids = {
            e.resource.gid
            for e in events
            if e.resource.resource_type == "task" and e.action == "deleted"
        }
        added_task_gids = {
            e.resource.gid
            for e in events
            if e.resource.resource_type == "task" and e.action == "added"
        }
        update_task_gids = {
            e.resource.gid
            for e in events
            if e.resource.resource_type == "task" and e.action != "deleted" and e.action != "added"
        }
        parent_task_gids = {
            e.parent.gid
            for e in events
            if e.parent and e.parent.gid is not None and e.parent.resource_type == "task"
        }

        updated_task_gids = update_task_gids.union(parent_task_gids)

        logger.info(
            "Processed Asana event page",
            added_task_count=len(added_task_gids),
            deleted_task_count=len(deleted_task_gids),
            updated_task_count=len(updated_task_gids),
            total_events=len(events),
        )

        return EventPageResult(
            added_task_gids=added_task_gids,
            deleted_task_gids=deleted_task_gids,
            updated_task_gids=updated_task_gids,
        )

    async def _handle_task_page(self, workspace: AsanaWorkspace, tasks: list[AsanaTask]) -> None:
        result = await self.task_batch_backfiller.get_artifacts(
            workspace=workspace, tasks=tasks, refresh_tasks=True
        )

        await self.artifact_repo.upsert_artifacts_batch(
            result.task_artifacts + result.secondary_artifacts
        )

        task_entity_ids = [
            asana_task_entity_id(artifact.content.task.gid) for artifact in result.task_artifacts
        ]
        if task_entity_ids:
            await self.trigger_indexing(
                entity_ids=task_entity_ids,
                source=DocumentSource.ASANA_TASK,
                tenant_id=self.base_config.tenant_id,
                backfill_id=self.base_config.backfill_id,
                suppress_notification=self.base_config.suppress_notification,
            )

    async def _refresh_tasks(self, workspace: AsanaWorkspace, task_gids: list[str]) -> None:
        tasks = await self._get_tasks_by_gid(task_gids)
        await self._handle_task_page(workspace, tasks)

    async def _get_tasks_by_gid(self, gids: list[str]) -> list[AsanaTask]:
        async with asyncio.TaskGroup() as tg:
            task_tasks: list[asyncio.Task[AsanaTask | None]] = [
                tg.create_task(self._get_task_by_gid_fallible(gid)) for gid in gids
            ]

        results = [task.result() for task in task_tasks]
        return [task for task in results if task is not None]

    # It is very possible for a task to be deleted by the time we try to fetch it here.
    # Incremental syncing is best effort anyways so don't let a single 404 bring down the job.
    async def _get_task_by_gid_fallible(self, gid: str) -> AsanaTask | None:
        try:
            return await self.client.get_task(gid)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == httpx.codes.NOT_FOUND.value:
                logger.warning(f"Asana task {gid} not found (may have been deleted)")
                return None
            if e.response.status_code == httpx.codes.FORBIDDEN.value:
                logger.warning(f"Access forbidden to Asana task {gid} (oauth user may lack access)")
                return None

            raise

    async def _delete_tasks(self, task_gids: list[str]) -> AsanaPruneResult:
        return await AsanaPruner().prune_tasks_by_gid(
            db_pool=self.db_pool,
            tenant_id=self.base_config.tenant_id,
            task_gids=task_gids,
        )
