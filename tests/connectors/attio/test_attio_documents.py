"""Tests for Attio document models."""

from uuid import uuid4

import pytest

from connectors.attio.attio_artifacts import (
    AttioCompanyArtifact,
    AttioDealArtifact,
    AttioPersonArtifact,
)
from connectors.attio.attio_company_document import AttioCompanyDocument
from connectors.attio.attio_deal_document import AttioDealDocument
from connectors.attio.attio_person_document import AttioPersonDocument
from connectors.base.document_source import DocumentSource


@pytest.fixture
def job_id():
    """Create a test job ID."""
    return uuid4()


@pytest.fixture
def mock_company_record():
    """Complete mock Attio company record."""
    return {
        "id": {"record_id": "rec_company_test123"},
        "values": {
            "name": [{"value": "Test Corporation"}],
            "domains": [{"domain": "test.com"}, {"domain": "test.io"}],
            "description": [{"value": "A test company for testing purposes."}],
            "industry": [{"value": "Software"}],
            "employee_count": [{"value": 150}],
            "linkedin": [{"value": "https://linkedin.com/company/test"}],
            "twitter": [{"value": "@testcorp"}],
        },
        "created_at": "2024-01-15T10:00:00.000Z",
        "updated_at": "2024-02-20T15:30:00.000Z",
    }


@pytest.fixture
def mock_person_record():
    """Complete mock Attio person record."""
    return {
        "id": {"record_id": "rec_person_test456"},
        "values": {
            "name": [{"first_name": "Jane", "last_name": "Smith", "full_name": "Jane Smith"}],
            "email_addresses": [
                {"email_address": "jane@test.com"},
                {"email_address": "jane.smith@personal.com"},
            ],
            "phone_numbers": [{"phone_number": "+1-555-987-6543"}],
            "job_title": [{"value": "CTO"}],
            "company": [
                {"record_id": "rec_company_test123", "name": {"full_name": "Test Corporation"}}
            ],
            "linkedin": [{"value": "https://linkedin.com/in/janesmith"}],
        },
        "created_at": "2024-01-20T09:00:00.000Z",
        "updated_at": "2024-03-01T12:00:00.000Z",
    }


@pytest.fixture
def mock_deal_record():
    """Complete mock Attio deal record."""
    return {
        "id": {"record_id": "rec_deal_test789"},
        "values": {
            "name": [{"value": "Enterprise Contract"}],
            "value": [{"currency_value": 75000, "currency_code": "USD"}],
            "pipeline_stage": [{"value": "Proposal Sent"}],
            "stage": [{"status": {"title": "Proposal Sent"}}],
            "close_date": [{"value": "2024-04-30"}],
            "associated_company": [
                {"record_id": "rec_company_test123", "name": {"full_name": "Test Corporation"}}
            ],
            "associated_people": [
                {"record_id": "rec_person_test456", "name": {"full_name": "Jane Smith"}}
            ],
            "owner": [{"referenced_actor_id": "actor_123", "name": {"full_name": "Sales Rep"}}],
            "description": [{"value": "Large enterprise deal with Test Corporation."}],
        },
        "created_at": "2024-02-01T14:00:00.000Z",
        "updated_at": "2024-03-15T10:00:00.000Z",
    }


@pytest.fixture
def mock_notes():
    """Mock notes for deal."""
    return [
        {
            "id": {"note_id": "note_test001"},
            "title": "Discovery Call",
            "content_plaintext": "Discussed requirements and timeline.",
            "created_at": "2024-02-05T11:00:00.000Z",
            "created_by_actor": {"name": {"full_name": "Sales Rep"}},
        },
    ]


@pytest.fixture
def mock_tasks():
    """Mock tasks for deal.

    Uses Attio API field names:
    - content_plaintext: Task content text
    - deadline_at: Task due date
    """
    return [
        {
            "id": {"task_id": "task_test001"},
            "content_plaintext": "Send follow-up email",
            "is_completed": False,
            "deadline_at": "2024-03-25T17:00:00.000Z",
            "assignees": [{"name": {"full_name": "Sales Rep"}}],
        },
    ]


