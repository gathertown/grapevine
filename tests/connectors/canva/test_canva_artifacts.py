"""Tests for Canva artifact models."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from connectors.base.base_ingest_artifact import ArtifactEntity
from connectors.canva.canva_models import CanvaDesignArtifact


@pytest.fixture
def job_id() -> UUID:
    """Create a test job ID."""
    return uuid4()


@pytest.fixture
def mock_design_data():
    """Mock Canva design data from API."""
    return {
        "id": "DAGq1K2abc123",
        "title": "Marketing Banner",
        "owner": {"user_id": "user_123", "team_id": "team_456"},
        "urls": {
            "edit_url": "https://www.canva.com/design/DAGq1K2abc123/edit",
            "view_url": "https://www.canva.com/design/DAGq1K2abc123/view",
        },
        "created_at": 1704067200,  # 2024-01-01 00:00:00 UTC
        "updated_at": 1706745600,  # 2024-02-01 00:00:00 UTC
        "thumbnail": {
            "width": 200,
            "height": 150,
            "url": "https://example.com/thumb.png",
        },
        "page_count": 5,
    }


@pytest.fixture
def mock_minimal_design_data():
    """Mock minimal Canva design data."""
    return {
        "id": "DAGq1K2xyz789",
        "title": "Untitled Design",
        "created_at": 1704067200,
    }


class TestCanvaDesignArtifact:
    """Test suite for CanvaDesignArtifact."""

    def test_from_api_response_basic(self, mock_design_data, job_id):
        """Test creating artifact from complete design data."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )

        assert artifact.entity == ArtifactEntity.CANVA_DESIGN
        assert artifact.entity_id == "canva_design_DAGq1K2abc123"
        assert artifact.metadata.design_id == "DAGq1K2abc123"
        assert artifact.metadata.owner_user_id == "user_123"
        assert artifact.metadata.owner_team_id == "team_456"
        assert artifact.metadata.page_count == 5

    def test_from_api_response_content_fields(self, mock_design_data, job_id):
        """Test that content contains all expected fields."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )

        content = artifact.content
        assert content["design_id"] == "DAGq1K2abc123"
        assert content["title"] == "Marketing Banner"
        assert content["edit_url"] == "https://www.canva.com/design/DAGq1K2abc123/edit"
        assert content["view_url"] == "https://www.canva.com/design/DAGq1K2abc123/view"
        assert content["thumbnail_url"] == "https://example.com/thumb.png"
        assert content["thumbnail_width"] == 200
        assert content["thumbnail_height"] == 150
        assert content["page_count"] == 5

    def test_from_api_response_parses_updated_at_timestamp(self, mock_design_data, job_id):
        """Test that updated_at timestamp is properly parsed."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )

        # 1706745600 = 2024-02-01 00:00:00 UTC
        assert artifact.source_updated_at == datetime(2024, 2, 1, 0, 0, 0, tzinfo=UTC)

    def test_from_api_response_uses_created_at_when_no_updated_at(self, job_id):
        """Test fallback to created_at when updated_at is missing."""
        design_data = {
            "id": "DAGq1K2test",
            "created_at": 1704067200,  # 2024-01-01 00:00:00 UTC
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )

        # 1704067200 = 2024-01-01 00:00:00 UTC
        assert artifact.source_updated_at == datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

    def test_from_api_response_uses_current_time_when_no_timestamps(self, job_id):
        """Test fallback to current time when both timestamps missing."""
        design_data = {
            "id": "DAGq1K2test",
        }

        before = datetime.now(UTC)
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )
        after = datetime.now(UTC)

        assert before <= artifact.source_updated_at <= after

    def test_from_api_response_handles_null_owner(self, job_id):
        """Test handling when owner is None."""
        design_data = {
            "id": "DAGq1K2test",
            "title": "Test Design",
            "owner": None,
            "created_at": 1704067200,
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.owner_user_id is None
        assert artifact.metadata.owner_team_id is None

    def test_from_api_response_handles_missing_owner(self, job_id):
        """Test handling when owner field is missing entirely."""
        design_data = {
            "id": "DAGq1K2test",
            "title": "Test Design",
            "created_at": 1704067200,
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )

        assert artifact.metadata.owner_user_id is None
        assert artifact.metadata.owner_team_id is None

    def test_from_api_response_handles_null_urls(self, job_id):
        """Test handling when urls is None."""
        design_data = {
            "id": "DAGq1K2test",
            "urls": None,
            "created_at": 1704067200,
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )

        assert artifact.content["edit_url"] is None
        assert artifact.content["view_url"] is None

    def test_from_api_response_handles_null_thumbnail(self, job_id):
        """Test handling when thumbnail is None."""
        design_data = {
            "id": "DAGq1K2test",
            "thumbnail": None,
            "created_at": 1704067200,
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )

        assert artifact.content["thumbnail_url"] is None
        assert artifact.content["thumbnail_width"] is None

    def test_from_api_response_default_title(self, job_id):
        """Test default title when not provided."""
        design_data = {
            "id": "DAGq1K2test",
            "created_at": 1704067200,
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )

        assert artifact.content["title"] == "Untitled Design"

    def test_from_api_response_handles_invalid_timestamp(self, job_id):
        """Test handling of invalid timestamp values."""
        design_data = {
            "id": "DAGq1K2test",
            "updated_at": "invalid",  # Not a valid timestamp
            "created_at": "also_invalid",
        }

        before = datetime.now(UTC)
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )
        after = datetime.now(UTC)

        # Should fall back to current time
        assert before <= artifact.source_updated_at <= after


class TestCanvaDesignArtifactEntityId:
    """Test suite for entity ID generation."""

    def test_entity_id_format(self, mock_design_data, job_id):
        """Test entity ID has correct format."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )

        # Entity ID should be prefixed
        assert artifact.entity_id == "canva_design_DAGq1K2abc123"
        assert artifact.entity_id.startswith("canva_design_")

    def test_entity_id_empty_design_id(self, job_id):
        """Test entity ID with empty design ID."""
        design_data = {
            "id": "",
            "created_at": 1704067200,
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )

        assert artifact.entity_id == "canva_design_"

    def test_entity_id_missing_design_id(self, job_id):
        """Test entity ID when design ID is missing."""
        design_data = {
            "created_at": 1704067200,
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )

        assert artifact.entity_id == "canva_design_"
