"""Tests for Gong pruner functionality."""

from unittest.mock import AsyncMock, patch

import pytest

from connectors.gong import GongPruner, gong_pruner

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


class TestGongPruner:
    """Test suite for Gong pruner functionality."""

    def test_singleton_pattern(self):
        """Test that GongPruner follows singleton pattern."""
        pruner1 = GongPruner()
        pruner2 = GongPruner()

        assert pruner1 is pruner2
        assert pruner1 is gong_pruner

    @pytest.mark.asyncio
    async def test_prune_unmarked_entities_no_stale_entities(
        self,
        mock_db_pool_fixture,
    ):
        """Test pruning when there are no stale entities."""
        pool, conn = mock_db_pool_fixture

        # Setup: no stale entities found in either artifacts or documents
        conn.fetch = AsyncMock(side_effect=[[], []])  # First for artifacts, second for documents

        pruner = GongPruner()
        result = await pruner.prune_unmarked_entities(
            tenant_id="tenant123",
            backfill_id="backfill789",
            db_pool=pool,
        )

        # Verify no deletions were made
        assert result == {}

        # Verify both queries were made (artifacts + documents)
        assert conn.fetch.call_count == 2

        # First call: artifacts query
        first_query_args = conn.fetch.call_args_list[0][0]
        assert "entity LIKE 'gong_%'" in first_query_args[0]
        assert "last_seen_backfill_id" in first_query_args[0]

        # Second call: documents query
        second_query_args = conn.fetch.call_args_list[1][0]
        assert "documents" in second_query_args[0]
        assert "source = 'gong'" in second_query_args[0]
        assert "last_seen_backfill_id" in second_query_args[0]

    @pytest.mark.asyncio
    async def test_prune_unmarked_entities_with_stale_calls(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test pruning stale Gong call entities."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup: 3 stale gong_call entities in artifacts
        stale_entities = [
            {"entity": "gong_call", "entity_id": "gong_call_123"},
            {"entity": "gong_call", "entity_id": "gong_call_456"},
            {"entity": "gong_call", "entity_id": "gong_call_789"},
        ]
        # No stale documents found directly
        conn.fetch = AsyncMock(side_effect=[stale_entities, []])

        # Setup document deletion mocks
        MockHelper.setup_no_document_found(conn)

        # Override execute to return correct artifact deletion count
        # (setup_no_document_found sets it to "DELETE 0", we need "DELETE 3" for artifacts)
        def execute_side_effect(query, *args):
            if "DELETE FROM ingest_artifact" in query:
                return "DELETE 3"
            return "DELETE 0"

        pool.execute = AsyncMock(side_effect=execute_side_effect)

        pruner = GongPruner()
        result = await pruner.prune_unmarked_entities(
            tenant_id="tenant123",
            backfill_id="backfill789",
            db_pool=pool,
        )

        # Verify deletion stats
        assert result == {"gong_call": 3}

        # Verify artifacts were deleted in batch
        pool.execute.assert_called()
        execute_calls = list(pool.execute.call_args_list)
        artifact_delete_call = execute_calls[0]
        assert "DELETE FROM ingest_artifact" in artifact_delete_call[0][0]
        assert artifact_delete_call[0][1] == "gong_call"

    @pytest.mark.asyncio
    async def test_prune_unmarked_entities_with_multiple_types(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test pruning with multiple entity types."""
        pool, conn = mock_db_pool_fixture
        _, _ = mock_opensearch_manager

        # Setup: multiple stale entity types in artifacts
        stale_entities = [
            {"entity": "gong_call", "entity_id": "gong_call_123"},
            {"entity": "gong_call", "entity_id": "gong_call_456"},
            {"entity": "gong_user", "entity_id": "gong_user_u1"},
            {"entity": "gong_user", "entity_id": "gong_user_u2"},
            {"entity": "gong_user", "entity_id": "gong_user_u3"},
            {"entity": "gong_permission_profile", "entity_id": "gong_permission_profile_p1"},
        ]
        # No stale documents found directly
        conn.fetch = AsyncMock(side_effect=[stale_entities, []])

        # Mock execute to return different counts for different entity types
        def execute_side_effect(query, *args):
            if "gong_call" in str(args):
                return "DELETE 2"
            elif "gong_user" in str(args):
                return "DELETE 3"
            elif "gong_permission_profile" in str(args):
                return "DELETE 1"
            return "DELETE 0"

        pool.execute = AsyncMock(side_effect=execute_side_effect)

        # Setup document deletion mocks
        MockHelper.setup_no_document_found(conn)

        pruner = GongPruner()
        result = await pruner.prune_unmarked_entities(
            tenant_id="tenant123",
            backfill_id="backfill789",
            db_pool=pool,
        )

        # Verify deletion stats for all entity types
        assert result == {
            "gong_call": 2,
            "gong_user": 3,
            "gong_permission_profile": 1,
        }

    @pytest.mark.asyncio
    async def test_prune_unmarked_entities_no_backfill_id(
        self,
        mock_db_pool_fixture,
    ):
        """Test pruning fails gracefully when no backfill_id is provided."""
        pool, _ = mock_db_pool_fixture

        pruner = GongPruner()
        result = await pruner.prune_unmarked_entities(
            tenant_id="tenant123",
            backfill_id="",  # Empty backfill_id
            db_pool=pool,
        )

        # Should return empty dict and not attempt deletions
        assert result == {}

    @pytest.mark.asyncio
    async def test_prune_unmarked_entities_with_document_deletion(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test that call entities trigger document deletion."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup: 2 stale gong_call entities in artifacts, 1 orphan document
        stale_entities = [
            {"entity": "gong_call", "entity_id": "gong_call_abc"},
            {"entity": "gong_call", "entity_id": "gong_call_def"},
        ]
        stale_documents = [
            {"id": "gong_call_orphan_xyz"},
        ]
        conn.fetch = AsyncMock(side_effect=[stale_entities, stale_documents])

        # Setup document with references for deletion flow
        MockHelper.setup_document_with_references(
            conn, reference_id="gong_call_ref_abc", referenced_docs={}
        )

        # Override execute to return correct artifact deletion count
        # (setup_document_with_references sets it to "DELETE 1", we need "DELETE 2" for artifacts)
        def execute_side_effect(query, *args):
            if "DELETE FROM ingest_artifact" in query:
                return "DELETE 2"
            return "DELETE 1"

        pool.execute = AsyncMock(side_effect=execute_side_effect)

        pruner = GongPruner()

        # Mock the delete_document method to track calls
        with (
            patch.object(pruner, "delete_document", new_callable=AsyncMock) as mock_delete_doc,
            patch.object(pruner, "delete_documents", new_callable=AsyncMock) as mock_delete_docs,
        ):
            mock_delete_doc.return_value = True

            result = await pruner.prune_unmarked_entities(
                tenant_id="tenant123",
                backfill_id="backfill789",
                db_pool=pool,
            )

            # Verify deletion stats - includes both artifact-based (2) and direct document (1) deletions
            assert result == {"gong_call": 2, "gong_document_direct": 1}

            # Verify delete_document was called for each orphan document
            assert mock_delete_doc.call_count == 1
            # Verify delete_documents was called once for calls
            assert mock_delete_docs.call_count == 1

            # Verify document IDs are correctly formatted
            mock_delete_doc_call_args_list = [call[0] for call in mock_delete_doc.call_args_list]
            mock_delete_doc_document_ids = [args[0] for args in mock_delete_doc_call_args_list]
            assert "gong_call_orphan_xyz" in mock_delete_doc_document_ids

            mock_delete_docs_document_ids = mock_delete_docs.call_args_list[0][0][0]
            assert "gong_call_abc" in mock_delete_docs_document_ids
            assert "gong_call_def" in mock_delete_docs_document_ids

    @pytest.mark.asyncio
    async def test_parse_gong_call_entity_id_valid(self):
        """Test parsing valid Gong call entity IDs."""
        from connectors.base.doc_ids import parse_gong_call_entity_id

        # Valid entity ID
        result = parse_gong_call_entity_id("gong_call_1234567")
        assert result == "1234567"

        # Valid entity ID with longer call ID
        result = parse_gong_call_entity_id("gong_call_abc-123-xyz")
        assert result == "abc-123-xyz"

    @pytest.mark.asyncio
    async def test_parse_gong_call_entity_id_invalid(self):
        """Test parsing invalid entity IDs."""
        from connectors.base.doc_ids import parse_gong_call_entity_id

        # Invalid prefix
        result = parse_gong_call_entity_id("gong_user_1234")
        assert result is None

        # Completely invalid
        result = parse_gong_call_entity_id("invalid_entity_id")
        assert result is None

        # Empty string
        result = parse_gong_call_entity_id("")
        assert result is None

    @pytest.mark.asyncio
    async def test_prune_with_large_batch_processing(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test pruning handles large batches efficiently."""
        pool, conn = mock_db_pool_fixture
        _, _ = mock_opensearch_manager

        # Setup: simulate 250 stale entities (testing batch processing)
        stale_entities = [
            {"entity": "gong_call", "entity_id": f"gong_call_{i}"} for i in range(250)
        ]
        # No stale documents found directly
        conn.fetch = AsyncMock(side_effect=[stale_entities, []])

        # Setup document deletion mocks
        MockHelper.setup_no_document_found(conn)

        # Override execute to return correct artifact deletion count
        # (setup_no_document_found sets it to "DELETE 0", we need "DELETE 250" for artifacts)
        def execute_side_effect(query, *args):
            if "DELETE FROM ingest_artifact" in query:
                return "DELETE 250"
            return "DELETE 0"

        pool.execute = AsyncMock(side_effect=execute_side_effect)

        pruner = GongPruner()

        # Mock delete_document to avoid actual deletion logic
        with patch.object(pruner, "delete_documents", new_callable=AsyncMock) as mock_delete_docs:
            result = await pruner.prune_unmarked_entities(
                tenant_id="tenant123",
                backfill_id="backfill789",
                db_pool=pool,
            )

            # Verify deletion stats
            assert result == {"gong_call": 250}

            # Verify delete_document was called for batch
            assert mock_delete_docs.call_count == 1

    @pytest.mark.asyncio
    async def test_prune_handles_document_deletion_errors(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test pruning continues even if some document deletions fail."""
        pool, conn = mock_db_pool_fixture
        _, _ = mock_opensearch_manager

        # Setup: 3 stale gong_call entities
        stale_entities = [{"entity": "gong_call", "entity_id": f"gong_call_{i}"} for i in range(3)]
        # No stale documents found directly
        conn.fetch = AsyncMock(side_effect=[stale_entities, []])
        pool.execute = AsyncMock(return_value="DELETE 3")

        pruner = GongPruner()

        # Mock delete_document to fail on second call
        with patch.object(pruner, "delete_documents", new_callable=AsyncMock) as mock_delete_docs:
            result = await pruner.prune_unmarked_entities(
                tenant_id="tenant123",
                backfill_id="backfill789",
                db_pool=pool,
            )

            # Artifacts should still be deleted
            assert result == {"gong_call": 3}

            # All document deletions should have been attempted
            assert mock_delete_docs.call_count == 1
