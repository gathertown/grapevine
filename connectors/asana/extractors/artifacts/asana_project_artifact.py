from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.asana.client.asana_api_models import AsanaProject, AsanaUser, AsanaWorkspace
from connectors.asana.extractors.artifacts.asana_team_artifact import AsanaTeamWithUsers
from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class AsanaProjectPermissionsArtifactMetadata(BaseModel):
    project_gid: str
    workspace_gid: str


class AsanaProjectPermissionsArtifactContent(BaseModel):
    project: AsanaProject
    users: list[AsanaUser]
    teams: list[AsanaTeamWithUsers]

    def get_all_users(self) -> list[AsanaUser]:
        user_map: dict[str, AsanaUser] = {user.gid: user for user in self.users}

        for team_with_users in self.teams:
            for user in team_with_users.users:
                user_map[user.gid] = user

        return list(user_map.values())


def asana_project_permissions_entity_id(project_gid: str) -> str:
    return f"asana_project_permissions_{project_gid}"


class AsanaProjectPermissionsArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.ASANA_PROJECT_PERMISSIONS
    content: AsanaProjectPermissionsArtifactContent
    metadata: AsanaProjectPermissionsArtifactMetadata

    @classmethod
    def from_api_objects(
        cls,
        workspace: AsanaWorkspace,
        project: AsanaProject,
        users: list[AsanaUser],
        teams: list[AsanaTeamWithUsers],
        ingest_job_id: UUID,
    ) -> "AsanaProjectPermissionsArtifact":
        return AsanaProjectPermissionsArtifact(
            entity_id=asana_project_permissions_entity_id(project.gid),
            content=AsanaProjectPermissionsArtifactContent(
                project=project,
                users=users,
                teams=teams,
            ),
            metadata=AsanaProjectPermissionsArtifactMetadata(
                project_gid=project.gid,
                workspace_gid=workspace.gid,
            ),
            # Sadly teams do not have an updated_at field so we just need to update every time. The
            # Asana connector does a decent job at only updating when things change anyway.
            source_updated_at=datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )
