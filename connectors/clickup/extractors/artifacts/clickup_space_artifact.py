from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact
from connectors.clickup.client.clickup_api_models import ClickupSpace, ClickupWorkspace


class ClickupSpaceArtifactMetadata(BaseModel):
    space_id: str
    space_name: str

    workspace_id: str
    workspace_name: str


def clickup_space_entity_id(space_id: str) -> str:
    return f"clickup_space_{space_id}"


class ClickupSpaceArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.CLICKUP_SPACE
    content: ClickupSpace
    metadata: ClickupSpaceArtifactMetadata

    @classmethod
    def from_api_objects(
        cls,
        workspace: ClickupWorkspace,
        space: ClickupSpace,
        ingest_job_id: UUID,
    ) -> "ClickupSpaceArtifact":
        meta = ClickupSpaceArtifactMetadata(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            space_id=space.id,
            space_name=space.name,
        )

        return ClickupSpaceArtifact(
            entity_id=clickup_space_entity_id(space.id),
            content=space,
            metadata=meta,
            # always force an upsert
            source_updated_at=datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )
