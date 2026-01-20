"""Tests for Attio sync service cursor persistence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from connectors.attio.attio_sync_service import (
    AttioSyncService,
    _get_backfill_complete_key,
    _get_backfill_cursor_key,
    _get_last_sync_time_key,
)


class TestKeyGeneration:
    """Test suite for config key generation functions."""

    def test_backfill_cursor_key(self):
        """Test cursor key generation for different object types."""
        assert _get_backfill_cursor_key("companies") == "ATTIO_BACKFILL_CURSOR_companies"
        assert _get_backfill_cursor_key("people") == "ATTIO_BACKFILL_CURSOR_people"
        assert _get_backfill_cursor_key("deals") == "ATTIO_BACKFILL_CURSOR_deals"

    def test_backfill_complete_key(self):
        """Test complete key generation for different object types."""
        assert _get_backfill_complete_key("companies") == "ATTIO_BACKFILL_COMPLETE_companies"
        assert _get_backfill_complete_key("people") == "ATTIO_BACKFILL_COMPLETE_people"
        assert _get_backfill_complete_key("deals") == "ATTIO_BACKFILL_COMPLETE_deals"

    def test_last_sync_time_key(self):
        """Test last sync time key generation."""
        assert _get_last_sync_time_key("companies") == "ATTIO_LAST_SYNC_TIME_companies"
        assert _get_last_sync_time_key("people") == "ATTIO_LAST_SYNC_TIME_people"


@pytest.fixture
def mock_pool():
    """Create a mock database pool."""
    pool = MagicMock()
    return pool


@pytest.fixture
def sync_service(mock_pool):
    """Create an AttioSyncService instance with mock pool."""
    return AttioSyncService(mock_pool)


class TestAttioSyncServiceCursorManagement:
    """Test suite for cursor persistence methods."""

    @pytest.mark.asyncio
    async def test_get_backfill_cursor_returns_cursor_when_exists(self, sync_service, mock_pool):
        """Test getting cursor when one exists in the database."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "cursor_abc123"}

        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        cursor = await sync_service.get_backfill_cursor("companies")

        assert cursor == "cursor_abc123"
        mock_conn.fetchrow.assert_called_once_with(
            "SELECT value FROM config WHERE key = $1",
            "ATTIO_BACKFILL_CURSOR_companies",
        )

    @pytest.mark.asyncio
    async def test_get_backfill_cursor_returns_none_when_not_exists(self, sync_service, mock_pool):
        """Test getting cursor when none exists."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None

        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        cursor = await sync_service.get_backfill_cursor("companies")

        assert cursor is None

    @pytest.mark.asyncio
    async def test_set_backfill_cursor_inserts_or_updates(self, sync_service, mock_pool):
        """Test setting cursor performs upsert."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_backfill_cursor("companies", "new_cursor_xyz")

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "INSERT INTO config" in call_args[0][0]
        assert "ON CONFLICT" in call_args[0][0]
        assert call_args[0][1] == "ATTIO_BACKFILL_CURSOR_companies"
        assert call_args[0][2] == "new_cursor_xyz"

    @pytest.mark.asyncio
    async def test_set_backfill_cursor_deletes_when_none(self, sync_service, mock_pool):
        """Test setting cursor to None deletes the key."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_backfill_cursor("companies", None)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "DELETE FROM config" in call_args[0][0]
        assert call_args[0][1] == "ATTIO_BACKFILL_CURSOR_companies"

    @pytest.mark.asyncio
    async def test_clear_backfill_cursor(self, sync_service, mock_pool):
        """Test clearing cursor deletes the key."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.clear_backfill_cursor("people")

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "DELETE FROM config" in call_args[0][0]
        assert call_args[0][1] == "ATTIO_BACKFILL_CURSOR_people"


class TestAttioSyncServiceBackfillComplete:
    """Test suite for backfill completion tracking."""

    @pytest.mark.asyncio
    async def test_is_backfill_complete_returns_true(self, sync_service, mock_pool):
        """Test checking backfill complete when marked true."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "true"}

        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.is_backfill_complete("companies")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_backfill_complete_returns_false_when_false(self, sync_service, mock_pool):
        """Test checking backfill complete when marked false."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "false"}

        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.is_backfill_complete("companies")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_backfill_complete_returns_false_when_not_set(self, sync_service, mock_pool):
        """Test checking backfill complete when key doesn't exist."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None

        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.is_backfill_complete("companies")

        assert result is False

    @pytest.mark.asyncio
    async def test_set_backfill_complete_true(self, sync_service, mock_pool):
        """Test marking backfill as complete."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_backfill_complete("deals", True)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "INSERT INTO config" in call_args[0][0]
        assert call_args[0][1] == "ATTIO_BACKFILL_COMPLETE_deals"
        assert call_args[0][2] == "true"

    @pytest.mark.asyncio
    async def test_set_backfill_complete_false(self, sync_service, mock_pool):
        """Test marking backfill as incomplete."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_backfill_complete("deals", False)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert call_args[0][2] == "false"


class TestAttioSyncServiceLastSyncTime:
    """Test suite for last sync time tracking."""

    @pytest.mark.asyncio
    async def test_get_last_sync_time_returns_datetime(self, sync_service, mock_pool):
        """Test getting last sync time when one exists."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"value": "2024-01-15T10:30:00+00:00"}

        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_last_sync_time("companies")

        assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_get_last_sync_time_returns_none_when_not_set(self, sync_service, mock_pool):
        """Test getting last sync time when not set."""
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None

        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        result = await sync_service.get_last_sync_time("companies")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_last_sync_time(self, sync_service, mock_pool):
        """Test setting last sync time."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        sync_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        await sync_service.set_last_sync_time("companies", sync_time)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "INSERT INTO config" in call_args[0][0]
        assert call_args[0][1] == "ATTIO_LAST_SYNC_TIME_companies"
        # The value should be an ISO format string
        assert "2024-01-15" in call_args[0][2]

    @pytest.mark.asyncio
    async def test_set_last_sync_time_none_deletes_key(self, sync_service, mock_pool):
        """Test setting last sync time to None deletes the key."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.set_last_sync_time("companies", None)

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "DELETE FROM config" in call_args[0][0]
