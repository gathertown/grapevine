"""Tests for Notion pruner functionality."""

import pytest

from connectors.notion import NotionPruner, notion_pruner

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


class TestNotionPruner:
    """Test suite for Notion pruner functionality."""

    def test_singleton_pattern(self):
        """Test that NotionPruner follows singleton pattern."""
        pruner1 = NotionPruner()
        pruner2 = NotionPruner()

        assert pruner1 is pruner2
        assert pruner1 is notion_pruner

    @pytest.mark.asyncio
    async def test_delete_page_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Notion page deletion with referrer updates."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup complete successful scenario with artifacts and referrer updates
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=2)
        MockHelper.setup_document_with_references(
            pool, reference_id="notion_page_ref_456", referenced_docs={"doc3": 1, "doc4": 3}
        )
        MockHelper.setup_referrer_updates(
            mock_deletion_dependencies,
            referrer_updates=[{"doc_id": "doc3", "count": -1}, {"doc_id": "doc4", "count": -3}],
        )

        pruner = NotionPruner()
        result = await pruner.delete_page(
            page_id="abc123def456ghi789",
            tenant_id="tenant456",
            db_pool=pool,
        )

        assert result is True

        # Verify the complete end-to-end deletion flow:
        expected_document_id = "notion_page_abc123def456ghi789"  # Based on get_notion_doc_id format

        # 1. Artifacts were deleted (2 artifacts)
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "notion_page",
            "abc123def456ghi789",
        )

        # 2. Referrer updates were prepared with the document's references
        mock_deletion_dependencies["prepare_referrer_updates"].assert_called_once_with(
            "notion_page_ref_456", {"doc3": 1, "doc4": 3}, conn
        )

        # 3. Referrer updates were applied to database with expected updates
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_called_once_with(
            [{"doc_id": "doc3", "count": -1}, {"doc_id": "doc4", "count": -3}], conn
        )

        # 4. Document was deleted from database
        conn.execute.assert_called_with("DELETE FROM documents WHERE id = $1", expected_document_id)

        # 5. Referrer updates were applied to OpenSearch with expected parameters
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_called_once_with(
            [{"doc_id": "doc3", "count": -1}, {"doc_id": "doc4", "count": -3}],
            "tenant456",
            opensearch_client,
        )

        # 6. Document was deleted from OpenSearch with proper tenant prefix
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant456", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_page_no_document_found(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion when document doesn't exist in database."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup scenario where no document is found
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=0)
        MockHelper.setup_no_document_found(conn)

        pruner = NotionPruner()
        result = await pruner.delete_page(
            page_id="nonexistent123",
            tenant_id="tenant456",
            db_pool=pool,
        )

        assert result is True  # Should still succeed

        expected_document_id = "notion_page_nonexistent123"

        # Verify basic flow when document doesn't exist:
        # 1. Artifacts were still attempted to be deleted
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "notion_page",
            "nonexistent123",
        )

        # 2. No referrer updates should have been prepared (no document found)
        mock_deletion_dependencies["prepare_referrer_updates"].assert_not_called()

        # 3. No referrer updates should have been applied
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_not_called()
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_not_called()

        # 4. OpenSearch deletion should still be attempted (cleanup)
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant456", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_page_empty_page_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty page_id."""
        pool, _ = mock_db_pool_fixture

        pruner = NotionPruner()
        result = await pruner.delete_page(
            page_id="",
            tenant_id="tenant456",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_page_empty_tenant_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty tenant_id."""
        pool, _ = mock_db_pool_fixture

        pruner = NotionPruner()
        result = await pruner.delete_page(
            page_id="abc123def456ghi789",
            tenant_id="",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_page_handles_database_error(self, mock_db_pool_fixture):
        """Test deletion handles database errors gracefully."""
        pool, conn = mock_db_pool_fixture

        # Setup database error
        MockHelper.setup_database_error(conn)

        pruner = NotionPruner()
        result = await pruner.delete_page(
            page_id="abc123def456ghi789",
            tenant_id="tenant456",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_page_with_uuid_format(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion with UUID-style page ID (common Notion format)."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = NotionPruner()
        result = await pruner.delete_page(
            page_id="f47ac10b-58cc-4372-a567-0e02b2c3d479",
            tenant_id="tenant456",
            db_pool=pool,
        )

        assert result is True

        # Verify UUID format is preserved in entity_id and document_id
        expected_entity_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
        expected_document_id = "notion_page_f47ac10b-58cc-4372-a567-0e02b2c3d479"

        # Verify artifact deletion with UUID
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "notion_page",
            expected_entity_id,
        )

        # Verify OpenSearch deletion with UUID
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant456", expected_document_id
        )