class TestAttioCompanyDocument:
    """Test suite for AttioCompanyDocument."""

    def test_from_artifact_basic(self, mock_company_record, job_id):
        """Test creating document from company artifact."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
        )

        document = AttioCompanyDocument.from_artifact(artifact)

        assert document.id == "attio_company_rec_company_test123"

    def test_get_content(self, mock_company_record, job_id):
        """Test document content contains company info."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
        )
        document = AttioCompanyDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Test Corporation" in content

    def test_to_embedding_chunks(self, mock_company_record, job_id):
        """Test document generates embedding chunks."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
        )
        document = AttioCompanyDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1
        # Chunk should contain company name (via get_content method)
        all_content = " ".join(chunk.get_content() for chunk in chunks)
        assert "Test Corporation" in all_content

    def test_get_reference_id(self, mock_company_record, job_id):
        """Test reference ID format."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
        )
        document = AttioCompanyDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id.startswith("r_attio_company_")

    def test_get_metadata_includes_type(self, mock_company_record, job_id):
        """Test metadata includes correct type field."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
        )
        document = AttioCompanyDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        assert metadata["type"] == "attio_company"

    def test_get_source_enum(self, mock_company_record, job_id):
        """Test source enum is correct."""
        artifact = AttioCompanyArtifact.from_api_response(
            record_data=mock_company_record,
            ingest_job_id=job_id,
        )
        document = AttioCompanyDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.ATTIO_COMPANY

    def test_select_attribute_extraction(self, job_id):
        """Test that select/status attributes extract the option title correctly."""
        record_with_select = {
            "id": {"record_id": "rec_company_select_test"},
            "values": {
                "name": [{"value": "Select Test Company"}],
                # This is the actual format Attio returns for select attributes
                "estimated_arr_usd": [
                    {
                        "option": {
                            "id": {
                                "object_id": "4e121da1-0495-4f1d-8ecd-48ac4a0cf2a6",
                                "option_id": "5c33de8b-7a6a-456a-a653-29dc4ef87fc0",
                                "attribute_id": "7028654d-4147-4cac-a4f7-bde79521df78",
                                "workspace_id": "3415fdb1-b81f-4006-b086-b59a9b89a3d9",
                            },
                            "title": "$10B+",
                            "is_archived": False,
                        },
                        "active_from": "2025-12-01T23:24:12.669000000Z",
                        "active_until": None,
                        "attribute_type": "select",
                        "created_by_actor": {"id": None, "type": "system"},
                    }
                ],
            },
            "created_at": "2024-01-15T10:00:00.000Z",
            "updated_at": "2024-02-20T15:30:00.000Z",
        }

        artifact = AttioCompanyArtifact.from_api_response(
            record_data=record_with_select,
            ingest_job_id=job_id,
        )
        document = AttioCompanyDocument.from_artifact(artifact)

        content = document.get_content()

        # Should extract the option title "$10B+" not the raw object
        assert "$10B+" in content
        # Should NOT contain the raw option_id or attribute_id
        assert "option_id" not in content
        assert "attribute_id" not in content


class TestAttioPersonDocument:
    """Test suite for AttioPersonDocument."""

    def test_from_artifact_basic(self, mock_person_record, job_id):
        """Test creating document from person artifact."""
        artifact = AttioPersonArtifact.from_api_response(
            record_data=mock_person_record,
            ingest_job_id=job_id,
        )

        document = AttioPersonDocument.from_artifact(artifact)

        assert document.id == "attio_person_rec_person_test456"

    def test_get_content(self, mock_person_record, job_id):
        """Test document content contains person info."""
        artifact = AttioPersonArtifact.from_api_response(
            record_data=mock_person_record,
            ingest_job_id=job_id,
        )
        document = AttioPersonDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Jane Smith" in content

    def test_to_embedding_chunks(self, mock_person_record, job_id):
        """Test document generates embedding chunks."""
        artifact = AttioPersonArtifact.from_api_response(
            record_data=mock_person_record,
            ingest_job_id=job_id,
        )
        document = AttioPersonDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1
        # Chunk should contain person name (via get_content method)
        all_content = " ".join(chunk.get_content() for chunk in chunks)
        assert "Jane Smith" in all_content

    def test_get_reference_id(self, mock_person_record, job_id):
        """Test reference ID format."""
        artifact = AttioPersonArtifact.from_api_response(
            record_data=mock_person_record,
            ingest_job_id=job_id,
        )
        document = AttioPersonDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id.startswith("r_attio_person_")

    def test_get_metadata_includes_type(self, mock_person_record, job_id):
        """Test metadata includes correct type field."""
        artifact = AttioPersonArtifact.from_api_response(
            record_data=mock_person_record,
            ingest_job_id=job_id,
        )
        document = AttioPersonDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        assert metadata["type"] == "attio_person"

    def test_get_source_enum(self, mock_person_record, job_id):
        """Test source enum is correct."""
        artifact = AttioPersonArtifact.from_api_response(
            record_data=mock_person_record,
            ingest_job_id=job_id,
        )
        document = AttioPersonDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.ATTIO_PERSON


class TestAttioDealDocument:
    """Test suite for AttioDealDocument."""

    def test_from_artifact_basic(self, mock_deal_record, job_id):
        """Test creating document from deal artifact."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )

        document = AttioDealDocument.from_artifact(artifact)

        assert document.id == "attio_deal_rec_deal_test789"

    def test_get_content(self, mock_deal_record, job_id):
        """Test document content contains deal info."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Enterprise Contract" in content

    def test_to_embedding_chunks(self, mock_deal_record, job_id):
        """Test document generates embedding chunks."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1

    def test_to_embedding_chunks_includes_notes(self, mock_deal_record, mock_notes, job_id):
        """Test chunks include notes content."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
            notes=mock_notes,
        )
        document = AttioDealDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()
        all_content = " ".join(chunk.get_content() for chunk in chunks)

        # Notes content should appear in chunks
        assert "Discovery Call" in all_content or "requirements and timeline" in all_content

    def test_to_embedding_chunks_includes_tasks(self, mock_deal_record, mock_tasks, job_id):
        """Test chunks include tasks content."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
            tasks=mock_tasks,
        )
        document = AttioDealDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()
        all_content = " ".join(chunk.get_content() for chunk in chunks)

        # Tasks content should appear in chunks
        assert "follow-up email" in all_content

    def test_get_reference_id(self, mock_deal_record, job_id):
        """Test reference ID format."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id.startswith("r_attio_deal_")

    def test_get_metadata_includes_type(self, mock_deal_record, job_id):
        """Test metadata includes correct type field."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        assert metadata["type"] == "attio_deal"

    def test_get_source_enum(self, mock_deal_record, job_id):
        """Test source enum is correct."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.ATTIO_DEAL

    def test_associated_company_in_content(self, mock_deal_record, job_id):
        """Test that associated company appears in document content."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Test Corporation" in content

    def test_associated_people_in_content(self, mock_deal_record, job_id):
        """Test that associated people appear in document content."""
        artifact = AttioDealArtifact.from_api_response(
            record_data=mock_deal_record,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Jane Smith" in content

    def test_currency_attribute_extraction(self, job_id):
        """Test that currency attributes extract value and code correctly."""
        record_with_currency = {
            "id": {"record_id": "rec_deal_currency_test"},
            "values": {
                "name": [{"value": "Currency Test Deal"}],
                # This is the actual format Attio returns for currency attributes
                "value": [
                    {
                        "active_from": "2025-12-05T13:34:39.030000000Z",
                        "active_until": None,
                        "currency_code": "USD",
                        "attribute_type": "currency",
                        "currency_value": 400,
                        "created_by_actor": {
                            "id": "2463c48e-5952-4898-90cd-fe9e86525e35",
                            "type": "workspace-member",
                        },
                    }
                ],
            },
            "created_at": "2024-02-01T14:00:00.000Z",
            "updated_at": "2024-03-15T10:00:00.000Z",
        }

        artifact = AttioDealArtifact.from_api_response(
            record_data=record_with_currency,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        content = document.get_content()

        # Should show formatted value with currency code
        assert "USD" in content
        assert "400" in content
        # Should NOT contain the raw attribute_type or active_from
        assert "attribute_type" not in content
        assert "active_from" not in content

    def test_owner_actor_reference_extraction(self, job_id):
        """Test that owner (actor reference) extracts the name correctly."""
        record_with_owner = {
            "id": {"record_id": "rec_deal_owner_test"},
            "values": {
                "name": [{"value": "Owner Test Deal"}],
                # This is the actual format Attio returns for actor reference attributes
                "owner": [
                    {
                        "referenced_actor_type": "workspace-member",
                        "referenced_actor_id": "2463c48e-5952-4898-90cd-fe9e86525e35",
                        "name": {"full_name": "John Sales Rep"},
                        "active_from": "2025-12-05T13:34:39.030000000Z",
                        "active_until": None,
                        "attribute_type": "actor-reference",
                    }
                ],
            },
            "created_at": "2024-02-01T14:00:00.000Z",
            "updated_at": "2024-03-15T10:00:00.000Z",
        }

        artifact = AttioDealArtifact.from_api_response(
            record_data=record_with_owner,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        content = document.get_content()

        # Should show owner name
        assert "John Sales Rep" in content
        # Should NOT contain the raw referenced_actor_id
        assert "referenced_actor_id" not in content

    def test_company_record_reference_extraction(self, job_id):
        """Test that associated_company (record reference) extracts the name correctly."""
        record_with_company = {
            "id": {"record_id": "rec_deal_company_test"},
            "values": {
                "name": [{"value": "Company Test Deal"}],
                # This is the actual format Attio returns for record reference attributes
                "associated_company": [
                    {
                        "target_object": "companies",
                        "target_record_id": "208ce7c6-0b6d-4635-bcef-e4fa4491a1b3",
                        "name": {"full_name": "Acme Corporation"},
                        "active_from": "2025-12-05T13:34:39.030000000Z",
                        "active_until": None,
                        "attribute_type": "record-reference",
                    }
                ],
            },
            "created_at": "2024-02-01T14:00:00.000Z",
            "updated_at": "2024-03-15T10:00:00.000Z",
        }

        artifact = AttioDealArtifact.from_api_response(
            record_data=record_with_company,
            ingest_job_id=job_id,
        )
        document = AttioDealDocument.from_artifact(artifact)

        content = document.get_content()

        # Should show company name
        assert "Acme Corporation" in content
        # Should NOT show the raw UUID
        assert "208ce7c6-0b6d-4635-bcef-e4fa4491a1b3" not in content
