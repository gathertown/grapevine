from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact
from connectors.clickup.client.clickup_api_models import (
    ClickupComment,
    ClickupTask,
    ClickupWorkspace,
)


class ClickupCommentArtifactMetadata(BaseModel):
    comment_id: str
    # epoch milliseconds
    date: str

    workspace_id: str
    workspace_name: str
    space_id: str
    folder_id: str
    folder_name: str
    list_id: str
    list_name: str
    task_id: str
    task_name: str
    parent_comment_id: str | None


def clickup_comment_entity_id(comment_id: str) -> str:
    return f"clickup_comment_{comment_id}"


class ClickupCommentArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.CLICKUP_COMMENT
    content: ClickupComment
    metadata: ClickupCommentArtifactMetadata

    @classmethod
    def from_api_objects(
        cls,
        comment: ClickupComment,
        parent: ClickupComment | None,
        task: ClickupTask,
        workspace: ClickupWorkspace,
        ingest_job_id: UUID,
    ) -> "ClickupCommentArtifact":
        meta = ClickupCommentArtifactMetadata(
            comment_id=comment.id,
            date=comment.date,
            parent_comment_id=parent.id if parent else None,
            task_id=task.id,
            task_name=task.name,
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            space_id=task.space.id,
            folder_id=task.folder.id,
            folder_name=task.folder.name,
            list_id=task.list.id,
            list_name=task.list.name,
        )

        return ClickupCommentArtifact(
            entity_id=clickup_comment_entity_id(comment.id),
            content=comment,
            metadata=meta,
            # always force an upsert
            source_updated_at=datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )
