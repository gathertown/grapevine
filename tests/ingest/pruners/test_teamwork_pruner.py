"""Tests for Teamwork pruner functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.teamwork.teamwork_pruner import (
    TEAMWORK_TASK_DOC_ID_PREFIX,
    TeamworkPruner,
    get_teamwork_task_doc_id,
)

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


@pytest.fixture
def mock_ssm_client():
    """Fixture for mock SSM client."""
    return MagicMock()


class TestTeamworkPrunerSingleton:
    """Test singleton pattern."""

    def test_singleton_pattern(self):
        """Test that TeamworkPruner follows singleton pattern."""
        pruner1 = TeamworkPruner()
        pruner2 = TeamworkPruner()
        assert pruner1 is pruner2


@pytest.fixture
def mock_teamwork_client():
    """Fixture for mock Teamwork client."""
    client = MagicMock()
    client.get_tasks_by_ids = MagicMock()
    return client


class TestTeamworkPrunerHelpers:
    """Test helper functions."""

    def test_get_teamwork_task_doc_id_with_int(self):
        """Test doc ID generation with integer task ID."""
        assert get_teamwork_task_doc_id(12345) == "teamwork_task_12345"

    def test_get_teamwork_task_doc_id_with_string(self):
        """Test doc ID generation with string task ID."""
        assert get_teamwork_task_doc_id("67890") == "teamwork_task_67890"

    def test_doc_id_prefix_constant(self):
        """Test that doc ID prefix is correct."""
        assert TEAMWORK_TASK_DOC_ID_PREFIX == "teamwork_task_"


class TestTeamworkPrunerDeleteTask:
    """Test suite for delete_task functionality."""

    @pytest.mark.asyncio
    async def test_delete_task_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Teamwork task deletion."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        pruner = TeamworkPruner()
        result = await pruner.delete_task(
            task_id=12345,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is True

        # Verify artifact deletion was called with correct entity
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "teamwork_task",
            "teamwork_task_12345",
        )

        # Verify OpenSearch deletion
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant123", "teamwork_task_12345"
        )

    @pytest.mark.asyncio
    async def test_delete_task_empty_task_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty task_id."""
        pool, _ = mock_db_pool_fixture

        pruner = TeamworkPruner()
        result = await pruner.delete_task(
            task_id=0,  # Falsy task ID
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_task_handles_database_error(self, mock_db_pool_fixture):
        """Test deletion handles database errors gracefully."""
        pool, conn = mock_db_pool_fixture

        # Setup database error
        MockHelper.setup_database_error(conn)

        pruner = TeamworkPruner()
        result = await pruner.delete_task(
            task_id=12345,
            tenant_id="tenant123",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_task_handles_opensearch_error(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test deletion handles OpenSearch errors gracefully."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful DB operations
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        # Setup OpenSearch deletion to fail
        opensearch_client.delete_document.side_effect = Exception("OpenSearch connection failed")

        pruner = TeamworkPruner()
        result = await pruner.delete_task(
            task_id=12345,
            tenant_id="tenant123",
            db_pool=pool,
        )

        # Should return falsy (not True) when OpenSearch fails
        # Note: Currently returns None due to how deletion_service handles errors
        assert not result

        # Verify DB operations were still attempted
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "teamwork_task",
            "teamwork_task_12345",
        )


class TestTeamworkPrunerFindStaleDocuments:
    """Test suite for find_stale_documents functionality."""

    @pytest.mark.asyncio
    async def test_find_stale_documents_no_ssm_client(self, mock_db_pool_fixture):
        """Test find_stale_documents fails without SSM client."""
        pool, _ = mock_db_pool_fixture

        pruner = TeamworkPruner()
        result = await pruner.find_stale_documents(
            tenant_id="tenant123",
            db_pool=pool,
            ssm_client=None,
        )

        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_no_indexed_documents(
        self, mock_db_pool_fixture, mock_ssm_client
    ):
        """Test find_stale_documents with no indexed documents."""
        pool, conn = mock_db_pool_fixture

        # Setup: no documents found
        conn.fetch = AsyncMock(return_value=[])

        with patch(
            "connectors.teamwork.teamwork_pruner.get_teamwork_client_for_tenant"
        ) as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            pruner = TeamworkPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_deleted_tasks(
        self, mock_db_pool_fixture, mock_ssm_client, mock_teamwork_client
    ):
        """Test find_stale_documents detects deleted tasks."""
        pool, conn = mock_db_pool_fixture

        # Setup: 3 indexed documents
        conn.fetch = AsyncMock(
            return_value=[
                {"id": "teamwork_task_100"},
                {"id": "teamwork_task_200"},
                {"id": "teamwork_task_300"},
            ]
        )

        # Setup: API returns only task 100 (200 and 300 are deleted)
        mock_teamwork_client.get_tasks_by_ids.return_value = {
            "tasks": [{"id": 100, "isPrivate": False}],
        }

        with patch(
            "connectors.teamwork.teamwork_pruner.get_teamwork_client_for_tenant",
            new=AsyncMock(return_value=mock_teamwork_client),
        ):
            pruner = TeamworkPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # Tasks 200 and 300 should be marked as stale (deleted)
        assert len(result) == 2
        assert "teamwork_task_200" in result
        assert "teamwork_task_300" in result
        assert "teamwork_task_100" not in result

    @pytest.mark.asyncio
    async def test_find_stale_documents_private_tasks(
        self, mock_db_pool_fixture, mock_ssm_client, mock_teamwork_client
    ):
        """Test find_stale_documents detects private tasks."""
        pool, conn = mock_db_pool_fixture

        # Setup: 3 indexed documents
        conn.fetch = AsyncMock(
            return_value=[
                {"id": "teamwork_task_100"},
                {"id": "teamwork_task_200"},
                {"id": "teamwork_task_300"},
            ]
        )

        # Setup: API returns all tasks, but 200 is now private
        mock_teamwork_client.get_tasks_by_ids.return_value = {
            "tasks": [
                {"id": 100, "isPrivate": False},
                {"id": 200, "isPrivate": True},  # Became private
                {"id": 300, "isPrivate": False},
            ],
        }

        with patch(
            "connectors.teamwork.teamwork_pruner.get_teamwork_client_for_tenant",
            new=AsyncMock(return_value=mock_teamwork_client),
        ):
            pruner = TeamworkPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # Only task 200 should be marked as stale (private)
        assert len(result) == 1
        assert "teamwork_task_200" in result

    @pytest.mark.asyncio
    async def test_find_stale_documents_missing_visibility(
        self, mock_db_pool_fixture, mock_ssm_client, mock_teamwork_client
    ):
        """Test find_stale_documents treats missing isPrivate as private (fail-closed)."""
        pool, conn = mock_db_pool_fixture

        # Setup: 3 indexed documents
        conn.fetch = AsyncMock(
            return_value=[
                {"id": "teamwork_task_100"},
                {"id": "teamwork_task_200"},
                {"id": "teamwork_task_300"},
            ]
        )

        # Setup: API returns all tasks, but 200 is missing isPrivate field
        mock_teamwork_client.get_tasks_by_ids.return_value = {
            "tasks": [
                {"id": 100, "isPrivate": False},
                {"id": 200},  # Missing isPrivate - should be treated as private
                {"id": 300, "isPrivate": False},
            ],
        }

        with patch(
            "connectors.teamwork.teamwork_pruner.get_teamwork_client_for_tenant",
            new=AsyncMock(return_value=mock_teamwork_client),
        ):
            pruner = TeamworkPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # Task 200 should be marked as stale (missing visibility)
        assert len(result) == 1
        assert "teamwork_task_200" in result

    @pytest.mark.asyncio
    async def test_find_stale_documents_mixed_scenarios(
        self, mock_db_pool_fixture, mock_ssm_client, mock_teamwork_client
    ):
        """Test find_stale_documents with mixed deleted, private, and missing visibility."""
        pool, conn = mock_db_pool_fixture

        # Setup: 5 indexed documents
        conn.fetch = AsyncMock(
            return_value=[
                {"id": "teamwork_task_100"},  # Public - keep
                {"id": "teamwork_task_200"},  # Deleted - remove
                {"id": "teamwork_task_300"},  # Private - remove
                {"id": "teamwork_task_400"},  # Missing visibility - remove
                {"id": "teamwork_task_500"},  # Public - keep
            ]
        )

        # Setup: API returns 4 tasks (200 is deleted)
        mock_teamwork_client.get_tasks_by_ids.return_value = {
            "tasks": [
                {"id": 100, "isPrivate": False},  # Public
                {"id": 300, "isPrivate": True},  # Private
                {"id": 400},  # Missing isPrivate
                {"id": 500, "isPrivate": False},  # Public
            ],
        }

        with patch(
            "connectors.teamwork.teamwork_pruner.get_teamwork_client_for_tenant",
            new=AsyncMock(return_value=mock_teamwork_client),
        ):
            pruner = TeamworkPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # 200 (deleted), 300 (private), 400 (missing visibility) should be stale
        assert len(result) == 3
        assert "teamwork_task_200" in result
        assert "teamwork_task_300" in result
        assert "teamwork_task_400" in result
        assert "teamwork_task_100" not in result
        assert "teamwork_task_500" not in result

    @pytest.mark.asyncio
    async def test_find_stale_documents_handles_client_error(
        self, mock_db_pool_fixture, mock_ssm_client
    ):
        """Test find_stale_documents handles client creation error."""
        pool, _ = mock_db_pool_fixture

        with patch(
            "connectors.teamwork.teamwork_pruner.get_teamwork_client_for_tenant",
            new=AsyncMock(side_effect=Exception("API error")),
        ):
            pruner = TeamworkPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_handles_batch_error(
        self, mock_db_pool_fixture, mock_ssm_client, mock_teamwork_client
    ):
        """Test find_stale_documents handles batch fetch errors gracefully."""
        pool, conn = mock_db_pool_fixture

        # Setup: 2 indexed documents
        conn.fetch = AsyncMock(
            return_value=[
                {"id": "teamwork_task_100"},
                {"id": "teamwork_task_200"},
            ]
        )

        # Setup: API throws error
        mock_teamwork_client.get_tasks_by_ids.side_effect = Exception("Batch fetch error")

        with patch(
            "connectors.teamwork.teamwork_pruner.get_teamwork_client_for_tenant",
            new=AsyncMock(return_value=mock_teamwork_client),
        ):
            pruner = TeamworkPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # Should return empty list on error (not crash)
        assert result == []

    @pytest.mark.asyncio
    async def test_find_stale_documents_invalid_doc_id_format(
        self, mock_db_pool_fixture, mock_ssm_client, mock_teamwork_client
    ):
        """Test find_stale_documents handles invalid document ID formats."""
        pool, conn = mock_db_pool_fixture

        # Setup: Mix of valid and invalid document IDs
        conn.fetch = AsyncMock(
            return_value=[
                {"id": "teamwork_task_100"},  # Valid
                {"id": "invalid_format"},  # Invalid - should be skipped
                {"id": "teamwork_task_abc"},  # Invalid - non-numeric ID
                {"id": "teamwork_task_200"},  # Valid
            ]
        )

        # Setup: API returns both valid tasks as public
        mock_teamwork_client.get_tasks_by_ids.return_value = {
            "tasks": [
                {"id": 100, "isPrivate": False},
                {"id": 200, "isPrivate": False},
            ],
        }

        with patch(
            "connectors.teamwork.teamwork_pruner.get_teamwork_client_for_tenant",
            new=AsyncMock(return_value=mock_teamwork_client),
        ):
            pruner = TeamworkPruner()
            result = await pruner.find_stale_documents(
                tenant_id="tenant123",
                db_pool=pool,
                ssm_client=mock_ssm_client,
            )

        # No stale documents since both valid tasks are public
        assert result == []
