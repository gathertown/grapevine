from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.asana.client.asana_api_models import AsanaTask, AsanaWorkspace
from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class AsanaTaskArtifactMetadata(BaseModel):
    task_gid: str
    project_gids: list[str]
    section_gids: list[str]
    workspace_gid: str

    created_at: str
    modified_at: str


class AsanaTaskArtifactContent(BaseModel):
    task: AsanaTask
    workspace: AsanaWorkspace


def asana_task_entity_id(task_gid: str) -> str:
    return f"asana_task_{task_gid}"


class AsanaTaskArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.ASANA_TASK
    content: AsanaTaskArtifactContent
    metadata: AsanaTaskArtifactMetadata

    @classmethod
    def from_api_objects(
        cls, workspace: AsanaWorkspace, task: AsanaTask, ingest_job_id: UUID
    ) -> "AsanaTaskArtifact":
        project_gids = [membership.project.gid for membership in task.memberships]
        section_gids = [membership.section.gid for membership in task.memberships]

        return AsanaTaskArtifact(
            entity_id=asana_task_entity_id(task.gid),
            content=AsanaTaskArtifactContent(task=task, workspace=workspace),
            metadata=AsanaTaskArtifactMetadata(
                task_gid=task.gid,
                project_gids=project_gids,
                section_gids=section_gids,
                workspace_gid=workspace.gid,
                created_at=task.created_at,
                modified_at=task.modified_at,
            ),
            source_updated_at=datetime.fromisoformat(task.modified_at),
            ingest_job_id=ingest_job_id,
        )
