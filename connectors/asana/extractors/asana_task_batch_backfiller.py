import asyncio
from dataclasses import dataclass
from uuid import UUID

from connectors.asana.client.asana_api_models import (
    AsanaTask,
    AsanaWorkspace,
    dedupe_asana_resources,
)
from connectors.asana.client.asana_client import AsanaClient
from connectors.asana.extractors.artifacts.asana_story_artifact import AsanaStoryArtifact
from connectors.asana.extractors.artifacts.asana_task_artifact import (
    AsanaTaskArtifact,
    asana_task_entity_id,
)
from connectors.asana.extractors.asana_permissions_backfill_extractor import (
    AsanaPermissionBackfiller,
)
from connectors.base.base_ingest_artifact import BaseIngestArtifact
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TaskBatchArtifacts:
    task_artifacts: list[AsanaTaskArtifact]
    secondary_artifacts: list[BaseIngestArtifact]


@dataclass
class AsanaTaskBatchBackfiller:
    def __init__(
        self,
        client: AsanaClient,
        db: ArtifactRepository,
        job_id: UUID,
    ) -> None:
        self.client = client
        self.db = db
        self.job_id = job_id

        self.permissions_backfiller = AsanaPermissionBackfiller(
            client=client,
            cache=db,
            job_id=job_id,
        )

    async def get_artifacts(
        self, workspace: AsanaWorkspace, tasks: list[AsanaTask], refresh_tasks: bool = False
    ) -> TaskBatchArtifacts:
        """
        Get artifacts for a batch of tasks.
        Use existing artifacts to skip already backfilled tasks UNLESS refresh_tasks is True.
        Permissions artifacts (projects, teams) are always cached / skipped when possible. They are
        refreshed on a separate schedule.
        """

        logger.info(
            "Asana Getting artifacts for task batch",
            task_count=len(tasks),
            refresh_tasks=refresh_tasks,
        )

        if refresh_tasks:
            new_tasks = tasks
        else:
            entity_ids = [asana_task_entity_id(task.gid) for task in tasks]
            existing = await self.db.get_artifacts_by_entity_ids(AsanaTaskArtifact, entity_ids)
            existing_gids = {artifact.content.task.gid for artifact in existing}

            new_tasks = [task for task in tasks if task.gid not in existing_gids]

        if not new_tasks:
            return TaskBatchArtifacts(task_artifacts=[], secondary_artifacts=[])

        # collect all the projects and backfill project permissions
        projects = [membership.project for task in new_tasks for membership in task.memberships]
        unique_projects = dedupe_asana_resources(projects)

        logger.info(
            "Asana Getting permission and story artifacts for task batch",
            task_count=len(tasks),
            refresh_tasks=refresh_tasks,
            project_count=len(unique_projects),
        )

        async with asyncio.TaskGroup() as tg:
            project_permissions_task = tg.create_task(
                self.permissions_backfiller.backfill_projects_permissions(
                    workspace, unique_projects
                )
            )
            story_tasks: list[asyncio.Task[list[BaseIngestArtifact]]] = [
                tg.create_task(self._backfill_task_stories(task.gid)) for task in new_tasks
            ]

            secondary_artifact_tasks = [project_permissions_task] + story_tasks

        task_artifacts = [
            AsanaTaskArtifact.from_api_objects(
                workspace=workspace, task=task, ingest_job_id=self.job_id
            )
            for task in new_tasks
        ]
        secondary_artifacts = [t for task in secondary_artifact_tasks for t in task.result()]

        return TaskBatchArtifacts(
            task_artifacts=task_artifacts, secondary_artifacts=secondary_artifacts
        )

    async def _backfill_task_stories(self, task_gid: str) -> list[BaseIngestArtifact]:
        artifacts = list[BaseIngestArtifact]()

        async for story_page in self.client.list_stories(task_gid):
            artifacts.extend(
                [
                    AsanaStoryArtifact.from_api_story(story, task_gid, ingest_job_id=self.job_id)
                    for story in story_page.data
                ]
            )

        return artifacts
