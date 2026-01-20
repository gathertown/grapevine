from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.asana.client.asana_api_models import AsanaTeam, AsanaUser, AsanaWorkspace
from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class AsanaTeamWithUsers(BaseModel):
    team: AsanaTeam
    users: list[AsanaUser]


class AsanaTeamPermissionsArtifactMetadata(BaseModel):
    team_gid: str
    workspace_gid: str


def asana_team_permissions_entity_id(team_gid: str) -> str:
    return f"asana_team_permissions_{team_gid}"


class AsanaTeamPermissionsArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.ASANA_TEAM_PERMISSIONS
    content: AsanaTeamWithUsers
    metadata: AsanaTeamPermissionsArtifactMetadata

    @classmethod
    def from_api_objects(
        cls,
        workspace: AsanaWorkspace,
        team: AsanaTeamWithUsers,
        ingest_job_id: UUID,
    ) -> "AsanaTeamPermissionsArtifact":
        return AsanaTeamPermissionsArtifact(
            entity_id=asana_team_permissions_entity_id(team.team.gid),
            content=team,
            metadata=AsanaTeamPermissionsArtifactMetadata(
                team_gid=team.team.gid,
                workspace_gid=workspace.gid,
            ),
            source_updated_at=datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )
