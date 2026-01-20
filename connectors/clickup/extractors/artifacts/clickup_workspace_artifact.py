from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact
from connectors.clickup.client.clickup_api_models import ClickupWorkspace


class ClickupWorkspaceArtifactMetadata(BaseModel):
    workspace_id: str
    workspace_name: str


def clickup_workspace_entity_id(workspace_id: str) -> str:
    return f"clickup_workspace_{workspace_id}"


class ClickupWorkspaceArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.CLICKUP_WORKSPACE
    content: ClickupWorkspace
    metadata: ClickupWorkspaceArtifactMetadata

    @classmethod
    def from_api_objects(
        cls,
        workspace: ClickupWorkspace,
        ingest_job_id: UUID,
    ) -> "ClickupWorkspaceArtifact":
        meta = ClickupWorkspaceArtifactMetadata(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
        )

        return ClickupWorkspaceArtifact(
            entity_id=clickup_workspace_entity_id(workspace.id),
            content=workspace,
            metadata=meta,
            # always force an upsert
            source_updated_at=datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )
