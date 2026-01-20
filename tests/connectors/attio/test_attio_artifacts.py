"""Tests for Attio artifact models."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from connectors.attio.attio_artifacts import (
    AttioCompanyArtifact,
    AttioDealArtifact,
    AttioPersonArtifact,
)
from connectors.base.base_ingest_artifact import ArtifactEntity


@pytest.fixture
def job_id() -> UUID:
    """Create a test job ID."""
    return uuid4()


@pytest.fixture
def mock_company_record():
    """Mock Attio company record from API."""
    return {
        "id": {"record_id": "rec_company_abc123"},
        "values": {
            "name": [{"value": "Acme Corporation"}],
            "domains": [{"domain": "acme.com"}, {"domain": "acme.io"}],
            "description": [{"value": "A leading provider of everything."}],
            "industry": [{"value": "Technology"}],
            "employee_count": [{"value": 500}],
        },
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-02-20T15:30:00.000Z",
    }


@pytest.fixture
def mock_person_record():
    """Mock Attio person record from API."""
    return {
        "id": {"record_id": "rec_person_xyz789"},
        "values": {
            "name": [{"first_name": "John", "last_name": "Doe", "full_name": "John Doe"}],
            "email_addresses": [
                {"email_address": "john@acme.com"},
                {"email_address": "john.doe@gmail.com"},
            ],
            "phone_numbers": [{"phone_number": "+1-555-123-4567"}],
            "job_title": [{"value": "CEO"}],
        },
        "created_at": "2024-01-20T09:00:00.000Z",
        "updated_at": "2024-03-01T12:00:00.000Z",
    }


@pytest.fixture
def mock_deal_record():
    """Mock Attio deal record from API."""
    return {
        "id": {"record_id": "rec_deal_def456"},
        "values": {
            "name": [{"value": "Enterprise Deal - Acme"}],
            "value": [{"currency_value": 150000, "currency_code": "USD"}],
            "pipeline_stage": [{"value": "Negotiation"}],
            "close_date": [{"value": "2024-06-30"}],
            "associated_company": [
                {"record_id": "rec_company_abc123", "name": {"full_name": "Acme Corporation"}}
            ],
            "associated_people": [
                {"record_id": "rec_person_xyz789", "name": {"full_name": "John Doe"}}
            ],
        },
        "created_at": "2024-02-01T14:00:00.000Z",
        "updated_at": "2024-03-15T10:00:00.000Z",
    }


@pytest.fixture
def mock_notes():
    """Mock notes attached to a deal."""
    return [
        {
            "id": {"note_id": "note_001"},
            "title": "Initial Call Notes",
            "content_plaintext": "Discussed pricing and timeline. Client seems interested.",
            "created_at": "2024-02-05T11:00:00.000Z",
        },
        {
            "id": {"note_id": "note_002"},
            "title": "Follow-up Meeting",
            "content_plaintext": "Presented demo. Received positive feedback.",
            "created_at": "2024-02-15T14:00:00.000Z",
        },
    ]


@pytest.fixture
def mock_tasks():
    """Mock tasks linked to a deal."""
    return [
        {
            "id": {"task_id": "task_001"},
            "content_plaintext": "Send proposal document",
            "is_completed": True,
            "deadline_at": "2024-02-10T17:00:00.000Z",
        },
        {
            "id": {"task_id": "task_002"},
            "content_plaintext": "Schedule contract review call",
            "is_completed": False,
            "deadline_at": "2024-03-20T17:00:00.000Z",
        },
    ]


class TestAttioCompanyArtifact:
    """Test suite for AttioCompanyArtifact."""

    def test_from_api_response_basic(self, mock_company_record, job_id):
        """Test creating artifact from basic company record."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.ATTIO_COMPANY
        # entity_id is just the raw record_id (prefix added at document level)
        assert artifact.entity_id == "rec_company_abc123"
        assert artifact.metadata.record_id == "rec_company_abc123"
        assert artifact.metadata.created_at == "2024-01-15T10:00:00.000Z"
        assert artifact.metadata.updated_at == "2024-02-20T15:30:00.000Z"
        assert artifact.content.record_data == mock_company_record

    def test_from_api_response_with_workspace_id(self, mock_company_record, job_id):
        """Test creating artifact with workspace ID."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
            workspace_id="ws_123",
        )

        assert artifact.metadata.workspace_id == "ws_123"

    def test_from_api_response_parses_timestamp(self, mock_company_record, job_id):
        """Test that source_updated_at is properly parsed."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
        )

        assert artifact.source_updated_at == datetime(2024, 2, 20, 15, 30, 0, tzinfo=UTC)

    def test_from_api_response_uses_created_at_when_no_updated_at(self, job_id):
        """Test fallback to created_at when updated_at is missing."""
        record = {
            "id": {"record_id": "rec_123"},
            "values": {"name": [{"value": "Test"}]},
            "created_at": "2024-01-15T10:00:00.000Z",
        }

        artifact = AttioCompanyArtifact.from_api_response(
            record_data=record,
            ingest_job_id=job_id,
        )

        assert artifact.source_updated_at == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)

    def test_from_api_response_handles_string_id(self, job_id):
        """Test handling when id is a string instead of dict."""
        record = {
            "id": "rec_simple_id",
            "values": {"name": [{"value": "Test"}]},
            "created_at": "2024-01-15T10:00:00.000Z",
        }

        artifact = AttioCompanyArtifact.from_api_response(
            record_data=record,
            ingest_job_id=job_id,
        )

        # When id is a string, it's used directly
        assert artifact.metadata.record_id == "rec_simple_id"


class TestAttioPersonArtifact:
    """Test suite for AttioPersonArtifact."""

    def test_from_api_response_basic(self, mock_person_record, job_id):
        """Test creating artifact from basic person record."""
        artifact = AttioPersonArtifact.from_api_response(
            record_data=mock_person_record,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.ATTIO_PERSON
        # entity_id is just the raw record_id (prefix added at document level)
        assert artifact.entity_id == "rec_person_xyz789"
        assert artifact.metadata.record_id == "rec_person_xyz789"
        assert artifact.content.record_data == mock_person_record

    def test_from_api_response_parses_z_suffix_timestamp(self, job_id):
        """Test that Z suffix timestamps are parsed correctly."""
        record = {
            "id": {"record_id": "rec_123"},
            "values": {},
            "created_at": "2024-01-15T10:00:00Z",  # Z suffix without milliseconds
        }

        artifact = AttioPersonArtifact.from_api_response(
            record_data=record,
            ingest_job_id=job_id,
        )

        assert artifact.source_updated_at == datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC)


class TestAttioDealArtifact:
    """Test suite for AttioDealArtifact."""

    def test_from_api_response_basic(self, mock_deal_record, job_id):
        """Test creating artifact from basic deal record."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.ATTIO_DEAL
        # entity_id is just the raw record_id (prefix added at document level)
        assert artifact.entity_id == "rec_deal_def456"
        assert artifact.metadata.record_id == "rec_deal_def456"
        assert artifact.metadata.pipeline_stage == "Negotiation"
        assert artifact.content.record_data == mock_deal_record

    def test_from_api_response_with_notes_and_tasks(
        self, mock_deal_record, mock_notes, mock_tasks, job_id
    ):
        """Test creating artifact with embedded notes and tasks."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
            notes=mock_notes,
            tasks=mock_tasks,
        )

        assert len(artifact.content.notes) == 2
        assert len(artifact.content.tasks) == 2
        assert artifact.content.notes[0]["title"] == "Initial Call Notes"
        assert artifact.content.tasks[0]["content_plaintext"] == "Send proposal document"

    def test_from_api_response_without_notes_and_tasks(self, mock_deal_record, job_id):
        """Test creating artifact without notes and tasks defaults to empty lists."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )

        assert artifact.content.notes == []
        assert artifact.content.tasks == []

    def test_from_api_response_extracts_pipeline_stage_with_title(self, job_id):
        """Test extracting pipeline stage when it has 'title' key."""
        record = {
            "id": {"record_id": "rec_deal_123"},
            "values": {
                "name": [{"value": "Test Deal"}],
                "pipeline_stage": [{"title": "Closed Won"}],
            },
            "created_at": "2024-01-15T10:00:00.000Z",
        }

        artifact = AttioDealArtifact.from_api_response(
            record_data=record,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.pipeline_stage == "Closed Won"

    def test_from_api_response_no_pipeline_stage(self, job_id):
        """Test creating artifact when pipeline_stage is missing."""
        record = {
            "id": {"record_id": "rec_deal_123"},
            "values": {"name": [{"value": "Test Deal"}]},
            "created_at": "2024-01-15T10:00:00.000Z",
        }

        artifact = AttioDealArtifact.from_api_response(
            record_data=record,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.pipeline_stage is None

    def test_from_api_response_empty_pipeline_stage_list(self, job_id):
        """Test creating artifact when pipeline_stage is empty list."""
        record = {
            "id": {"record_id": "rec_deal_123"},
            "values": {
                "name": [{"value": "Test Deal"}],
                "pipeline_stage": [],
            },
            "created_at": "2024-01-15T10:00:00.000Z",
        }

        artifact = AttioDealArtifact.from_api_response(
            record_data=record,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.pipeline_stage is None


class TestArtifactEntityIds:
    """Test suite for entity ID generation.

    Note: entity_id at the artifact level is just the raw record_id.
    The prefix (attio_company_, attio_person_, attio_deal_) is added
    when creating document IDs, not at the artifact level.
    """

    def test_company_entity_id_format(self, mock_company_record, job_id):
        """Test company entity ID is the raw record ID."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
        )

        # entity_id is just the raw record_id
        assert artifact.entity_id == "rec_company_abc123"

    def test_person_entity_id_format(self, mock_person_record, job_id):
        """Test person entity ID is the raw record ID."""
        artifact = AttioPersonArtifact.from_api_response(
            record_data=mock_person_record,
            ingest_job_id=job_id,
        )

        # entity_id is just the raw record_id
        assert artifact.entity_id == "rec_person_xyz789"

    def test_deal_entity_id_format(self, mock_deal_record, job_id):
        """Test deal entity ID is the raw record ID."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )

        # entity_id is just the raw record_id
        assert artifact.entity_id == "rec_deal_def456"


class TestArtifactTimestampHandling:
    """Test suite for timestamp edge cases."""

    def test_uses_current_time_when_no_timestamps(self, job_id):
        """Test fallback to current time when both timestamps missing."""
        record = {
            "id": {"record_id": "rec_123"},
            "values": {},
            # No created_at or updated_at
        }

        before = datetime.now(UTC)
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=record,
            ingest_job_id=job_id,
        )
        after = datetime.now(UTC)

        # source_updated_at should be approximately now
        assert before <= artifact.source_updated_at <= after

    def test_handles_milliseconds_in_timestamp(self, job_id):
        """Test parsing timestamps with milliseconds."""
        record = {
            "id": {"record_id": "rec_123"},
            "values": {},
            "created_at": "2024-01-15T10:00:00.123Z",
        }

        artifact = AttioCompanyArtifact.from_api_response(
            record_data=record,
            ingest_job_id=job_id,
        )

        assert artifact.source_updated_at.microsecond == 123000
