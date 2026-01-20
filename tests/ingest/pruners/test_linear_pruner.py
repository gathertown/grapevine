"""Tests for Linear pruner functionality."""

import pytest

from connectors.linear import LinearPruner, linear_pruner

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


class TestLinearPruner:
    """Test suite for Linear pruner functionality."""

    def test_singleton_pattern(self):
        """Test that LinearPruner follows singleton pattern."""
        pruner1 = LinearPruner()
        pruner2 = LinearPruner()

        assert pruner1 is pruner2
        assert pruner1 is linear_pruner

    @pytest.mark.asyncio
    async def test_delete_issue_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Linear issue deletion with referrer updates."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup complete successful scenario with artifacts and referrer updates
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_document_with_references(
            pool, reference_id="linear_issue_ref_789", referenced_docs={"doc5": 2, "doc6": 1}
        )
        MockHelper.setup_referrer_updates(
            mock_deletion_dependencies,
            referrer_updates=[{"doc_id": "doc5", "count": -2}, {"doc_id": "doc6", "count": -1}],
        )

        pruner = LinearPruner()
        result = await pruner.delete_issue(
            issue_id="PROJ-123",
            tenant_id="tenant789",
            db_pool=pool,
        )

        assert result is True

        # Verify the complete end-to-end deletion flow:
        expected_document_id = "issue_PROJ-123"  # Based on get_linear_doc_id format

        # 1. Artifacts were deleted (1 artifact)
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "linear_issue",
            "PROJ-123",
        )

        # 2. Referrer updates were prepared with the document's references
        mock_deletion_dependencies["prepare_referrer_updates"].assert_called_once_with(
            "linear_issue_ref_789", {"doc5": 2, "doc6": 1}, conn
        )

        # 3. Referrer updates were applied to database with expected updates
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_called_once_with(
            [{"doc_id": "doc5", "count": -2}, {"doc_id": "doc6", "count": -1}], conn
        )

        # 4. Document was deleted from database
        conn.execute.assert_called_with("DELETE FROM documents WHERE id = $1", expected_document_id)

        # 5. Referrer updates were applied to OpenSearch with expected parameters
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_called_once_with(
            [{"doc_id": "doc5", "count": -2}, {"doc_id": "doc6", "count": -1}],
            "tenant789",
            opensearch_client,
        )

        # 6. Document was deleted from OpenSearch with proper tenant prefix
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant789", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_issue_no_document_found(
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

        pruner = LinearPruner()
        result = await pruner.delete_issue(
            issue_id="NONEXISTENT-999",
            tenant_id="tenant789",
            db_pool=pool,
        )

        assert result is True  # Should still succeed

        expected_document_id = "issue_NONEXISTENT-999"

        # Verify basic flow when document doesn't exist:
        # 1. Artifacts were still attempted to be deleted
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "linear_issue",
            "NONEXISTENT-999",
        )

        # 2. No referrer updates should have been prepared (no document found)
        mock_deletion_dependencies["prepare_referrer_updates"].assert_not_called()

        # 3. No referrer updates should have been applied
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_not_called()
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_not_called()

        # 4. OpenSearch deletion should still be attempted (cleanup)
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant789", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_issue_empty_issue_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty issue_id."""
        pool, _ = mock_db_pool_fixture

        pruner = LinearPruner()
        result = await pruner.delete_issue(
            issue_id="",
            tenant_id="tenant789",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_issue_empty_tenant_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty tenant_id."""
        pool, _ = mock_db_pool_fixture

        pruner = LinearPruner()
        result = await pruner.delete_issue(
            issue_id="PROJ-123",
            tenant_id="",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_issue_handles_database_error(self, mock_db_pool_fixture):
        """Test deletion handles database errors gracefully."""
        pool, conn = mock_db_pool_fixture

        # Setup database error
        MockHelper.setup_database_error(conn)

        pruner = LinearPruner()
        result = await pruner.delete_issue(
            issue_id="PROJ-123",
            tenant_id="tenant789",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_issue_with_special_characters(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion with special characters in issue ID."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = LinearPruner()
        result = await pruner.delete_issue(
            issue_id="MY-PROJECT_2024-456",
            tenant_id="tenant789",
            db_pool=pool,
        )

        assert result is True

        # Verify special characters are preserved in entity_id and document_id
        expected_entity_id = "MY-PROJECT_2024-456"
        expected_document_id = "issue_MY-PROJECT_2024-456"

        # Verify artifact deletion with special characters
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "linear_issue",
            expected_entity_id,
        )

        # Verify OpenSearch deletion with special characters
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant789", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_issue_with_uuid_style_id(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion with UUID-style issue ID (some Linear issues use UUIDs)."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=2)
        MockHelper.setup_no_document_found(conn)

        pruner = LinearPruner()
        result = await pruner.delete_issue(
            issue_id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            tenant_id="tenant789",
            db_pool=pool,
        )

        assert result is True

        # Verify UUID format is preserved
        expected_entity_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        expected_document_id = "issue_a1b2c3d4-e5f6-7890-abcd-ef1234567890"

        # Verify artifact deletion with UUID
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "linear_issue",
            expected_entity_id,
        )

        # Verify OpenSearch deletion with UUID
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant789", expected_document_id
        )
