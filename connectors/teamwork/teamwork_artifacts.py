"""Teamwork artifact models for ingest pipeline."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import (
    ArtifactEntity,
    BaseIngestArtifact,
    get_teamwork_project_entity_id,
    get_teamwork_task_entity_id,
    get_teamwork_user_entity_id,
)
from connectors.base.utils import parse_iso_timestamp


class TeamworkTaskArtifactContent(BaseModel):
    """Full task data from Teamwork API."""

    task_data: dict[str, Any]
    comments: list[dict[str, Any]] = []


class TeamworkTaskArtifactMetadata(BaseModel):
    """Metadata for Teamwork task artifact."""

    task_id: int
    project_id: int | None = None
    project_name: str | None = None
    task_list_id: int | None = None
    task_list_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TeamworkTaskArtifact(BaseIngestArtifact):
    """Typed Teamwork task artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.TEAMWORK_TASK
    content: TeamworkTaskArtifactContent
    metadata: TeamworkTaskArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        task_data: dict[str, Any],
        ingest_job_id: UUID,
        comments: list[dict[str, Any]] | None = None,
    ) -> "TeamworkTaskArtifact":
        """Create artifact from Teamwork API task response.

        Args:
            task_data: Raw task data from Teamwork API
            ingest_job_id: UUID of the current ingest job
            comments: Optional list of comments attached to the task
        """
        task_id = int(task_data.get("id", 0))

        # Extract project info - can be nested object or ID
        project = task_data.get("project", {})
        if isinstance(project, dict):
            project_id = int(project.get("id", 0)) if project.get("id") else None
            project_name = project.get("name")
        else:
            project_id = int(project) if project else None
            project_name = None

        # Extract task list info
        task_list = task_data.get("taskList", {})
        if isinstance(task_list, dict):
            task_list_id = int(task_list.get("id", 0)) if task_list.get("id") else None
            task_list_name = task_list.get("name")
        else:
            task_list_id = int(task_list) if task_list else None
            task_list_name = None

        # Parse timestamps - Teamwork uses ISO 8601 format
        created_at = task_data.get("createdAt") or task_data.get("created-at")
        updated_at = task_data.get("updatedAt") or task_data.get("updated-at")

        # Determine source_updated_at
        source_updated_at = datetime.now(UTC)
        timestamp_str = updated_at or created_at
        if timestamp_str:
            parsed = parse_iso_timestamp(timestamp_str)
            if parsed:
                source_updated_at = parsed

        return cls(
            entity_id=get_teamwork_task_entity_id(task_id=task_id),
            content=TeamworkTaskArtifactContent(
                task_data=task_data,
                comments=comments or [],
            ),
            metadata=TeamworkTaskArtifactMetadata(
                task_id=task_id,
                project_id=project_id,
                project_name=project_name,
                task_list_id=task_list_id,
                task_list_name=task_list_name,
                created_at=created_at,
                updated_at=updated_at,
            ),
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


class TeamworkProjectArtifactContent(BaseModel):
    """Full project data from Teamwork API."""

    project_data: dict[str, Any]


class TeamworkProjectArtifactMetadata(BaseModel):
    """Metadata for Teamwork project artifact (reference data)."""

    project_id: int
    project_name: str | None = None
    status: str | None = None
    company_id: int | None = None
    company_name: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TeamworkProjectArtifact(BaseIngestArtifact):
    """Typed Teamwork project artifact (reference data for hydration)."""

    entity: ArtifactEntity = ArtifactEntity.TEAMWORK_PROJECT
    content: TeamworkProjectArtifactContent
    metadata: TeamworkProjectArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        project_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> "TeamworkProjectArtifact":
        """Create artifact from Teamwork API project response."""
        project_id = int(project_data.get("id", 0))
        project_name = project_data.get("name")
        status = project_data.get("status")

        # Extract company info
        company = project_data.get("company", {})
        if isinstance(company, dict):
            company_id = int(company.get("id", 0)) if company.get("id") else None
            company_name = company.get("name")
        else:
            company_id = int(company) if company else None
            company_name = None

        created_at = project_data.get("createdAt") or project_data.get("created-at")
        updated_at = project_data.get("updatedAt") or project_data.get("updated-at")

        source_updated_at = datetime.now(UTC)
        timestamp_str = updated_at or created_at
        if timestamp_str:
            parsed = parse_iso_timestamp(timestamp_str)
            if parsed:
                source_updated_at = parsed

        return cls(
            entity_id=get_teamwork_project_entity_id(project_id=project_id),
            content=TeamworkProjectArtifactContent(project_data=project_data),
            metadata=TeamworkProjectArtifactMetadata(
                project_id=project_id,
                project_name=project_name,
                status=status,
                company_id=company_id,
                company_name=company_name,
                created_at=created_at,
                updated_at=updated_at,
            ),
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


class TeamworkUserArtifactContent(BaseModel):
    """Full user data from Teamwork API."""

    user_data: dict[str, Any]


class TeamworkUserArtifactMetadata(BaseModel):
    """Metadata for Teamwork user artifact (reference data)."""

    user_id: int
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None


class TeamworkUserArtifact(BaseIngestArtifact):
    """Typed Teamwork user artifact (reference data for hydration)."""

    entity: ArtifactEntity = ArtifactEntity.TEAMWORK_USER
    content: TeamworkUserArtifactContent
    metadata: TeamworkUserArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        user_data: dict[str, Any],
        ingest_job_id: UUID,
    ) -> "TeamworkUserArtifact":
        """Create artifact from Teamwork API user (person) response."""
        user_id = int(user_data.get("id", 0))
        first_name = user_data.get("firstName") or user_data.get("first-name")
        last_name = user_data.get("lastName") or user_data.get("last-name")
        email = user_data.get("email")

        return cls(
            entity_id=get_teamwork_user_entity_id(user_id=user_id),
            content=TeamworkUserArtifactContent(user_data=user_data),
            metadata=TeamworkUserArtifactMetadata(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                email=email,
            ),
            source_updated_at=datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )
