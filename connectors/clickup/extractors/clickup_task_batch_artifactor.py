import asyncio
from dataclasses import dataclass
from uuid import UUID

from connectors.base.base_ingest_artifact import BaseIngestArtifact
from connectors.clickup.client.clickup_api_models import (
    ClickupComment,
    ClickupSpace,
    ClickupTask,
    ClickupWorkspace,
)
from connectors.clickup.client.clickup_client import ClickupClient
from connectors.clickup.extractors.artifacts.clickup_comment_artifact import ClickupCommentArtifact
from connectors.clickup.extractors.artifacts.clickup_list_artifact import (
    ClickupListArtifact,
    clickup_list_entity_id,
)
from connectors.clickup.extractors.artifacts.clickup_space_artifact import (
    ClickupSpaceArtifact,
    clickup_space_entity_id,
)
from connectors.clickup.extractors.artifacts.clickup_task_artifact import ClickupTaskArtifact
from connectors.clickup.extractors.artifacts.clickup_workspace_artifact import (
    ClickupWorkspaceArtifact,
)
from src.ingest.repositories.artifact_repository import ArtifactRepository


@dataclass
class TaskBatchArtifacts:
    task_artifacts: list[ClickupTaskArtifact]
    comment_artifacts: list[ClickupCommentArtifact]
    list_artifacts: list[ClickupListArtifact]
    space_artifacts: list[ClickupSpaceArtifact]
    workspace_artifact: ClickupWorkspaceArtifact | None

    def all_artifacts(self) -> list[BaseIngestArtifact]:
        artifacts: list[BaseIngestArtifact] = []
        artifacts.extend(self.task_artifacts)
        artifacts.extend(self.comment_artifacts)
        artifacts.extend(self.list_artifacts)
        artifacts.extend(self.space_artifacts)

        if self.workspace_artifact:
            artifacts.append(self.workspace_artifact)

        return artifacts


@dataclass
class PermissionsArtifacts:
    list_artifacts: list[ClickupListArtifact]
    space_artifacts: list[ClickupSpaceArtifact]
    workspace_artifact: ClickupWorkspaceArtifact | None


