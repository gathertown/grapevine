from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact
from connectors.clickup.client.clickup_api_models import ClickupTask, ClickupWorkspace


class ClickupTaskArtifactMetadata(BaseModel):
    task_id: str
    task_name: str

    workspace_id: str
    workspace_name: str
    space_id: str
    folder_id: str
    folder_name: str
    list_id: str
    list_name: str

    # epoch milliseconds
    date_created: str
    # epoch milliseconds
    date_updated: str
    # epoch milliseconds
    date_closed: str | None
    # epoch milliseconds
    date_done: str | None


def clickup_task_entity_id(task_id: str) -> str:
    return f"clickup_task_{task_id}"


class ClickupTaskArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.CLICKUP_TASK
    content: ClickupTask
    metadata: ClickupTaskArtifactMetadata

    @classmethod
    def from_api_objects(
        cls,
        task: ClickupTask,
        workspace: ClickupWorkspace,
        ingest_job_id: UUID,
    ) -> "ClickupTaskArtifact":
        meta = ClickupTaskArtifactMetadata(
            task_id=task.id,
            task_name=task.name,
            date_created=task.date_created,
            date_updated=task.date_updated,
            date_closed=task.date_closed,
            date_done=task.date_done,
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            space_id=task.space.id,
            folder_id=task.folder.id,
            folder_name=task.folder.name,
            list_id=task.list.id,
            list_name=task.list.name,
        )

        return ClickupTaskArtifact(
            entity_id=clickup_task_entity_id(task.id),
            content=task,
            metadata=meta,
            # always force an upsert
            source_updated_at=datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )
