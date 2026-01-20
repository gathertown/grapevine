"""Tests for GitHub pruner functionality."""

import pytest

from connectors.github import GitHubPruner, github_pruner

from .mock_utils import (
    MockHelper,
    create_mock_db_pool,
    mock_deletion_dependencies,  # noqa: F401 - Used as pytest fixture
    mock_opensearch_manager,  # noqa: F401 - Used as pytest fixture
    mock_tenant_opensearch_manager_decorator,
)


@pytest.fixture
def mock_db_pool_fixture():
    """Fixture for mock database pool."""
    return create_mock_db_pool()


class TestGitHubPruner:
    """Test suite for GitHub pruner functionality."""

    def test_singleton_pattern(self):
        """Test that GitHubPruner follows singleton pattern."""
        pruner1 = GitHubPruner()
        pruner2 = GitHubPruner()

        assert pruner1 is pruner2
        assert pruner1 is github_pruner

    @pytest.mark.asyncio
    async def test_delete_file_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end GitHub file deletion with referrer updates."""
        pool, conn = mock_db_pool_fixture
        opensearch_mgr, opensearch_client = mock_opensearch_manager

        # Setup complete successful scenario with multiple artifacts and referrer updates
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=3)
        MockHelper.setup_document_with_references(
            pool, reference_id="github_file_ref_123", referenced_docs={"doc1": 2, "doc2": 1}
        )
        MockHelper.setup_referrer_updates(
            mock_deletion_dependencies,
            referrer_updates=[{"doc_id": "doc1", "count": -2}, {"doc_id": "doc2", "count": -1}],
        )

        pruner = GitHubPruner()
        result = await pruner.delete_file(
            file_path="src/utils/helper.ts",
            repo_name="frontend-app",
            organization="acme-corp",
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is True

        # Verify the complete end-to-end deletion flow:
        entity_id = "acme-corp/frontend-app/src/utils/helper.ts"
        expected_document_id = f"github_file_{entity_id}"

        # 1. Artifacts were deleted (3 artifacts)
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "github_file",
            entity_id,
        )

        # 2. Referrer updates were prepared with the document's references
        mock_deletion_dependencies["prepare_referrer_updates"].assert_called_once_with(
            "github_file_ref_123", {"doc1": 2, "doc2": 1}, conn
        )

        # 3. Referrer updates were applied to database with expected updates
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_called_once_with(
            [{"doc_id": "doc1", "count": -2}, {"doc_id": "doc2", "count": -1}], conn
        )

        # 4. Document was deleted from database
        conn.execute.assert_called_with("DELETE FROM documents WHERE id = $1", expected_document_id)

        # 5. Referrer updates were applied to OpenSearch with expected parameters
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_called_once_with(
            [{"doc_id": "doc1", "count": -2}, {"doc_id": "doc2", "count": -1}],
            "tenant123",
            opensearch_client,
        )

        # 6. Document was deleted from OpenSearch with proper tenant prefix
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant123", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_file_no_document_found(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test deletion when document doesn't exist in database."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup scenario where no document is found
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = GitHubPruner()
        result = await pruner.delete_file(
            file_path="nonexistent/file.py",
            repo_name="test-repo",
            organization="test-org",
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is True  # Should still succeed

        entity_id = "test-org/test-repo/nonexistent/file.py"
        expected_document_id = f"github_file_{entity_id}"

        # Verify basic flow when document doesn't exist:
        # 1. Artifacts were still deleted
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "github_file",
            entity_id,
        )

        # 3. No referrer updates should have been prepared (no document found)
        mock_deletion_dependencies["prepare_referrer_updates"].assert_not_called()

        # 4. No referrer updates should have been applied
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_not_called()
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_not_called()

        # 5. OpenSearch deletion should still be attempted (cleanup)
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant123", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_file_missing_parameters(self, mock_db_pool_fixture):
        """Test deletion with missing required parameters."""
        pool, _ = mock_db_pool_fixture
        pruner = GitHubPruner()

        # Test missing file_path
        result = await pruner.delete_file(
            file_path="",
            repo_name="test-repo",
            organization="test-org",
            tenant_id="tenant123",
            db_pool=pool,
        )
        assert result is False

        # Test missing repo_name
        result = await pruner.delete_file(
            file_path="src/main.py",
            repo_name="",
            organization="test-org",
            tenant_id="tenant123",
            db_pool=pool,
        )
        assert result is False

        # Test missing organization
        result = await pruner.delete_file(
            file_path="src/main.py",
            repo_name="test-repo",
            organization="",
            tenant_id="tenant123",
            db_pool=pool,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_file_constructs_correct_entity_id(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test that entity_id is constructed correctly from org/repo/file_path."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = GitHubPruner()
        await pruner.delete_file(
            file_path="path/to/file.py",
            repo_name="my-repo",
            organization="my-org",
            tenant_id="tenant123",
            db_pool=pool,
        )

        # Verify correct entity_id construction: org/repo/file_path
        expected_entity_id = "my-org/my-repo/path/to/file.py"
        expected_document_id = f"github_file_{expected_entity_id}"

        # Should be used for artifact deletion
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "github_file",
            expected_entity_id,
        )

        # Should be used for OpenSearch deletion
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant123", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_file_handles_database_error(self, mock_db_pool_fixture):
        """Test deletion handles database errors gracefully."""
        pool, conn = mock_db_pool_fixture

        # Setup database error
        MockHelper.setup_database_error(conn)

        pruner = GitHubPruner()
        result = await pruner.delete_file(
            file_path="src/main.py",
            repo_name="test-repo",
            organization="test-org",
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_file_handles_opensearch_error(self, mock_db_pool_fixture):
        """Test deletion handles OpenSearch errors gracefully."""
        pool, conn = mock_db_pool_fixture

        # Setup successful artifact deletion but OpenSearch error
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        # Use the decorator-based approach for this specific test
        @mock_tenant_opensearch_manager_decorator
        async def _test_with_opensearch_error(mock_opensearch_manager, mock_opensearch_client):  # noqa: F811, ARG001
            MockHelper.setup_opensearch_error(mock_opensearch_manager)

            pruner = GitHubPruner()
            result = await pruner.delete_file(
                file_path="src/main.py",
                repo_name="test-repo",
                organization="test-org",
                tenant_id="tenant123",
                db_pool=pool,
            )
            return result

        result = await _test_with_opensearch_error()
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_file_with_special_characters(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion with special characters in file paths."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario with no artifacts
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=0)
        MockHelper.setup_no_document_found(conn)

        pruner = GitHubPruner()
        result = await pruner.delete_file(
            file_path="src/components/Button@2x.tsx",
            repo_name="ui-lib",
            organization="company-name",
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is True

        # Verify special characters are preserved in entity_id
        expected_entity_id = "company-name/ui-lib/src/components/Button@2x.tsx"
        expected_document_id = f"github_file_{expected_entity_id}"

        # Verify artifact deletion attempt with special characters
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "github_file",
            expected_entity_id,
        )

        # Verify OpenSearch deletion with special characters
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant123", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_file_empty_tenant_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty tenant_id."""
        pool, _ = mock_db_pool_fixture

        pruner = GitHubPruner()
        result = await pruner.delete_file(
            file_path="src/main.py",
            repo_name="test-repo",
            organization="test-org",
            tenant_id="",
            db_pool=pool,
        )

        assert result is False
