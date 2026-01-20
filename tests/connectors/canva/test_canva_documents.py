"""Tests for Canva document models."""

from uuid import uuid4

import pytest

from connectors.base.document_source import DocumentSource
from connectors.canva.canva_documents import CanvaDesignDocument
from connectors.canva.canva_models import CanvaDesignArtifact


@pytest.fixture
def job_id():
    """Create a test job ID."""
    return uuid4()


@pytest.fixture
def mock_design_data():
    """Complete mock Canva design data."""
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
    """Minimal mock Canva design data."""
    return {
        "id": "DAGq1K2xyz789",
        "title": "Simple Design",
        "created_at": 1704067200,
    }


class TestCanvaDesignDocument:
    """Test suite for CanvaDesignDocument."""

    def test_from_artifact_basic(self, mock_design_data, job_id):
        """Test creating document from design artifact."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )

        document = CanvaDesignDocument.from_artifact(artifact)

        assert document.id == "canva_design_DAGq1K2abc123"

    def test_from_artifact_raw_data(self, mock_design_data, job_id):
        """Test that raw_data contains expected fields."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )

        document = CanvaDesignDocument.from_artifact(artifact)

        assert document.raw_data["design_id"] == "DAGq1K2abc123"
        assert document.raw_data["title"] == "Marketing Banner"
        assert document.raw_data["edit_url"] == "https://www.canva.com/design/DAGq1K2abc123/edit"
        assert document.raw_data["page_count"] == 5

    def test_get_content(self, mock_design_data, job_id):
        """Test document content contains design info."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Marketing Banner" in content
        assert "Canva Design:" in content
        assert "Pages: 5" in content

    def test_get_content_includes_timestamps(self, mock_design_data, job_id):
        """Test document content includes formatted timestamps."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        content = document.get_content()

        # Timestamps are formatted in local time, so just check they exist
        assert "Created:" in content
        assert "Last Modified:" in content
        # Should contain year and time format
        assert "2024" in content or "2023" in content  # Timezone may shift date

    def test_get_content_minimal_design(self, mock_minimal_design_data, job_id):
        """Test content generation with minimal design data."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_minimal_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        content = document.get_content()

        assert "Simple Design" in content
        # Should not include Pages if page_count is None
        assert "Pages:" not in content or "Pages: None" not in content

    def test_to_embedding_chunks(self, mock_design_data, job_id):
        """Test document generates embedding chunks."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()

        assert len(chunks) >= 1
        # Chunk should contain design title
        all_content = " ".join(chunk.get_content() for chunk in chunks)
        assert "Marketing Banner" in all_content

    def test_chunk_contains_document_id(self, mock_design_data, job_id):
        """Test chunks contain document ID for citation."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()
        chunk_content = chunks[0].get_content()

        # Should contain document ID prefix for citation resolver
        assert "[canva_design_" in chunk_content

    def test_chunk_metadata(self, mock_design_data, job_id):
        """Test chunk metadata is populated correctly."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        chunks = document.to_embedding_chunks()
        metadata = chunks[0].get_metadata()

        assert metadata["design_id"] == "DAGq1K2abc123"
        assert metadata["design_title"] == "Marketing Banner"
        assert metadata["chunk_type"] == "design"
        assert metadata["source"] == "canva_design"

    def test_get_reference_id(self, mock_design_data, job_id):
        """Test reference ID format."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        ref_id = document.get_reference_id()

        assert ref_id == "r_canva_design_DAGq1K2abc123"
        assert ref_id.startswith("r_canva_design_")

    def test_get_source_enum(self, mock_design_data, job_id):
        """Test source enum is correct."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        assert document.get_source_enum() == DocumentSource.CANVA_DESIGN

    def test_get_metadata_includes_type(self, mock_design_data, job_id):
        """Test metadata includes correct type field."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        assert metadata["type"] == "canva_design"
        assert metadata["source"] == "canva_design"

    def test_get_metadata_includes_design_info(self, mock_design_data, job_id):
        """Test metadata includes design-specific fields."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        assert metadata["design_id"] == "DAGq1K2abc123"
        assert metadata["design_title"] == "Marketing Banner"
        assert metadata["owner_user_id"] == "user_123"
        assert metadata["owner_team_id"] == "team_456"
        assert metadata["page_count"] == 5

    def test_get_metadata_includes_urls(self, mock_design_data, job_id):
        """Test metadata includes URL fields."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        assert metadata["edit_url"] == "https://www.canva.com/design/DAGq1K2abc123/edit"
        assert metadata["view_url"] == "https://www.canva.com/design/DAGq1K2abc123/view"
        assert metadata["thumbnail_url"] == "https://example.com/thumb.png"

    def test_get_metadata_formats_timestamps(self, mock_design_data, job_id):
        """Test metadata formats timestamps as ISO strings."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        # Unix timestamps should be converted to ISO format
        # Timezone may shift date, so just check format
        assert metadata["source_created_at"] is not None
        assert "T" in metadata["source_created_at"]  # ISO format
        assert metadata["source_updated_at"] is not None
        assert "T" in metadata["source_updated_at"]  # ISO format

    def test_permission_policy_default(self, mock_design_data, job_id):
        """Test default permission policy is tenant-wide."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )

        document = CanvaDesignDocument.from_artifact(artifact)

        assert document.permission_policy == "tenant"
        assert document.permission_allowed_tokens is None

    def test_permission_policy_private(self, mock_design_data, job_id):
        """Test private permission policy with valid email tokens."""
        artifact = CanvaDesignArtifact.from_api_response(
            design_data=mock_design_data,
            ingest_job_id=job_id,
        )

        # Base document requires tokens prefixed with "e:" for email-based permissions
        document = CanvaDesignDocument.from_artifact(
            artifact,
            permission_policy="private",
            permission_allowed_tokens=["e:user@example.com", "e:admin@example.com"],
        )

        assert document.permission_policy == "private"
        assert document.permission_allowed_tokens == ["e:user@example.com", "e:admin@example.com"]


class TestCanvaDesignDocumentEdgeCases:
    """Test edge cases for CanvaDesignDocument."""

    def test_handles_none_timestamps_in_metadata(self, job_id):
        """Test metadata handles None timestamps gracefully."""
        design_data = {
            "id": "DAGq1K2test",
            "title": "No Timestamps Design",
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        metadata = document.get_metadata()

        # Should not crash, timestamps should be None
        assert metadata["source_created_at"] is None
        assert metadata["source_updated_at"] is None

    def test_handles_invalid_timestamps_in_content(self, job_id):
        """Test content handles invalid timestamps gracefully."""
        design_data = {
            "id": "DAGq1K2test",
            "title": "Bad Timestamp Design",
            "created_at": -999999999999999,  # Invalid timestamp
        }

        artifact = CanvaDesignArtifact.from_api_response(
            design_data=design_data,
            ingest_job_id=job_id,
        )
        document = CanvaDesignDocument.from_artifact(artifact)

        # Should not crash, should use fallback
        content = document.get_content()
        assert "Bad Timestamp Design" in content
