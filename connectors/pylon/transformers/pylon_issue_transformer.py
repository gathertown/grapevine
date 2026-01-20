"""Pylon transformer to convert artifacts into documents."""

from datetime import UTC, datetime

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.pylon.client.pylon_models import PylonAssignee, PylonIssue, PylonRequester
from connectors.pylon.extractors.pylon_artifacts import (
    PylonAccountArtifact,
    PylonContactArtifact,
    PylonIssueArtifact,
    PylonTeamArtifact,
    PylonUserArtifact,
    pylon_account_entity_id,
    pylon_contact_entity_id,
    pylon_team_entity_id,
    pylon_user_entity_id,
)
from connectors.pylon.transformers.pylon_issue_document import (
    PylonIssueDocument,
    PylonIssueDocumentRawData,
    RawDataAccount,
    RawDataCsatResponse,
    RawDataExternalIssue,
    RawDataRequester,
    RawDataTeam,
    RawDataUser,
    pylon_issue_document_id,
)
from src.ingest.repositories import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


class IssueHydrator:
    """Hydrates Pylon issues with full data from related artifacts."""

    _user_by_id: dict[str, PylonUserArtifact]
    _team_by_id: dict[str, PylonTeamArtifact]
    _account_by_id: dict[str, PylonAccountArtifact]
    _contact_by_id: dict[str, PylonContactArtifact]

    def __init__(
        self,
        user_by_id: dict[str, PylonUserArtifact],
        team_by_id: dict[str, PylonTeamArtifact],
        account_by_id: dict[str, PylonAccountArtifact],
        contact_by_id: dict[str, PylonContactArtifact],
    ):
        self._user_by_id = user_by_id
        self._team_by_id = team_by_id
        self._account_by_id = account_by_id
        self._contact_by_id = contact_by_id

    def hydrate_issue(self, artifact: PylonIssueArtifact) -> PylonIssueDocumentRawData:
        """Transform a Pylon issue artifact into hydrated raw data."""
        issue: PylonIssue = artifact.content

        # Build hydrated raw data structures
        account = self._get_raw_data_account(issue.account.id if issue.account else None)
        team = self._get_raw_data_team(issue.team.id if issue.team else None)
        assignee = self._get_raw_data_user(issue.assignee)
        requester = self._get_raw_data_requester(issue.requester)

        csat_responses: list[RawDataCsatResponse] = []
        if issue.csat_responses:
            csat_responses = [
                RawDataCsatResponse(
                    score=csat.score,
                    comment=csat.comment,
                )
                for csat in issue.csat_responses
            ]

        external_issues: list[RawDataExternalIssue] = []
        if issue.external_issues:
            external_issues = [
                RawDataExternalIssue(
                    source=ext.source,
                    external_id=ext.external_id,
                    link=ext.link,
                )
                for ext in issue.external_issues
            ]

        return PylonIssueDocumentRawData(
            id=issue.id,
            number=issue.number,
            title=issue.title,
            body_html=issue.body_html,
            state=issue.state,
            priority=issue.priority,
            tags=issue.tags,
            created_at=issue.created_at,
            updated_at=issue.updated_at,
            first_response_time=issue.first_response_time,
            resolution_time=issue.resolution_time,
            first_response_seconds=issue.first_response_seconds,
            resolution_seconds=issue.resolution_seconds,
            account=account,
            team=team,
            assignee=assignee,
            requester=requester,
            csat_responses=csat_responses,
            external_issues=external_issues,
            custom_fields=issue.custom_fields,
        )

    def _get_raw_data_user(self, assignee: "PylonAssignee | None") -> RawDataUser | None:
        """Get hydrated user data from user artifact.

        Falls back to email from issue.assignee if artifact not found.
        """
        if assignee is None:
            return None

        user_artifact = self._user_by_id.get(assignee.id)
        if user_artifact:
            return RawDataUser(
                id=user_artifact.content.id,
                name=user_artifact.content.name,
                email=user_artifact.content.email,
            )

        # Fallback: use email from issue if available (before reference sync completes)
        return RawDataUser(
            id=assignee.id,
            name=None,
            email=assignee.email,
        )

    def _get_raw_data_requester(
        self, requester: "PylonRequester | None"
    ) -> RawDataRequester | None:
        """Get hydrated requester data from contact or user artifact.

        Requesters can be either contacts (external) or users (internal).
        We check contacts first, then users.
        Falls back to email from issue.requester if artifacts not found.
        """
        if requester is None or requester.id is None:
            return None

        # Try to find as contact first (external requester)
        contact_artifact = self._contact_by_id.get(requester.id)
        if contact_artifact:
            return RawDataRequester(
                id=contact_artifact.content.id,
                name=contact_artifact.content.name,
                email=contact_artifact.content.email,
            )

        # Try to find as user (internal requester)
        user_artifact = self._user_by_id.get(requester.id)
        if user_artifact:
            return RawDataRequester(
                id=user_artifact.content.id,
                name=user_artifact.content.name,
                email=user_artifact.content.email,
            )

        # Fallback: use email from issue if available (before reference sync completes)
        return RawDataRequester(
            id=requester.id,
            name=None,
            email=requester.email,
        )

    def _get_raw_data_team(self, team_id: str | None) -> RawDataTeam | None:
        """Get hydrated team data from team artifact."""
        if team_id is None:
            return None

        team_artifact = self._team_by_id.get(team_id)
        if team_artifact:
            return RawDataTeam(
                id=team_artifact.content.id,
                name=team_artifact.content.name,
            )

        # Fallback: return minimal data with just the ID
        return RawDataTeam(
            id=team_id,
            name=None,
        )

    def _get_raw_data_account(self, account_id: str | None) -> RawDataAccount | None:
        """Get hydrated account data from account artifact."""
        if account_id is None:
            return None

        account_artifact = self._account_by_id.get(account_id)
        if account_artifact:
            return RawDataAccount(
                id=account_artifact.content.id,
                name=account_artifact.content.name,
                domains=account_artifact.content.domains,
            )

        # Fallback: return minimal data with just the ID
        return RawDataAccount(
            id=account_id,
            name=None,
            domains=None,
        )


