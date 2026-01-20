"""Tests for Monday.com backfill extractors."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from connectors.monday.client.monday_models import MondayBoard
from connectors.monday.extractors.monday_full_backfill_extractor import (
    MondayFullBackfillExtractor,
)
from connectors.monday.extractors.monday_incremental_backfill_extractor import (
    MondayIncrementalBackfillExtractor,
)
from connectors.monday.monday_job_models import MondayBackfillRootConfig


@pytest.fixture
def mock_ssm_client():
    """Create a mock SSM client."""
    return MagicMock()


@pytest.fixture
def mock_sqs_client():
    """Create a mock SQS client."""
    client = MagicMock()
    client.send_backfill_ingest_message = AsyncMock()
    return client


@pytest.fixture
def mock_db_pool():
    """Create a mock database pool."""
    pool = MagicMock()
    return pool


@pytest.fixture
def mock_trigger_indexing():
    """Create a mock trigger indexing callback."""
    return AsyncMock()


@pytest.fixture
def mock_monday_client():
    """Create a mock Monday.com client."""
    client = MagicMock()
    return client


@pytest.fixture
def sample_boards():
    """Sample boards with different visibility levels."""
    return [
        MondayBoard(
            id=1,
            name="Public Board 1",
            description="A public board",
            board_kind="public",
            workspace_id=100,
            workspace_name="Main Workspace",
        ),
        MondayBoard(
            id=2,
            name="Private Board",
            description="A private board",
            board_kind="private",
            workspace_id=100,
            workspace_name="Main Workspace",
        ),
        MondayBoard(
            id=3,
            name="Public Board 2",
            description="Another public board",
            board_kind="public",
            workspace_id=100,
            workspace_name="Main Workspace",
        ),
        MondayBoard(
            id=4,
            name="Shareable Board",
            description="A shareable board",
            board_kind="share",
            workspace_id=100,
            workspace_name="Main Workspace",
        ),
    ]


class TestMondayFullBackfillExtractorPrivateBoardFiltering:
    """Test suite for private board filtering in full backfill."""

    @pytest.mark.asyncio
    async def test_full_backfill_excludes_private_boards(
        self,
        mock_ssm_client,
        mock_sqs_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_monday_client,
        sample_boards,
    ):
        """Test that full backfill excludes private boards."""
        # Setup
        extractor = MondayFullBackfillExtractor(mock_ssm_client, mock_sqs_client)
        config = MondayBackfillRootConfig(
            tenant_id="test_tenant",
            backfill_id="test_backfill",
        )

        mock_monday_client.get_boards.return_value = sample_boards
        # Return item IDs for each board
        mock_monday_client.get_board_item_ids.side_effect = lambda board_id: [
            board_id * 100 + i for i in range(3)
        ]

        with (
            patch(
                "connectors.monday.extractors.monday_full_backfill_extractor.get_monday_client_for_tenant",
                return_value=mock_monday_client,
            ),
            patch(
                "connectors.monday.extractors.monday_full_backfill_extractor.MondaySyncService"
            ) as mock_sync_service_class,
            patch(
                "connectors.monday.extractors.monday_full_backfill_extractor.increment_backfill_total_ingest_jobs",
                new_callable=AsyncMock,
            ),
        ):
            mock_sync_service = MagicMock()
            mock_sync_service.set_incr_items_synced_until = AsyncMock()
            mock_sync_service_class.return_value = mock_sync_service

            await extractor.process_job(
                job_id="test_job_id",
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Verify get_board_item_ids was called only for non-private boards
        called_board_ids = [
            call.args[0] for call in mock_monday_client.get_board_item_ids.call_args_list
        ]

        # Should include only public (1, 3) boards, NOT private (2) or share (4)
        assert 1 in called_board_ids, "Public board 1 should be included"
        assert 3 in called_board_ids, "Public board 2 should be included"
        assert 2 not in called_board_ids, "Private board should be excluded"
        assert 4 not in called_board_ids, "Shareable board should be excluded"

    @pytest.mark.asyncio
    async def test_full_backfill_handles_all_private_boards(
        self,
        mock_ssm_client,
        mock_sqs_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_monday_client,
    ):
        """Test that full backfill handles case when all boards are private."""
        # Setup - all boards are private
        all_private_boards = [
            MondayBoard(
                id=1,
                name="Private Board 1",
                board_kind="private",
            ),
            MondayBoard(
                id=2,
                name="Private Board 2",
                board_kind="private",
            ),
        ]

        extractor = MondayFullBackfillExtractor(mock_ssm_client, mock_sqs_client)
        config = MondayBackfillRootConfig(
            tenant_id="test_tenant",
            backfill_id="test_backfill",
        )

        mock_monday_client.get_boards.return_value = all_private_boards

        with (
            patch(
                "connectors.monday.extractors.monday_full_backfill_extractor.get_monday_client_for_tenant",
                return_value=mock_monday_client,
            ),
            patch(
                "connectors.monday.extractors.monday_full_backfill_extractor.MondaySyncService"
            ) as mock_sync_service_class,
            patch(
                "connectors.monday.extractors.monday_full_backfill_extractor.increment_backfill_total_ingest_jobs",
                new_callable=AsyncMock,
            ),
        ):
            mock_sync_service = MagicMock()
            mock_sync_service.set_incr_items_synced_until = AsyncMock()
            mock_sync_service_class.return_value = mock_sync_service

            await extractor.process_job(
                job_id="test_job_id",
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Should not call get_board_item_ids for any board
        mock_monday_client.get_board_item_ids.assert_not_called()
        # Should not send any batch jobs
        mock_sqs_client.send_backfill_ingest_message.assert_not_called()


class TestMondayIncrementalBackfillExtractorPrivateBoardFiltering:
    """Test suite for private board filtering in incremental backfill."""

    @pytest.mark.asyncio
    async def test_incremental_backfill_excludes_private_boards(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_monday_client,
        sample_boards,
    ):
        """Test that incremental backfill excludes private boards."""
        from connectors.monday.extractors.monday_incremental_backfill_extractor import (
            MondayIncrementalBackfillConfig,
        )

        extractor = MondayIncrementalBackfillExtractor(mock_ssm_client)
        config = MondayIncrementalBackfillConfig(
            tenant_id="test_tenant",
            backfill_id="test_backfill",
        )

        mock_monday_client.get_boards.return_value = sample_boards
        mock_monday_client.get_all_activity_logs_since.return_value = []

        with (
            patch(
                "connectors.monday.extractors.monday_incremental_backfill_extractor.get_monday_client_for_tenant",
                return_value=mock_monday_client,
            ),
            patch(
                "connectors.monday.extractors.monday_incremental_backfill_extractor.MondaySyncService"
            ) as mock_sync_service_class,
            patch(
                "connectors.monday.extractors.monday_incremental_backfill_extractor.ArtifactRepository"
            ),
        ):
            mock_sync_service = MagicMock()
            mock_sync_service.get_incr_items_synced_until = AsyncMock(
                return_value=datetime.now(UTC)
            )
            mock_sync_service.set_incr_items_synced_until = AsyncMock()
            mock_sync_service_class.return_value = mock_sync_service

            await extractor.process_job(
                job_id=str(uuid4()),
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Verify get_all_activity_logs_since was called only for non-private boards
        called_board_ids = [
            call.kwargs.get("board_id") or call.args[0]
            for call in mock_monday_client.get_all_activity_logs_since.call_args_list
        ]

        # Should include only public (1, 3) boards, NOT private (2) or share (4)
        assert 1 in called_board_ids, "Public board 1 should be included"
        assert 3 in called_board_ids, "Public board 2 should be included"
        assert 2 not in called_board_ids, "Private board should be excluded"
        assert 4 not in called_board_ids, "Shareable board should be excluded"

    @pytest.mark.asyncio
    async def test_incremental_backfill_syncs_cursor_even_with_no_boards(
        self,
        mock_ssm_client,
        mock_db_pool,
        mock_trigger_indexing,
        mock_monday_client,
    ):
        """Test that incremental backfill updates cursor even when all boards are private."""
        from connectors.monday.extractors.monday_incremental_backfill_extractor import (
            MondayIncrementalBackfillConfig,
        )

        # All boards are private
        all_private_boards = [
            MondayBoard(id=1, name="Private Board", board_kind="private"),
        ]

        extractor = MondayIncrementalBackfillExtractor(mock_ssm_client)
        config = MondayIncrementalBackfillConfig(
            tenant_id="test_tenant",
            backfill_id="test_backfill",
        )

        mock_monday_client.get_boards.return_value = all_private_boards

        with (
            patch(
                "connectors.monday.extractors.monday_incremental_backfill_extractor.get_monday_client_for_tenant",
                return_value=mock_monday_client,
            ),
            patch(
                "connectors.monday.extractors.monday_incremental_backfill_extractor.MondaySyncService"
            ) as mock_sync_service_class,
            patch(
                "connectors.monday.extractors.monday_incremental_backfill_extractor.ArtifactRepository"
            ),
        ):
            mock_sync_service = MagicMock()
            mock_sync_service.get_incr_items_synced_until = AsyncMock(return_value=None)
            mock_sync_service.set_incr_items_synced_until = AsyncMock()
            mock_sync_service_class.return_value = mock_sync_service

            await extractor.process_job(
                job_id=str(uuid4()),
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

        # Should not check activity logs for private boards
        mock_monday_client.get_all_activity_logs_since.assert_not_called()
        # Cursor should still be updated
        mock_sync_service.set_incr_items_synced_until.assert_called_once()
