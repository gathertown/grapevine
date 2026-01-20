"""Tests for Slack pruner functionality."""

from unittest.mock import AsyncMock, patch

import pytest

from connectors.slack import SlackPruner, slack_pruner

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


class TestSlackPruner:
    """Test suite for Slack pruner functionality."""

    def test_singleton_pattern(self):
        """Test that SlackPruner follows singleton pattern."""
        pruner1 = SlackPruner()
        pruner2 = SlackPruner()

        assert pruner1 is pruner2
        assert pruner1 is slack_pruner

    @pytest.mark.asyncio
    async def test_delete_message_complete_flow_with_client_msg_id(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Slack message deletion with client_msg_id."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup complete successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_document_with_references(
            pool, reference_id="slack_msg_ref_123", referenced_docs={"doc7": 1}
        )
        MockHelper.setup_referrer_updates(
            mock_deletion_dependencies,
            referrer_updates=[{"doc_id": "doc7", "count": -1}],
        )

        # Mock the reindex entity lookup
        conn.fetchval = AsyncMock(return_value="reindex_msg_456")

        with patch("connectors.slack.slack_pruner.get_message_pacific_document_id") as mock_doc_id:
            mock_doc_id.return_value = "slack-C123456789-2024-01-15"

            pruner = SlackPruner()
            result, reindex_entity = await pruner.delete_message(
                channel="C123456789",
                deleted_ts="1705123456.789",
                tenant_id="tenant-slack",
                db_pool=pool,
                client_msg_id="client_msg_abc123",
            )

        assert result is True
        assert reindex_entity == "reindex_msg_456"

        expected_document_id = "slack-C123456789-2024-01-15"

        # 1. Artifacts were deleted using client_msg_id (preferred method)
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "slack_message",
            "client_msg_abc123",
        )

        # 2. Referrer updates were prepared with the document's references
        mock_deletion_dependencies["prepare_referrer_updates"].assert_called_once_with(
            "slack_msg_ref_123", {"doc7": 1}, conn
        )

        # 3. Referrer updates were applied to database with expected updates
        mock_deletion_dependencies["apply_referrer_updates_db"].assert_called_once_with(
            [{"doc_id": "doc7", "count": -1}], conn
        )

        # 4. Document was deleted from database
        conn.execute.assert_called_with("DELETE FROM documents WHERE id = $1", expected_document_id)

        # 5. Referrer updates were applied to OpenSearch
        mock_deletion_dependencies["apply_referrer_updates_opensearch"].assert_called_once_with(
            [{"doc_id": "doc7", "count": -1}],
            "tenant-slack",
            opensearch_client,
        )

        # 6. Document was deleted from OpenSearch
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-slack", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_message_complete_flow_with_timestamp_fallback(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test message deletion using timestamp fallback when client_msg_id is None."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario with no document found
        MockHelper.setup_no_document_found(conn)

        # Mock the timestamp-based artifact deletion query result
        conn.execute = AsyncMock(return_value="DELETE 2")
        conn.fetchval = AsyncMock(return_value=None)  # No reindex entity found

        with patch("connectors.slack.slack_pruner.get_message_pacific_document_id") as mock_doc_id:
            mock_doc_id.return_value = "slack-C987654321-2024-01-15"

            pruner = SlackPruner()
            result, reindex_entity = await pruner.delete_message(
                channel="C987654321",
                deleted_ts="1705123456.789",
                tenant_id="tenant-slack",
                db_pool=pool,
                client_msg_id=None,  # Force timestamp fallback
            )

        assert result is True
        assert reindex_entity is None  # No entity found for reindex

        expected_document_id = "slack-C987654321-2024-01-15"

        # Verify timestamp-based artifact deletion was used
        conn.execute.assert_any_call(
            """
                DELETE FROM ingest_artifact
                WHERE entity = 'slack_message'
                AND content->>'ts' = $1
                AND metadata->>'channel_id' = $2
                """,
            "1705123456.789",
            "C987654321",
        )

        # Verify OpenSearch deletion
        opensearch_client.delete_document.assert_called_once_with(
            "tenant-tenant-slack", expected_document_id
        )

    @pytest.mark.asyncio
    async def test_delete_message_finds_reindex_entity(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test that the pruner finds an entity for reindexing from the same channel-day."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager  # noqa: F841

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        # Mock the reindex entity lookup to return a specific entity
        conn.fetchval = AsyncMock(return_value="msg_for_reindex_789")

        with (
            patch("connectors.slack.slack_pruner.get_message_pacific_document_id") as mock_doc_id,
            patch("connectors.slack.slack_pruner.datetime") as mock_datetime,
            patch(
                "connectors.slack.slack_pruner.get_pacific_day_boundaries_timestamps"
            ) as mock_boundaries,
        ):
            mock_doc_id.return_value = "slack-C555555555-2024-01-15"

            # Mock datetime conversion
            mock_dt = mock_datetime.fromtimestamp.return_value
            mock_dt.strftime.return_value = "2024-01-15"

            # Mock Pacific boundaries
            mock_boundaries.return_value = (1705123400.0, 1705209799.999)

            pruner = SlackPruner()
            result, reindex_entity = await pruner.delete_message(
                channel="C555555555",
                deleted_ts="1705123456.789",
                tenant_id="tenant-slack",
                db_pool=pool,
                client_msg_id="client_msg_xyz",
            )

        assert result is True
        assert reindex_entity == "msg_for_reindex_789"

        # Verify the reindex query was called with correct parameters
        conn.fetchval.assert_called_with(
            """
                SELECT entity_id FROM ingest_artifact
                WHERE entity = 'slack_message'
                AND metadata->>'channel_id' = $1
                AND (content->>'ts')::float >= $2
                AND (content->>'ts')::float <= $3
                LIMIT 1
                """,
            "C555555555",
            1705123400.0,
            1705209799.999,
        )

    @pytest.mark.asyncio
    async def test_delete_message_missing_parameters(self, mock_db_pool_fixture):
        """Test deletion with missing required parameters."""
        pool, _ = mock_db_pool_fixture
        pruner = SlackPruner()

        # Test missing channel
        result, reindex_entity = await pruner.delete_message(
            channel="",
            deleted_ts="1705123456.789",
            tenant_id="tenant-slack",
            db_pool=pool,
        )
        assert result is False
        assert reindex_entity is None

        # Test missing deleted_ts
        result, reindex_entity = await pruner.delete_message(
            channel="C123456789",
            deleted_ts="",
            tenant_id="tenant-slack",
            db_pool=pool,
        )
        assert result is False
        assert reindex_entity is None

    @pytest.mark.asyncio
    async def test_delete_message_handles_database_error(self, mock_db_pool_fixture):
        """Test deletion handles database errors gracefully."""
        pool, conn = mock_db_pool_fixture

        # Setup database error
        MockHelper.setup_database_error(conn)

        pruner = SlackPruner()
        result, reindex_entity = await pruner.delete_message(
            channel="C123456789",
            deleted_ts="1705123456.789",
            tenant_id="tenant-slack",
            db_pool=pool,
        )

        assert result is False
        assert reindex_entity is None

    @pytest.mark.asyncio
    async def test_delete_message_handles_reindex_query_error(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811, ARG001
    ):
        """Test deletion handles errors in reindex entity lookup gracefully."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager  # noqa: F841

        # Setup successful deletion but error in reindex lookup
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        MockHelper.setup_no_document_found(conn)

        # Make fetchval raise an exception for reindex query
        conn.fetchval = AsyncMock(side_effect=Exception("Database error in reindex lookup"))

        with patch("connectors.slack.slack_pruner.get_message_pacific_document_id") as mock_doc_id:
            mock_doc_id.return_value = "slack-C777777777-2024-01-15"

            pruner = SlackPruner()
            result, reindex_entity = await pruner.delete_message(
                channel="C777777777",
                deleted_ts="1705123456.789",
                tenant_id="tenant-slack",
                db_pool=pool,
                client_msg_id="client_msg_error_test",
            )

        # Deletion should succeed but reindex entity should be None due to error
        assert result is True
        assert reindex_entity is None

    @pytest.mark.asyncio
    async def test_delete_message_empty_tenant_id(self, mock_db_pool_fixture):
        """Test deletion fails with empty tenant_id."""
        pool, _ = mock_db_pool_fixture

        pruner = SlackPruner()
        result, reindex_entity = await pruner.delete_message(
            channel="C123456789",
            deleted_ts="1705123456.789",
            tenant_id="",
            db_pool=pool,
        )

        assert result is False
        assert reindex_entity is None

    @pytest.mark.asyncio
    async def test_delete_channel_complete_flow(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test complete end-to-end Slack channel deletion."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful scenario
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=2)  # channel artifacts

        # Mock message artifact deletion
        conn.execute.return_value = "DELETE 5"  # 5 message artifacts deleted

        # Mock finding channel documents
        conn.fetch.return_value = [
            {"id": "C123456789_2024-01-15"},
            {"id": "C123456789_2024-01-16"},
        ]

        # Setup document deletion success
        MockHelper.setup_document_with_references(
            conn, reference_id="slack_channel_ref_123", referenced_docs={}
        )

        with patch("connectors.base.doc_ids.get_slack_channel_doc_ids") as mock_get_docs:
            mock_get_docs.return_value = ["C123456789_2024-01-15", "C123456789_2024-01-16"]

            pruner = SlackPruner()
            result = await pruner.delete_channel(
                channel_id="C123456789",
                tenant_id="tenant-slack",
                db_pool=pool,
            )

        assert result is True

        # Verify channel artifacts were deleted
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = $1 AND entity_id = $2",
            "slack_channel",
            "C123456789",
        )

        # Verify message artifacts were deleted by channel
        conn.execute.assert_any_call(
            "DELETE FROM ingest_artifact WHERE entity = 'slack_message' AND metadata->>'channel_id' = $1",
            "C123456789",
        )

    @pytest.mark.asyncio
    async def test_delete_channel_no_documents_found(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test channel deletion when no documents exist."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup artifact deletion but no documents
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        conn.execute.return_value = "DELETE 3"  # message artifacts

        with patch("connectors.base.doc_ids.get_slack_channel_doc_ids") as mock_get_docs:
            mock_get_docs.return_value = []  # No documents found

            pruner = SlackPruner()
            result = await pruner.delete_channel(
                channel_id="C123456789",
                tenant_id="tenant-slack",
                db_pool=pool,
            )

        assert result is True  # Should succeed even with no documents

    @pytest.mark.asyncio
    async def test_delete_channel_empty_channel_id(self, mock_db_pool_fixture):
        """Test channel deletion fails with empty channel_id."""
        pool, _ = mock_db_pool_fixture

        pruner = SlackPruner()
        result = await pruner.delete_channel(
            channel_id="",
            tenant_id="tenant-slack",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_channel_database_error(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test channel deletion handles database errors gracefully."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup database error
        conn.execute.side_effect = Exception("Database connection failed")

        pruner = SlackPruner()
        result = await pruner.delete_channel(
            channel_id="C123456789",
            tenant_id="tenant-slack",
            db_pool=pool,
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_channel_partial_document_deletion_failure(
        self,
        mock_db_pool_fixture,
        mock_opensearch_manager,  # noqa: F811
        mock_deletion_dependencies,  # noqa: F811
    ):
        """Test channel deletion with some document deletion failures."""
        pool, conn = mock_db_pool_fixture
        _, opensearch_client = mock_opensearch_manager

        # Setup successful artifact deletion
        MockHelper.setup_successful_artifact_deletion(conn, num_artifacts=1)
        conn.execute.return_value = "DELETE 2"  # message artifacts

        # Setup mixed document deletion results
        MockHelper.setup_document_with_references(
            conn, reference_id="slack_channel_ref_123", referenced_docs={}
        )

        with patch("connectors.base.doc_ids.get_slack_channel_doc_ids") as mock_get_docs:
            mock_get_docs.return_value = ["C123456789_2024-01-15", "C123456789_2024-01-16"]

            with patch.object(SlackPruner, "delete_document") as mock_delete_doc:
                # First document deletion succeeds, second fails
                mock_delete_doc.side_effect = [True, False]

                pruner = SlackPruner()
                result = await pruner.delete_channel(
                    channel_id="C123456789",
                    tenant_id="tenant-slack",
                    db_pool=pool,
                )

        # Should fail because not all documents were deleted successfully
        assert result is False
