"""Tests for GitHub PR pruner functionality."""

import pytest

from connectors.github import GitHubPRPruner, github_pr_pruner

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


class TestGitHubPRPruner:
    """Test suite for GitHub PR pruner functionality."""

    def test_singleton_pattern(self):
        """Test that GitHubPRPruner follows singleton pattern."""
        pruner1 = GitHubPRPruner()
        pruner2 = GitHubPRPruner()

        assert pruner1 is pruner2
        assert pruner1 is github_pr_pruner

    @pytest.mark.asyncio
    async def test_delete_pr_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end GitHub PR deletion with referrer updates."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup complete successful scenario with artifacts and referrer updates
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=5)
        MockHelper.setup_document_with_references(
            pool,
            reference_id="github_pr_ref_789",
            referenced_docs={"doc11": 3, "doc12": 1, "doc13": 2},
        )
        MockHelper.setup_referrer_updates(
            mock_deletion_dependencies,
            referrer_updates=[
                {"doc_id": "doc11", "count": -3},
                {"doc_id": "doc12", "count": -1},
                {"doc_id": "doc13", "count": -2},
            ],
        )

        pruner = GitHubPRPruner()
        result = await pruner.delete_pr(
            repo_id="12345678",
            pr_number=456,
            tenant_id="tenant-github-pr",
            db_pool=pool,
        )

        assert result is True

        # Verify the complete end-to-end deletion flow:
        expected_entity_id = "12345678_pr_456"
        expected_document_id = "12345678_pr_456"  # Based on get_github_pr_doc_id format

        # 1. Artifacts were deleted (5 artifacts)
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "github_pr",
            expected_entity_id,
        )

        # 2. Referrer updates were prepared with the document's references
        mock_deletion_dependencies["prepare_referrer_updates"].assert_called_once_with(
            "github_pr_ref_789", {"doc11": 3, "doc12": 1, "doc13": 2}, conn
        )

        # 3. Referrer updates were applied to database with expected updates
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_called_once_with(
            [
                {"doc_id": "doc11", "count": -3},
                {"doc_id": "doc12", "count": -1},
                {"doc_id": "doc13", "count": -2},
            ],
            conn,
        )

        # 4. Document was deleted from database
        conn.execute.assert_called_with("DELETE FROM documents WHERE id = $1", expected_document_id)

        # 5. Referrer updates were applied to OpenSearch with expected parameters
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_called_once_with(
            [
                {"doc_id": "doc11", "count": -3},
                {"doc_id": "doc12", "count": -1},
                {"doc_id": "doc13", "count": -2},
            ],
            "tenant-github-pr",
            opensearch_client,
        )

        # 6. Document was deleted from OpenSearch with proper tenant prefix
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-github-pr", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_pr_no_document_found(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion when document doesn't exist in database."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup scenario where no document is found
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=2)
        MockHelper.setup_no_document_found(conn)

        pruner = GitHubPRPruner()
        result = await pruner.delete_pr(
            repo_id="87654321",
            pr_number=999,
            tenant_id="tenant-github-pr",
            db_pool=pool,
        )

        assert result is True  # Should still succeed

        expected_entity_id = "87654321_pr_999"
        expected_document_id = "87654321_pr_999"

        # Verify basic flow when document doesn't exist:
        # 1. Artifacts were still attempted to be deleted
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "github_pr",
            expected_entity_id,
        )

        # 2. No referrer updates should have been prepared (no document found)
        mock_deletion_dependencies["prepare_referrer_updates"].assert_not_called()

        # 3. No referrer updates should have been applied
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_not_called()
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_not_called()

        # 4. OpenSearch deletion should still be attempted (cleanup)
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-github-pr", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_pr_invalid_repo_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty repo_id."""
        pool, _ = mock_db_pool_fixture

        pruner = GitHubPRPruner()
        result = await pruner.delete_pr(
            repo_id="",
            pr_number=123,
            tenant_id="tenant-github-pr",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_pr_invalid_pr_number(self, mock_db_pool_fixture):
        """Test deletion fails with invalid PR numbers."""
        pool, _ = mock_db_pool_fixture
        pruner = GitHubPRPruner()

        # Test zero PR number
        result = await pruner.delete_pr(
            repo_id="12345678",
            pr_number=0,
            tenant_id="tenant-github-pr",
            db_pool=pool,
        )
        assert result is False

        # Test negative PR number
        result = await pruner.delete_pr(
            repo_id="12345678",
            pr_number=-1,
            tenant_id="tenant-github-pr",
            db_pool=pool,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_pr_empty_tenant_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty tenant_id."""
        pool, _ = mock_db_pool_fixture

        pruner = GitHubPRPruner()
        result = await pruner.delete_pr(
            repo_id="12345678",
            pr_number=123,
            tenant_id="",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_pr_handles_database_error(self, mock_db_pool_fixture):
        """Test deletion handles database errors gracefully."""
        pool, conn = mock_db_pool_fixture

        # Setup database error
        MockHelper.setup_database_error(conn)

        pruner = GitHubPRPruner()
        result = await pruner.delete_pr(
            repo_id="12345678",
            pr_number=123,
            tenant_id="tenant-github-pr",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_pr_with_large_pr_number(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion with large PR number (edge case)."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=3)
        MockHelper.setup_no_document_found(conn)

        pruner = GitHubPRPruner()
        result = await pruner.delete_pr(
            repo_id="98765432",
            pr_number=999999,
            tenant_id="tenant-github-pr",
            db_pool=pool,
        )

        assert result is True

        # Verify large numbers are handled correctly
        expected_entity_id = "98765432_pr_999999"
        expected_document_id = "98765432_pr_999999"

        # Verify artifact deletion with large PR number
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "github_pr",
            expected_entity_id,
        )

        # Verify OpenSearch deletion with large PR number
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-github-pr", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_pr_with_long_repo_id(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion with long repository ID."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = GitHubPRPruner()
        result = await pruner.delete_pr(
            repo_id="123456789012345678901234567890",
            pr_number=42,
            tenant_id="tenant-github-pr",
            db_pool=pool,
        )

        assert result is True

        # Verify long repo ID is handled correctly
        expected_entity_id = "123456789012345678901234567890_pr_42"
        expected_document_id = "123456789012345678901234567890_pr_42"

        # Verify artifact deletion with long repo ID
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "github_pr",
            expected_entity_id,
        )

        # Verify OpenSearch deletion with long repo ID
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-github-pr", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_pr_constructs_correct_ids(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test that entity_id and document_id are constructed correctly."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=2)
        MockHelper.setup_no_document_found(conn)

        pruner = GitHubPRPruner()
        await pruner.delete_pr(
            repo_id="555666777",
            pr_number=1001,
            tenant_id="tenant-github-pr",
            db_pool=pool,
        )

        # Verify correct ID construction: {repo_id}_pr_{pr_number}
        expected_entity_id = "555666777_pr_1001"
        expected_document_id = "555666777_pr_1001"

        # Should be used for artifact deletion
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "github_pr",
            expected_entity_id,
        )

        # Should be used for OpenSearch deletion
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-github-pr", expected_document_id
        )
