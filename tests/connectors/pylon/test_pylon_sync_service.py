"""Tests for Pylon sync service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from connectors.pylon.pylon_sync_service import PylonSyncService


@pytest.fixture
def mock_pool():
    """Create a mock database pool."""
    return MagicMock()


@pytest.fixture
def sync_service(mock_pool):
    """Create a PylonSyncService instance with mock pool."""
    return PylonSyncService(mock_pool)


class TestPylonSyncServiceFullBackfill:
    """Tests for full backfill tracking methods."""

    @pytest.mark.asyncio
    async def test_get_full_issues_synced_after_returns_datetime(self, sync_service, mock_pool):
        """Test getting synced_after timestamp when it exists."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "2024-01-15T10:30:00+00:00"}
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_full_issues_synced_after()

        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        mock_conn.fetchrow.assert_called_once_with(
            "SELECT value FROM config WHERE key = $1",
            "PYLON_FULL_BACKFILL_ISSUES_SYNCED_AFTER",
        )

    @pytest.mark.asyncio
    async def test_get_full_issues_synced_after_returns_none(self, sync_service, mock_pool):
        """Test getting synced_after timestamp when not set."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_full_issues_synced_after()

        assert result is None

    @pytest.mark.asyncio
    async def test_set_full_issues_synced_after(self, sync_service, mock_pool):
        """Test setting synced_after timestamp."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        sync_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        await sync_service.set_full_issues_synced_after(sync_time)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "INSERT INTO config" in call_args[0][0]
        assert call_args[0][1] == "PYLON_FULL_BACKFILL_ISSUES_SYNCED_AFTER"
        assert "2024-01-15" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_set_full_issues_synced_after_none_deletes(self, sync_service, mock_pool):
        """Test setting synced_after to None deletes the key."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_full_issues_synced_after(None)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "DELETE FROM config" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_get_full_issues_backfill_complete_true(self, sync_service, mock_pool):
        """Test checking backfill complete when marked true."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "true"}
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_full_issues_backfill_complete()

        assert result is True

    @pytest.mark.asyncio
    async def test_get_full_issues_backfill_complete_false(self, sync_service, mock_pool):
        """Test checking backfill complete when marked false."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "false"}
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_full_issues_backfill_complete()

        assert result is False

    @pytest.mark.asyncio
    async def test_get_full_issues_backfill_complete_not_set(self, sync_service, mock_pool):
        """Test checking backfill complete when key doesn't exist."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_full_issues_backfill_complete()

        assert result is False

    @pytest.mark.asyncio
    async def test_set_full_issues_backfill_complete_true(self, sync_service, mock_pool):
        """Test marking backfill as complete."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_full_issues_backfill_complete(True)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][1] == "PYLON_FULL_BACKFILL_ISSUES_COMPLETE"
        assert call_args[0][2] == "true"

    @pytest.mark.asyncio
    async def test_set_full_issues_backfill_complete_false(self, sync_service, mock_pool):
        """Test marking backfill as incomplete."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_full_issues_backfill_complete(False)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][2] == "false"

    @pytest.mark.asyncio
    async def test_get_full_issues_cursor_returns_string(self, sync_service, mock_pool):
        """Test getting cursor when it exists."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "abc123cursor"}
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_full_issues_cursor()

        assert result == "abc123cursor"
        mock_conn.fetchrow.assert_called_once_with(
            "SELECT value FROM config WHERE key = $1",
            "PYLON_FULL_BACKFILL_ISSUES_CURSOR",
        )

    @pytest.mark.asyncio
    async def test_get_full_issues_cursor_returns_none(self, sync_service, mock_pool):
        """Test getting cursor when not set."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_full_issues_cursor()

        assert result is None

    @pytest.mark.asyncio
    async def test_set_full_issues_cursor(self, sync_service, mock_pool):
        """Test setting cursor."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_full_issues_cursor("xyz789cursor")

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][1] == "PYLON_FULL_BACKFILL_ISSUES_CURSOR"
        assert call_args[0][2] == "xyz789cursor"

    @pytest.mark.asyncio
    async def test_set_full_issues_cursor_none_deletes(self, sync_service, mock_pool):
        """Test setting cursor to None deletes the key."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_full_issues_cursor(None)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "DELETE FROM config" in call_args[0][0]


class TestPylonSyncServiceIncrementalBackfill:
    """Tests for incremental backfill tracking methods."""

    @pytest.mark.asyncio
    async def test_get_incr_issues_synced_until_returns_datetime(self, sync_service, mock_pool):
        """Test getting synced_until timestamp when it exists."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "2024-02-20T15:45:00+00:00"}
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_incr_issues_synced_until()

        assert result == datetime(2024, 2, 20, 15, 45, 0, tzinfo=UTC)
        mock_conn.fetchrow.assert_called_once_with(
            "SELECT value FROM config WHERE key = $1",
            "PYLON_INCR_BACKFILL_ISSUES_SYNCED_UNTIL",
        )

    @pytest.mark.asyncio
    async def test_get_incr_issues_synced_until_returns_none(self, sync_service, mock_pool):
        """Test getting synced_until timestamp when not set."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_incr_issues_synced_until()

        assert result is None

    @pytest.mark.asyncio
    async def test_set_incr_issues_synced_until(self, sync_service, mock_pool):
        """Test setting synced_until timestamp."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        sync_time = datetime(2024, 2, 20, 15, 45, 0, tzinfo=UTC)
        await sync_service.set_incr_issues_synced_until(sync_time)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][1] == "PYLON_INCR_BACKFILL_ISSUES_SYNCED_UNTIL"
        assert "2024-02-20" in call_args[0][2]


class TestPylonSyncServiceReferenceData:
    """Tests for reference data sync tracking methods."""

    @pytest.mark.asyncio
    async def test_get_reference_data_synced_at_returns_datetime(self, sync_service, mock_pool):
        """Test getting reference data sync timestamp when it exists."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "2024-03-01T08:00:00+00:00"}
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_reference_data_synced_at()

        assert result == datetime(2024, 3, 1, 8, 0, 0, tzinfo=UTC)
        mock_conn.fetchrow.assert_called_once_with(
            "SELECT value FROM config WHERE key = $1",
            "PYLON_REFERENCE_DATA_SYNCED_AT",
        )

    @pytest.mark.asyncio
    async def test_get_reference_data_synced_at_returns_none(self, sync_service, mock_pool):
        """Test getting reference data sync timestamp when not set."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_reference_data_synced_at()

        assert result is None

    @pytest.mark.asyncio
    async def test_set_reference_data_synced_at(self, sync_service, mock_pool):
        """Test setting reference data sync timestamp."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        sync_time = datetime(2024, 3, 1, 8, 0, 0, tzinfo=UTC)
        await sync_service.set_reference_data_synced_at(sync_time)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][1] == "PYLON_REFERENCE_DATA_SYNCED_AT"
        assert "2024-03-01" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_set_reference_data_synced_at_none_deletes(self, sync_service, mock_pool):
        """Test setting reference data sync to None deletes the key."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_reference_data_synced_at(None)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "DELETE FROM config" in call_args[0][0]