@dataclass
class ClickupTaskBatchArtifactor:
    api: ClickupClient
    artifact_repo: ArtifactRepository
    job_id: UUID

    async def get_artifacts(
        self, workspace: ClickupWorkspace, tasks: list[ClickupTask]
    ) -> TaskBatchArtifacts:
        task_artifacts = [
            ClickupTaskArtifact.from_api_objects(
                workspace=workspace,
                task=task,
                ingest_job_id=self.job_id,
            )
            for task in tasks
        ]

        async with asyncio.TaskGroup() as tg:
            permission_artifacts_task = tg.create_task(
                self._get_permissions_artifacts_batch(workspace, tasks)
            )
            comment_artifacts_task = tg.create_task(
                self._get_comment_artifacts_batch(workspace, tasks)
            )

        return TaskBatchArtifacts(
            task_artifacts=task_artifacts,
            comment_artifacts=comment_artifacts_task.result(),
            list_artifacts=permission_artifacts_task.result().list_artifacts,
            space_artifacts=permission_artifacts_task.result().space_artifacts,
            workspace_artifact=permission_artifacts_task.result().workspace_artifact,
        )

    async def _get_permissions_artifacts_batch(
        self, workspace: ClickupWorkspace, tasks: list[ClickupTask]
    ) -> PermissionsArtifacts:
        """Get list and space artifacts for a batch of tasks, in most cases these will already exist."""

        list_entity_ids = {clickup_list_entity_id(task.list.id) for task in tasks}
        existing_list_artifacts = await self.artifact_repo.get_artifacts_by_entity_ids(
            ClickupListArtifact, list(list_entity_ids)
        )
        existing_list_ids = {artifact.content.list.id for artifact in existing_list_artifacts}
        new_list_ids = {task.list.id for task in tasks if task.list.id not in existing_list_ids}
        if not new_list_ids:
            return PermissionsArtifacts(
                list_artifacts=[],
                space_artifacts=[],
                workspace_artifact=None,
            )

        space_entity_ids = {clickup_space_entity_id(task.space.id) for task in tasks}
        existing_space_artifacts = await self.artifact_repo.get_artifacts_by_entity_ids(
            ClickupSpaceArtifact, list(space_entity_ids)
        )
        existing_space_ids = {artifact.content.id for artifact in existing_space_artifacts}
        new_space_ids = {task.space.id for task in tasks if task.space.id not in existing_space_ids}

        async with asyncio.TaskGroup() as tg:
            space_tasks = [
                tg.create_task(self.api.get_space(space_id)) for space_id in new_space_ids
            ]

        new_spaces = [task.result() for task in space_tasks]
        new_space_artifacts = [
            ClickupSpaceArtifact.from_api_objects(
                workspace=workspace,
                space=space,
                ingest_job_id=self.job_id,
            )
            for space in new_spaces
        ]

        space_by_id: dict[str, ClickupSpace] = {}
        for artifact in existing_space_artifacts:
            space_by_id[artifact.content.id] = artifact.content
        for artifact in new_space_artifacts:
            space_by_id[artifact.content.id] = artifact.content

        # single task per list is enough to populate list info
        tasks_by_new_list_id = {
            task.list.id: task for task in tasks if task.list.id not in existing_list_ids
        }
        one_task_per_new_list = list(tasks_by_new_list_id.values())

        new_spaces = [space_by_id[task.space.id] for task in one_task_per_new_list]
        new_folders = [task.folder for task in one_task_per_new_list]
        new_lists = [task.list for task in one_task_per_new_list]

        async with asyncio.TaskGroup() as tg:
            new_members_tasks = [
                tg.create_task(self.api.get_list_members(task.list.id))
                for task in one_task_per_new_list
            ]

        new_members = [task.result() for task in new_members_tasks]

        new_list_artifacts = [
            ClickupListArtifact.from_api_objects(
                lst=lst,
                workspace=workspace,
                space=space,
                folder=folder,
                members=members,
                ingest_job_id=self.job_id,
            )
            for lst, space, folder, members in zip(
                new_lists, new_spaces, new_folders, new_members, strict=True
            )
        ]

        return PermissionsArtifacts(
            list_artifacts=new_list_artifacts,
            space_artifacts=new_space_artifacts,
            workspace_artifact=ClickupWorkspaceArtifact.from_api_objects(
                workspace=workspace,
                ingest_job_id=self.job_id,
            ),
        )

    async def _get_comment_artifacts_batch(
        self, workspace: ClickupWorkspace, tasks: list[ClickupTask]
    ) -> list[ClickupCommentArtifact]:
        async with asyncio.TaskGroup() as tg:
            comment_tasks = [
                tg.create_task(self._get_comment_artifacts(workspace, task)) for task in tasks
            ]

        return [comment for task in comment_tasks for comment in task.result()]

    async def _get_comment_artifacts(
        self, workspace: ClickupWorkspace, task: ClickupTask
    ) -> list[ClickupCommentArtifact]:
        comment_artifact_tasks: list[asyncio.Task[list[ClickupCommentArtifact]]] = []
        async for comments in self.api.get_task_comments(task.id):
            async with asyncio.TaskGroup() as tg:
                comment_artifact_tasks.extend(
                    [
                        tg.create_task(
                            self._get_comment_and_reply_artifacts(workspace, task, comment)
                        )
                        for comment in comments
                    ]
                )

        return [artifact for task in comment_artifact_tasks for artifact in task.result()]

    async def _get_comment_and_reply_artifacts(
        self, workspace: ClickupWorkspace, task: ClickupTask, comment: ClickupComment
    ) -> list[ClickupCommentArtifact]:
        artifacts = [
            ClickupCommentArtifact.from_api_objects(
                workspace=workspace,
                task=task,
                comment=comment,
                ingest_job_id=self.job_id,
                parent=None,
            )
        ]

        if comment.reply_count > 0:
            reply_artifacts = await self._get_comment_replies_artifacts(workspace, task, comment)
            artifacts.extend(reply_artifacts)

        return artifacts

    async def _get_comment_replies_artifacts(
        self, workspace: ClickupWorkspace, task: ClickupTask, parent_comment: ClickupComment
    ) -> list[ClickupCommentArtifact]:
        replies = await self.api.get_comment_replies(parent_comment.id)

        return [
            ClickupCommentArtifact.from_api_objects(
                workspace=workspace,
                task=task,
                comment=reply,
                ingest_job_id=self.job_id,
                parent=parent_comment,
            )
            for reply in replies
        ]