class PylonIssueTransformer(BaseTransformer[PylonIssueDocument]):
    """Transform Pylon issue artifacts into documents for indexing."""

    def __init__(self):
        super().__init__(DocumentSource.PYLON_ISSUE)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[PylonIssueDocument]:
        """Transform Pylon issue artifacts into documents.

        Args:
            entity_ids: List of entity IDs to transform
            readonly_db_pool: Database connection pool

        Returns:
            List of transformed PylonIssueDocument instances
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Fetch issue artifacts from database
        issue_artifacts = await repo.get_artifacts_by_entity_ids(PylonIssueArtifact, entity_ids)

        logger.info(
            f"Loaded {len(issue_artifacts)} Pylon issue artifacts for {len(entity_ids)} entity IDs"
        )

        # Fetch related reference data artifacts
        user_by_id = await self._get_user_artifacts_by_id(repo, issue_artifacts)
        team_by_id = await self._get_team_artifacts_by_id(repo, issue_artifacts)
        account_by_id = await self._get_account_artifacts_by_id(repo, issue_artifacts)
        contact_by_id = await self._get_contact_artifacts_by_id(repo, issue_artifacts)

        logger.info(
            f"Loaded reference data: {len(user_by_id)} users, {len(team_by_id)} teams, "
            f"{len(account_by_id)} accounts, {len(contact_by_id)} contacts"
        )

        # Create hydrator with reference data
        hydrator = IssueHydrator(
            user_by_id=user_by_id,
            team_by_id=team_by_id,
            account_by_id=account_by_id,
            contact_by_id=contact_by_id,
        )

        documents: list[PylonIssueDocument] = []

        for artifact in issue_artifacts:
            try:
                raw_data = hydrator.hydrate_issue(artifact)
                doc = self._create_document(artifact, raw_data)
                documents.append(doc)
            except Exception as e:
                logger.error(f"Failed to transform Pylon issue artifact {artifact.entity_id}: {e}")
                continue

        logger.info(
            f"Pylon Issue transformation complete: created {len(documents)} documents "
            f"from {len(issue_artifacts)} artifacts"
        )

        return documents

    def _create_document(
        self, artifact: PylonIssueArtifact, raw_data: PylonIssueDocumentRawData
    ) -> PylonIssueDocument:
        """Create a document from hydrated raw data."""
        issue: PylonIssue = artifact.content

        # Parse source_updated_at
        updated_at_str = issue.updated_at or issue.created_at
        if updated_at_str:
            source_updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        else:
            source_updated_at = datetime.now(UTC)

        return PylonIssueDocument(
            id=pylon_issue_document_id(issue.id),
            raw_data=raw_data,
            source_updated_at=source_updated_at,
            permission_policy="tenant",  # Pylon issues are visible to all tenant users
            permission_allowed_tokens=None,
        )

    async def _get_user_artifacts_by_id(
        self, repo: ArtifactRepository, issue_artifacts: list[PylonIssueArtifact]
    ) -> dict[str, PylonUserArtifact]:
        """Fetch user artifacts for assignees in the issues."""
        user_ids = {
            artifact.content.assignee.id
            for artifact in issue_artifacts
            if artifact.content.assignee is not None
        }
        # Also add requester IDs (they could be internal users)
        user_ids.update(
            artifact.content.requester.id
            for artifact in issue_artifacts
            if artifact.content.requester is not None and artifact.content.requester.id is not None
        )

        if not user_ids:
            return {}

        user_entity_ids = [pylon_user_entity_id(uid) for uid in user_ids]
        user_artifacts = await repo.get_artifacts_by_entity_ids(PylonUserArtifact, user_entity_ids)

        return {user.content.id: user for user in user_artifacts}

    async def _get_team_artifacts_by_id(
        self, repo: ArtifactRepository, issue_artifacts: list[PylonIssueArtifact]
    ) -> dict[str, PylonTeamArtifact]:
        """Fetch team artifacts for teams in the issues."""
        team_ids = {
            artifact.content.team.id
            for artifact in issue_artifacts
            if artifact.content.team is not None
        }

        if not team_ids:
            return {}

        team_entity_ids = [pylon_team_entity_id(tid) for tid in team_ids]
        team_artifacts = await repo.get_artifacts_by_entity_ids(PylonTeamArtifact, team_entity_ids)

        return {team.content.id: team for team in team_artifacts}

    async def _get_account_artifacts_by_id(
        self, repo: ArtifactRepository, issue_artifacts: list[PylonIssueArtifact]
    ) -> dict[str, PylonAccountArtifact]:
        """Fetch account artifacts for accounts in the issues."""
        account_ids = {
            artifact.content.account.id
            for artifact in issue_artifacts
            if artifact.content.account is not None
        }

        if not account_ids:
            return {}

        account_entity_ids = [pylon_account_entity_id(aid) for aid in account_ids]
        account_artifacts = await repo.get_artifacts_by_entity_ids(
            PylonAccountArtifact, account_entity_ids
        )

        return {account.content.id: account for account in account_artifacts}

    async def _get_contact_artifacts_by_id(
        self, repo: ArtifactRepository, issue_artifacts: list[PylonIssueArtifact]
    ) -> dict[str, PylonContactArtifact]:
        """Fetch contact artifacts for requesters in the issues."""
        requester_ids = {
            artifact.content.requester.id
            for artifact in issue_artifacts
            if artifact.content.requester is not None and artifact.content.requester.id is not None
        }

        if not requester_ids:
            return {}

        contact_entity_ids = [pylon_contact_entity_id(rid) for rid in requester_ids]
        contact_artifacts = await repo.get_artifacts_by_entity_ids(
            PylonContactArtifact, contact_entity_ids
        )

        return {contact.content.id: contact for contact in contact_artifacts}
