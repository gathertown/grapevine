"""Pylon artifact definitions for ingestion."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact
from connectors.pylon.client.pylon_models import (
    PylonAccount,
    PylonContact,
    PylonIssue,
    PylonTeam,
    PylonUser,
)


# Entity ID generators
def pylon_issue_entity_id(issue_id: str) -> str:
    return f"pylon_issue_{issue_id}"


def pylon_account_entity_id(account_id: str) -> str:
    return f"pylon_account_{account_id}"


def pylon_contact_entity_id(contact_id: str) -> str:
    return f"pylon_contact_{contact_id}"


def pylon_user_entity_id(user_id: str) -> str:
    return f"pylon_user_{user_id}"


def pylon_team_entity_id(team_id: str) -> str:
    return f"pylon_team_{team_id}"


# Artifact metadata classes
class PylonIssueArtifactMetadata(BaseModel):
    """Metadata for Pylon issue artifacts."""

    issue_id: str
    issue_number: int | None
    state: str | None
    priority: str | None
    account_id: str | None
    requester_id: str | None
    requester_email: str | None
    assignee_id: str | None
    team_id: str | None
    created_at: str | None
    updated_at: str | None

    @classmethod
    def from_api_issue(cls, issue: PylonIssue) -> "PylonIssueArtifactMetadata":
        return PylonIssueArtifactMetadata(
            issue_id=issue.id,
            issue_number=issue.number,
            state=issue.state,
            priority=issue.priority,
            account_id=issue.account.id if issue.account else None,
            requester_id=issue.requester.id if issue.requester else None,
            requester_email=issue.requester.email if issue.requester else None,
            assignee_id=issue.assignee.id if issue.assignee else None,
            team_id=issue.team.id if issue.team else None,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
        )


class PylonAccountArtifactMetadata(BaseModel):
    """Metadata for Pylon account artifacts."""

    account_id: str
    account_name: str | None
    primary_domain: str | None
    created_at: str | None

    @classmethod
    def from_api_account(cls, account: PylonAccount) -> "PylonAccountArtifactMetadata":
        return PylonAccountArtifactMetadata(
            account_id=account.id,
            account_name=account.name,
            primary_domain=account.primary_domain,
            created_at=account.created_at,
        )


class PylonContactArtifactMetadata(BaseModel):
    """Metadata for Pylon contact artifacts."""

    contact_id: str
    contact_name: str | None
    contact_email: str | None
    portal_role: str | None

    @classmethod
    def from_api_contact(cls, contact: PylonContact) -> "PylonContactArtifactMetadata":
        return PylonContactArtifactMetadata(
            contact_id=contact.id,
            contact_name=contact.name,
            contact_email=contact.email,
            portal_role=contact.portal_role,
        )


class PylonUserArtifactMetadata(BaseModel):
    """Metadata for Pylon user artifacts."""

    user_id: str
    user_name: str | None
    user_email: str | None

    @classmethod
    def from_api_user(cls, user: PylonUser) -> "PylonUserArtifactMetadata":
        return PylonUserArtifactMetadata(
            user_id=user.id,
            user_name=user.name,
            user_email=user.email,
        )


# Artifact classes
class PylonIssueArtifact(BaseIngestArtifact):
    """Typed Pylon issue artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.PYLON_ISSUE
    content: PylonIssue
    metadata: PylonIssueArtifactMetadata

    @classmethod
    def from_api_issue(cls, issue: PylonIssue, ingest_job_id: UUID) -> "PylonIssueArtifact":
        # Parse updated_at or use current time
        updated_at = issue.updated_at or issue.created_at
        if updated_at:
            source_updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        else:
            source_updated = datetime.now(UTC)

        return PylonIssueArtifact(
            entity_id=pylon_issue_entity_id(issue.id),
            content=issue,
            metadata=PylonIssueArtifactMetadata.from_api_issue(issue),
            source_updated_at=source_updated,
            ingest_job_id=ingest_job_id,
        )


class PylonAccountArtifact(BaseIngestArtifact):
    """Typed Pylon account artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.PYLON_ACCOUNT
    content: PylonAccount
    metadata: PylonAccountArtifactMetadata

    @classmethod
    def from_api_account(cls, account: PylonAccount, ingest_job_id: UUID) -> "PylonAccountArtifact":
        # Parse created_at or use current time
        if account.created_at:
            source_updated = datetime.fromisoformat(account.created_at.replace("Z", "+00:00"))
        else:
            source_updated = datetime.now(UTC)

        return PylonAccountArtifact(
            entity_id=pylon_account_entity_id(account.id),
            content=account,
            metadata=PylonAccountArtifactMetadata.from_api_account(account),
            source_updated_at=source_updated,
            ingest_job_id=ingest_job_id,
        )


class PylonContactArtifact(BaseIngestArtifact):
    """Typed Pylon contact artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.PYLON_CONTACT
    content: PylonContact
    metadata: PylonContactArtifactMetadata

    @classmethod
    def from_api_contact(cls, contact: PylonContact, ingest_job_id: UUID) -> "PylonContactArtifact":
        # Contacts don't have timestamps in the API, use current time
        source_updated = datetime.now(UTC)

        return PylonContactArtifact(
            entity_id=pylon_contact_entity_id(contact.id),
            content=contact,
            metadata=PylonContactArtifactMetadata.from_api_contact(contact),
            source_updated_at=source_updated,
            ingest_job_id=ingest_job_id,
        )


class PylonUserArtifact(BaseIngestArtifact):
    """Typed Pylon user artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.PYLON_USER
    content: PylonUser
    metadata: PylonUserArtifactMetadata

    @classmethod
    def from_api_user(cls, user: PylonUser, ingest_job_id: UUID) -> "PylonUserArtifact":
        # Users don't have timestamps in the API, use current time
        source_updated = datetime.now(UTC)

        return PylonUserArtifact(
            entity_id=pylon_user_entity_id(user.id),
            content=user,
            metadata=PylonUserArtifactMetadata.from_api_user(user),
            source_updated_at=source_updated,
            ingest_job_id=ingest_job_id,
        )


class PylonTeamArtifactMetadata(BaseModel):
    """Metadata for Pylon team artifacts."""

    team_id: str
    team_name: str | None

    @classmethod
    def from_api_team(cls, team: PylonTeam) -> "PylonTeamArtifactMetadata":
        return PylonTeamArtifactMetadata(
            team_id=team.id,
            team_name=team.name,
        )


class PylonTeamArtifact(BaseIngestArtifact):
    """Typed Pylon team artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.PYLON_TEAM
    content: PylonTeam
    metadata: PylonTeamArtifactMetadata

    @classmethod
    def from_api_team(cls, team: PylonTeam, ingest_job_id: UUID) -> "PylonTeamArtifact":
        # Teams don't have timestamps in the API, use current time
        source_updated = datetime.now(UTC)

        return PylonTeamArtifact(
            entity_id=pylon_team_entity_id(team.id),
            content=team,
            metadata=PylonTeamArtifactMetadata.from_api_team(team),
            source_updated_at=source_updated,
            ingest_job_id=ingest_job_id,
        )
