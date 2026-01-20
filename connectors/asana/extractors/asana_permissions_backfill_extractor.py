import asyncio
import secrets
import time
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.asana.client.asana_api_models import (
    AsanaProject,
    AsanaWorkspace,
)
from connectors.asana.client.asana_client import AsanaClient
from connectors.asana.client.asana_client_factory import get_asana_client_for_tenant
from connectors.asana.extractors.asana_permissions_backfiller import AsanaPermissionBackfiller
from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.models import BackfillIngestConfig
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository, MemoryArtifactCache
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class AsanaPermissionsBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["asana_permissions_backfill"] = "asana_permissions_backfill"


class AsanaPermissionsBackfillExtractor(BaseExtractor[AsanaPermissionsBackfillConfig]):
    """
    Extractor to sync permissions (projects and their memberships)
    """

    source_name = "asana_permissions_backfill"

    def __init__(self, ssm_client: SSMClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: AsanaPermissionsBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)

        logger.info("Started Asana permissions backfill job", backfill_id=backfill_id)

        asana_client = await get_asana_client_for_tenant(config.tenant_id, self.ssm_client)

        with LogContext(backfill_id=backfill_id):
            async with asana_client:
                backfiller = AllPermissionsBackfiller(
                    client=asana_client,
                    db=ArtifactRepository(db_pool),
                    job_id=UUID(job_id),
                )

                await backfiller.backfill_all_permissions()

            duration = time.perf_counter() - start_time
            logger.info("Asana permissions backfill job", duration=duration)


class AllPermissionsBackfiller:
    client: AsanaClient
    db: ArtifactRepository
    job_id: UUID

    def __init__(
        self,
        client: AsanaClient,
        db: ArtifactRepository,
        job_id: UUID,
    ) -> None:
        self.client = client
        self.db = db
        self.job_id = job_id

        self.cache = MemoryArtifactCache()
        self.backfiller = AsanaPermissionBackfiller(
            client=client,
            cache=self.cache,
            job_id=job_id,
        )

    async def backfill_all_permissions(self) -> None:
        async with asyncio.TaskGroup() as tg:
            async for workspace_page in self.client.list_workspaces():
                for workspace in workspace_page.data:
                    tg.create_task(self._backfill_workspace_permissions(workspace))

    async def _backfill_workspace_permissions(self, workspace: AsanaWorkspace) -> None:
        logger.info(
            "Backfilling Asana workspace (permissions)",
            workspace_gid=workspace.gid,
            workspace_name=workspace.name,
        )

        async with asyncio.TaskGroup() as tg:
            async for project_page in self.client.list_projects(workspace.gid):
                tg.create_task(self._backfill_projects_permissions(workspace, project_page.data))

    async def _backfill_projects_permissions(
        self,
        workspace: AsanaWorkspace,
        projects: list[AsanaProject],
    ) -> None:
        results = await self.backfiller.backfill_projects_permissions(workspace, projects)

        self.cache.add_batch(results)
        await self.db.upsert_artifacts_batch(results)
