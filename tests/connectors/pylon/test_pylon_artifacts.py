"""Tests for Pylon artifact models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from connectors.base.base_ingest_artifact import ArtifactEntity
from connectors.pylon.client.pylon_models import (
    PylonAccount,
    PylonAccountRef,
    PylonAssignee,
    PylonContact,
    PylonIssue,
    PylonRequester,
    PylonTeam,
    PylonUser,
)
from connectors.pylon.extractors.pylon_artifacts import (
    PylonAccountArtifact,
    PylonContactArtifact,
    PylonIssueArtifact,
    PylonTeamArtifact,
    PylonUserArtifact,
    pylon_account_entity_id,
    pylon_contact_entity_id,
    pylon_issue_entity_id,
    pylon_team_entity_id,
    pylon_user_entity_id,
)


@pytest.fixture
def job_id():
    """Create a test job ID."""
    return uuid4()


class TestEntityIdGenerators:
    """Tests for entity ID generation functions."""

    def test_pylon_issue_entity_id(self):
        assert pylon_issue_entity_id("iss_abc123") == "pylon_issue_iss_abc123"

    def test_pylon_account_entity_id(self):
        assert pylon_account_entity_id("acc_xyz789") == "pylon_account_acc_xyz789"

    def test_pylon_contact_entity_id(self):
        assert pylon_contact_entity_id("con_def456") == "pylon_contact_con_def456"

    def test_pylon_user_entity_id(self):
        assert pylon_user_entity_id("usr_ghi012") == "pylon_user_usr_ghi012"

    def test_pylon_team_entity_id(self):
        assert pylon_team_entity_id("team_jkl345") == "pylon_team_team_jkl345"


class TestPylonIssueArtifact:
    """Tests for PylonIssueArtifact."""

    @pytest.fixture
    def mock_issue(self):
        """Create a mock Pylon issue with full data."""
        return PylonIssue(
            id="iss_abc123",
            number=42,
            title="Test Issue",
            body_html="<p>Issue description</p>",
            state="open",
            priority="high",
            source="slack",
            created_at="2024-01-15T10:00:00Z",
            updated_at="2024-01-20T15:30:00Z",
            account=PylonAccountRef(id="acc_xyz"),
            requester=PylonRequester(id="req_123", email="requester@example.com"),
            assignee=PylonAssignee(id="usr_456", email="assignee@example.com"),
            team=PylonTeam(id="team_789", name="Support"),
        )

    @pytest.fixture
    def mock_issue_minimal(self):
        """Create a mock Pylon issue with minimal data."""
        return PylonIssue(
            id="iss_minimal",
        )

    def test_from_api_issue_full_data(self, mock_issue, job_id):
        """Test creating artifact from issue with full data."""
        artifact = PylonIssueArtifact.from_api_issue(mock_issue, job_id)

        assert artifact.entity == ArtifactEntity.PYLON_ISSUE
        assert artifact.entity_id == "pylon_issue_iss_abc123"
        assert artifact.content == mock_issue
        assert artifact.ingest_job_id == job_id

        # Check metadata
        assert artifact.metadata.issue_id == "iss_abc123"
        assert artifact.metadata.issue_number == 42
        assert artifact.metadata.state == "open"
        assert artifact.metadata.priority == "high"
        assert artifact.metadata.account_id == "acc_xyz"
        assert artifact.metadata.requester_id == "req_123"
        assert artifact.metadata.requester_email == "requester@example.com"
        assert artifact.metadata.assignee_id == "usr_456"
        assert artifact.metadata.team_id == "team_789"

    def test_from_api_issue_parses_updated_at(self, mock_issue, job_id):
        """Test that updated_at is correctly parsed."""
        artifact = PylonIssueArtifact.from_api_issue(mock_issue, job_id)

        expected = datetime(2024, 1, 20, 15, 30, 0, tzinfo=UTC)
        assert artifact.source_updated_at == expected

    def test_from_api_issue_uses_created_at_when_no_updated_at(self, job_id):
        """Test fallback to created_at when updated_at is missing."""
        issue = PylonIssue(
            id="iss_no_update",
            created_at="2024-01-15T10:00:00Z",
        )
        artifact = PylonIssueArtifact.from_api_issue(issue, job_id)

        expected = datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)
        assert artifact.source_updated_at == expected

    def test_from_api_issue_minimal_data(self, mock_issue_minimal, job_id):
        """Test creating artifact from issue with minimal data."""
        artifact = PylonIssueArtifact.from_api_issue(mock_issue_minimal, job_id)

        assert artifact.entity_id == "pylon_issue_iss_minimal"
        assert artifact.metadata.issue_id == "iss_minimal"
        assert artifact.metadata.issue_number is None
        assert artifact.metadata.state is None
        assert artifact.metadata.account_id is None
        assert artifact.metadata.requester_id is None
        assert artifact.metadata.assignee_id is None
        assert artifact.metadata.team_id is None


class TestPylonAccountArtifact:
    """Tests for PylonAccountArtifact."""

    @pytest.fixture
    def mock_account(self):
        """Create a mock Pylon account."""
        return PylonAccount(
            id="acc_abc123",
            name="Acme Corp",
            primary_domain="acme.com",
            created_at="2024-01-10T08:00:00Z",
        )

    def test_from_api_account(self, mock_account, job_id):
        """Test creating artifact from account."""
        artifact = PylonAccountArtifact.from_api_account(mock_account, job_id)

        assert artifact.entity == ArtifactEntity.PYLON_ACCOUNT
        assert artifact.entity_id == "pylon_account_acc_abc123"
        assert artifact.content == mock_account
        assert artifact.metadata.account_id == "acc_abc123"
        assert artifact.metadata.account_name == "Acme Corp"
        assert artifact.metadata.primary_domain == "acme.com"

    def test_from_api_account_parses_created_at(self, mock_account, job_id):
        """Test that created_at is correctly parsed."""
        artifact = PylonAccountArtifact.from_api_account(mock_account, job_id)

        expected = datetime(2024, 1, 10, 8, 0, 0, tzinfo=UTC)
        assert artifact.source_updated_at == expected

    def test_from_api_account_minimal(self, job_id):
        """Test creating artifact from account with minimal data."""
        account = PylonAccount(id="acc_minimal")
        artifact = PylonAccountArtifact.from_api_account(account, job_id)

        assert artifact.entity_id == "pylon_account_acc_minimal"
        assert artifact.metadata.account_name is None
        assert artifact.metadata.primary_domain is None


class TestPylonContactArtifact:
    """Tests for PylonContactArtifact."""

    @pytest.fixture
    def mock_contact(self):
        """Create a mock Pylon contact."""
        return PylonContact(
            id="con_abc123",
            name="John Doe",
            email="john@example.com",
            portal_role="admin",
        )

    def test_from_api_contact(self, mock_contact, job_id):
        """Test creating artifact from contact."""
        artifact = PylonContactArtifact.from_api_contact(mock_contact, job_id)

        assert artifact.entity == ArtifactEntity.PYLON_CONTACT
        assert artifact.entity_id == "pylon_contact_con_abc123"
        assert artifact.content == mock_contact
        assert artifact.metadata.contact_id == "con_abc123"
        assert artifact.metadata.contact_name == "John Doe"
        assert artifact.metadata.contact_email == "john@example.com"
        assert artifact.metadata.portal_role == "admin"

    def test_from_api_contact_minimal(self, job_id):
        """Test creating artifact from contact with minimal data."""
        contact = PylonContact(id="con_minimal")
        artifact = PylonContactArtifact.from_api_contact(contact, job_id)

        assert artifact.entity_id == "pylon_contact_con_minimal"
        assert artifact.metadata.contact_name is None
        assert artifact.metadata.contact_email is None


class TestPylonUserArtifact:
    """Tests for PylonUserArtifact."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock Pylon user."""
        return PylonUser(
            id="usr_abc123",
            name="Jane Smith",
            email="jane@company.com",
        )

    def test_from_api_user(self, mock_user, job_id):
        """Test creating artifact from user."""
        artifact = PylonUserArtifact.from_api_user(mock_user, job_id)

        assert artifact.entity == ArtifactEntity.PYLON_USER
        assert artifact.entity_id == "pylon_user_usr_abc123"
        assert artifact.content == mock_user
        assert artifact.metadata.user_id == "usr_abc123"
        assert artifact.metadata.user_name == "Jane Smith"
        assert artifact.metadata.user_email == "jane@company.com"

    def test_from_api_user_minimal(self, job_id):
        """Test creating artifact from user with minimal data."""
        user = PylonUser(id="usr_minimal")
        artifact = PylonUserArtifact.from_api_user(user, job_id)

        assert artifact.entity_id == "pylon_user_usr_minimal"
        assert artifact.metadata.user_name is None
        assert artifact.metadata.user_email is None


class TestPylonTeamArtifact:
    """Tests for PylonTeamArtifact."""

    @pytest.fixture
    def mock_team(self):
        """Create a mock Pylon team."""
        return PylonTeam(
            id="team_abc123",
            name="Support Team",
        )

    def test_from_api_team(self, mock_team, job_id):
        """Test creating artifact from team."""
        artifact = PylonTeamArtifact.from_api_team(mock_team, job_id)

        assert artifact.entity == ArtifactEntity.PYLON_TEAM
        assert artifact.entity_id == "pylon_team_team_abc123"
        assert artifact.content == mock_team
        assert artifact.metadata.team_id == "team_abc123"
        assert artifact.metadata.team_name == "Support Team"

    def test_from_api_team_minimal(self, job_id):
        """Test creating artifact from team with minimal data."""
        team = PylonTeam(id="team_minimal")
        artifact = PylonTeamArtifact.from_api_team(team, job_id)

        assert artifact.entity_id == "pylon_team_team_minimal"
        assert artifact.metadata.team_name is None
