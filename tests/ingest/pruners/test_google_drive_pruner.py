"""Tests for Google Drive pruner functionality."""

import pytest

from connectors.google_drive import GoogleDrivePruner, google_drive_pruner

from .mock_utils import (
    MockHelper,
    create_mock_db_pool,
    mock_deletion_dependencies,  # noqa: F401 - Used as pytest fixture
    mock_opensearch_manager,  # noqa: F401 - Used as pytest fixture
)


@pytest.fixture
def mock_db_pool_fixture():
    """Fixture for mock database pool."""
    return create_mock_db_pool()


class TestGoogleDrivePruner:
    """Test suite for Google Drive pruner functionality."""

    def test_singleton_pattern(self):
        """Test that GoogleDrivePruner follows singleton pattern."""
        pruner1 = GoogleDrivePruner()
        pruner2 = GoogleDrivePruner()

        assert pruner1 is pruner2
        assert pruner1 is google_drive_pruner

    @pytest.mark.asyncio
    async def test_delete_file_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Google Drive file deletion with referrer updates."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup complete successful scenario with artifacts and referrer updates
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=3)
        MockHelper.setup_document_with_references(
            pool,
            reference_id="gdrive_file_ref_456",
            referenced_docs={"doc8": 2, "doc9": 1, "doc10": 3},
        )
        MockHelper.setup_referrer_updates(
            mock_deletion_dependencies,
            referrer_updates=[
                {"doc_id": "doc8", "count": -2},
                {"doc_id": "doc9", "count": -1},
                {"doc_id": "doc10", "count": -3},
            ],
        )

        pruner = GoogleDrivePruner()
        result = await pruner.delete_file(
            file_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            tenant_id="tenant-gdrive",
            db_pool=pool,
        )

        assert result is True

        # Verify the complete end-to-end deletion flow:
        expected_document_id = "google_drive_file_1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"  # Based on get_google_drive_doc_id format

        # 1. Artifacts were deleted (3 artifacts)
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "google_drive_file",
            "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
        )

        # 2. Referrer updates were prepared with the document's references
        mock_deletion_dependencies["prepare_referrer_updates"].assert_called_once_with(
            "gdrive_file_ref_456", {"doc8": 2, "doc9": 1, "doc10": 3}, conn
        )

        # 3. Referrer updates were applied to database with expected updates
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_called_once_with(
            [
                {"doc_id": "doc8", "count": -2},
                {"doc_id": "doc9", "count": -1},
                {"doc_id": "doc10", "count": -3},
            ],
            conn,
        )

        # 4. Document was deleted from database
        conn.execute.assert_called_with("DELETE FROM documents WHERE id = $1", expected_document_id)

        # 5. Referrer updates were applied to OpenSearch with expected parameters
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_called_once_with(
            [
                {"doc_id": "doc8", "count": -2},
                {"doc_id": "doc9", "count": -1},
                {"doc_id": "doc10", "count": -3},
            ],
            "tenant-gdrive",
            opensearch_client,
        )

        # 6. Document was deleted from OpenSearch with proper tenant prefix
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-gdrive", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_file_no_document_found(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion when document doesn't exist in database."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup scenario where no document is found
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = GoogleDrivePruner()
        result = await pruner.delete_file(
            file_id="1NonExistentFileId123",
            tenant_id="tenant-gdrive",
            db_pool=pool,
        )

        assert result is True  # Should still succeed

        expected_document_id = "google_drive_file_1NonExistentFileId123"

        # Verify basic flow when document doesn't exist:
        # 1. Artifacts were still attempted to be deleted
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "google_drive_file",
            "1NonExistentFileId123",
        )

        # 2. No referrer updates should have been prepared (no document found)
        mock_deletion_dependencies["prepare_referrer_updates"].assert_not_called()

        # 3. No referrer updates should have been applied
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_not_called()
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_not_called()

        # 4. OpenSearch deletion should still be attempted (cleanup)
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-gdrive", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_file_empty_file_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty file_id."""
        pool, _ = mock_db_pool_fixture

        pruner = GoogleDrivePruner()
        result = await pruner.delete_file(
            file_id="",
            tenant_id="tenant-gdrive",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_file_empty_tenant_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty tenant_id."""
        pool, _ = mock_db_pool_fixture

        pruner = GoogleDrivePruner()
        result = await pruner.delete_file(
            file_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            tenant_id="",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_file_handles_database_error(self, mock_db_pool_fixture):
        """Test deletion handles database errors gracefully."""
        pool, conn = mock_db_pool_fixture

        # Setup database error
        MockHelper.setup_database_error(conn)

        pruner = GoogleDrivePruner()
        result = await pruner.delete_file(
            file_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
            tenant_id="tenant-gdrive",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_file_with_short_file_id(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion with shorter Google Drive file ID (some files have shorter IDs)."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = GoogleDrivePruner()
        result = await pruner.delete_file(
            file_id="1a2B3c4D5e6F",
            tenant_id="tenant-gdrive",
            db_pool=pool,
        )

        assert result is True

        # Verify file ID is preserved
        expected_entity_id = "1a2B3c4D5e6F"
        expected_document_id = "google_drive_file_1a2B3c4D5e6F"

        # Verify artifact deletion with short file ID
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "google_drive_file",
            expected_entity_id,
        )

        # Verify OpenSearch deletion with short file ID
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-gdrive", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_file_with_special_characters_in_file_id(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion with special characters in file ID (edge case)."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario with no artifacts
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=0)
        MockHelper.setup_no_document_found(conn)

        pruner = GoogleDrivePruner()
        result = await pruner.delete_file(
            file_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms-test_file",
            tenant_id="tenant-gdrive",
            db_pool=pool,
        )

        assert result is True

        # Verify special characters are preserved in file ID
        expected_entity_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms-test_file"
        expected_document_id = (
            "google_drive_file_1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms-test_file"
        )

        # Verify artifact deletion attempt with special characters
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "google_drive_file",
            expected_entity_id,
        )

        # Verify OpenSearch deletion with special characters
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-gdrive", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_file_typical_google_docs_file(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion with typical Google Docs file ID format."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=2)
        MockHelper.setup_no_document_found(conn)

        pruner = GoogleDrivePruner()
        result = await pruner.delete_file(
            file_id="1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHI",
            tenant_id="tenant-gdrive",
            db_pool=pool,
        )

        assert result is True

        # Verify typical Google file ID format is handled
        expected_entity_id = "1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHI"
        expected_document_id = "google_drive_file_1234567890abcdefghijklmnopqrstuvwxyzABCDEFGHI"

        # Verify artifact deletion with typical Google file ID
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "google_drive_file",
            expected_entity_id,
        )

        # Verify OpenSearch deletion with typical Google file ID
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-gdrive", expected_document_id
        )
