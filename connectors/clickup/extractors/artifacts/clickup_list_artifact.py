from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact
from connectors.clickup.client.clickup_api_models import (
    ClickupFolder,
    ClickupList,
    ClickupSpace,
    ClickupUser,
    ClickupWorkspace,
)


class ClickupListArtifactMetadata(BaseModel):
    list_id: str
    list_name: str

    workspace_id: str
    workspace_name: str
    space_id: str
    space_name: str
    folder_id: str
    folder_name: str


class ClickupListArtifactContent(BaseModel):
    members: list[ClickupUser]
    list: ClickupList


def clickup_list_entity_id(list_id: str) -> str:
    return f"clickup_list_{list_id}"


class ClickupListArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.CLICKUP_LIST
    content: ClickupListArtifactContent
    metadata: ClickupListArtifactMetadata

    @classmethod
    def from_api_objects(
        cls,
        lst: ClickupList,
        workspace: ClickupWorkspace,
        space: ClickupSpace,
        folder: ClickupFolder,
        members: list[ClickupUser],
        ingest_job_id: UUID,
    ) -> "ClickupListArtifact":
        content = ClickupListArtifactContent(list=lst, members=members)

        meta = ClickupListArtifactMetadata(
            workspace_id=workspace.id,
            workspace_name=workspace.name,
            space_id=space.id,
            space_name=space.name,
            folder_id=folder.id,
            folder_name=folder.name,
            list_id=lst.id,
            list_name=lst.name,
        )

        return ClickupListArtifact(
            entity_id=clickup_list_entity_id(lst.id),
            content=content,
            metadata=meta,
            # always force an upsert
            source_updated_at=datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )
