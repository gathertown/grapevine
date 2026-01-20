import asyncio
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.base_ingest_artifact import BaseIngestArtifact
from connectors.base.models import BackfillIngestConfig
from connectors.clickup.clickup_sync_service import ClickupSyncService
from connectors.clickup.client.clickup_api_models import (
    ClickupListWithFolder,
    ClickupSpace,
    ClickupWorkspace,
)
from connectors.clickup.client.clickup_client import ClickupClient
from connectors.clickup.client.clickup_client_factory import get_clickup_client_for_tenant
from connectors.clickup.extractors.artifacts.clickup_list_artifact import ClickupListArtifact
from connectors.clickup.extractors.artifacts.clickup_space_artifact import ClickupSpaceArtifact
from connectors.clickup.extractors.artifacts.clickup_workspace_artifact import (
    ClickupWorkspaceArtifact,
)
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class ClickupPermissionsBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["clickup_permissions_backfill"] = "clickup_permissions_backfill"


class ClickupPermissionsBackfillExtractor(BaseExtractor[ClickupPermissionsBackfillConfig]):
    """
    Extractor to make update all the lists in Clickup to have correct permissions.
    """

    source_name = "clickup_permissions_backfill"

    def __init__(self, ssm_client: SSMClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: ClickupPermissionsBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)
        logger.info(
            "Started Clickup permissions backfill job",
            backfill_id=backfill_id,
        )

        clickup_client = await get_clickup_client_for_tenant(config.tenant_id, self.ssm_client)
        backfiller = ClickupPermissionsBackfiller(
            api=clickup_client,
            artifact_repo=ArtifactRepository(db_pool),
            service=ClickupSyncService(db_pool),
            job_id=UUID(job_id),
        )

        with LogContext(backfill_id=backfill_id):
            async with clickup_client:
                await backfiller.backfill()

                duration = time.perf_counter() - start_time
                logger.info(
                    "Clickup permissions backfill complete",
                    backfill_id=backfill_id,
                    duration=duration,
                )


@dataclass
class ClickupPermissionsBackfiller:
    api: ClickupClient
    artifact_repo: ArtifactRepository
    service: ClickupSyncService
    job_id: UUID

    async def backfill(self) -> None:
        workspaces = await self.api.get_authorized_workspaces()

        async with asyncio.TaskGroup() as tg:
            for workspace in workspaces:
                tg.create_task(self._backfill_workspace(workspace))

        await self.service.set_permissions_latest_sync_completion(datetime.now(UTC))

    async def _backfill_workspace(self, workspace: ClickupWorkspace) -> None:
        spaces = await self.api.get_spaces(workspace.id)
        async with asyncio.TaskGroup() as tg:
            for space in spaces:
                tg.create_task(self._backfill_space(workspace, space))

    async def _backfill_space(self, workspace: ClickupWorkspace, space: ClickupSpace) -> None:
        lists = await self.api.get_lists(space.id)

        async with asyncio.TaskGroup() as tg:
            artifact_tasks = [
                tg.create_task(self._get_list_artifacts(workspace, space, lst)) for lst in lists
            ]

        workspace_artifact: BaseIngestArtifact = ClickupWorkspaceArtifact.from_api_objects(
            workspace=workspace,
            ingest_job_id=self.job_id,
        )
        space_artifact: BaseIngestArtifact = ClickupSpaceArtifact.from_api_objects(
            workspace=workspace,
            space=space,
            ingest_job_id=self.job_id,
        )
        list_artifacts: list[BaseIngestArtifact] = [task.result() for task in artifact_tasks]
        all_artifacts = list_artifacts + [space_artifact, workspace_artifact]
        await self.artifact_repo.upsert_artifacts_batch(all_artifacts)

    async def _get_list_artifacts(
        self, workspace: ClickupWorkspace, space: ClickupSpace, lst: ClickupListWithFolder
    ) -> ClickupListArtifact:
        members = await self.api.get_list_members(lst.id)

        return ClickupListArtifact.from_api_objects(
            lst=lst.to_list(),
            workspace=workspace,
            space=space,
            folder=lst.folder,
            members=members,
            ingest_job_id=self.job_id,
        )
