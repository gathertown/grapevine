import asyncio
from dataclasses import dataclass
from uuid import UUID

from connectors.asana.client.asana_api_models import (
    AsanaProject,
    AsanaTeam,
    AsanaUser,
    AsanaWorkspace,
)
from connectors.asana.client.asana_client import AsanaClient
from connectors.asana.client.asana_permissions_models import AsanaTeamMembership
from connectors.asana.extractors.artifacts.asana_project_artifact import (
    AsanaProjectPermissionsArtifact,
    asana_project_permissions_entity_id,
)
from connectors.asana.extractors.artifacts.asana_team_artifact import (
    AsanaTeamPermissionsArtifact,
    AsanaTeamWithUsers,
    asana_team_permissions_entity_id,
)
from connectors.base.base_ingest_artifact import BaseIngestArtifact
from src.ingest.repositories.artifact_repository import ArtifactCache
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AsanaPermissionBackfiller:
    client: AsanaClient
    cache: ArtifactCache
    job_id: UUID

    async def backfill_projects_permissions(
        self, workspace: AsanaWorkspace, projects: list[AsanaProject]
    ) -> list[BaseIngestArtifact]:
        entity_ids = [asana_project_permissions_entity_id(project.gid) for project in projects]
        existing = await self.cache.get_artifacts_by_entity_ids(
            AsanaProjectPermissionsArtifact, entity_ids
        )
        existing_gids = {artifact.content.project.gid for artifact in existing}

        new_projects = [project for project in projects if project.gid not in existing_gids]

        logger.info(
            "Asana Backfilling permissions for new projects",
            new_projects_count=len(new_projects),
            existing_projects_count=len(existing_gids),
        )

        async with asyncio.TaskGroup() as tg:
            project_tasks = [
                tg.create_task(self._backfill_project_permissions(workspace, project))
                for project in new_projects
            ]

        return [artifact for task in project_tasks for artifact in task.result()]

    async def _backfill_project_permissions(
        self, workspace: AsanaWorkspace, project: AsanaProject
    ) -> list[BaseIngestArtifact]:
        all_users = list[AsanaUser]()

        all_existing_teams = list[AsanaTeamWithUsers]()
        all_new_teams = list[AsanaTeamWithUsers]()

        async for membership_page in self.client.list_project_memberships(project.gid):
            users = [
                membership.member
                for membership in membership_page.data
                if isinstance(membership.member, AsanaUser)
            ]
            all_users.extend(users)

            teams = [
                membership.member
                for membership in membership_page.data
                if isinstance(membership.member, AsanaTeam)
            ]

            team_entity_ids = [asana_team_permissions_entity_id(team.gid) for team in teams]
            existing_team_artifacts = await self.cache.get_artifacts_by_entity_ids(
                AsanaTeamPermissionsArtifact, team_entity_ids
            )
            all_existing_teams.extend(artifact.content for artifact in existing_team_artifacts)

            existing_team_gids = {artifact.content.team.gid for artifact in existing_team_artifacts}
            new_teams = [team for team in teams if team.gid not in existing_team_gids]

            logger.info(
                "Asana Backfilling permissions for new project (membership page)",
                project_gid=project.gid,
                project_name=project.name,
                new_teams_count=len(new_teams),
                existing_teams_count=len(existing_team_gids),
                users_count=len(users),
            )

            async with asyncio.TaskGroup() as tg:
                team_backfill_tasks = [
                    tg.create_task(self._backfill_team(team)) for team in new_teams
                ]
            all_new_teams.extend(task.result() for task in team_backfill_tasks)

        all_teams = all_existing_teams + all_new_teams

        new_permission_artifact = AsanaProjectPermissionsArtifact.from_api_objects(
            workspace=workspace,
            project=project,
            users=all_users,
            teams=all_teams,
            ingest_job_id=self.job_id,
        )

        new_team_artifacts: list[BaseIngestArtifact] = [
            AsanaTeamPermissionsArtifact.from_api_objects(
                workspace, team, ingest_job_id=self.job_id
            )
            for team in all_new_teams
        ]

        return [new_permission_artifact] + new_team_artifacts

    async def _backfill_team(self, team: AsanaTeam) -> AsanaTeamWithUsers:
        memberships = list[AsanaTeamMembership]()

        async for membership_page in self.client.list_team_memberships(team.gid):
            memberships.extend(membership_page.data)

        return AsanaTeamWithUsers(
            team=team,
            users=[membership.user for membership in memberships],
        )
