"""Tests for Canva sync service cursor persistence."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.canva.canva_sync_service import CanvaSyncService


@pytest.fixture
def mock_pool():
    """Create a mock database pool."""
    pool = MagicMock()
    return pool


@pytest.fixture
def sync_service(mock_pool):
    """Create a CanvaSyncService instance with mock pool."""
    return CanvaSyncService(mock_pool, tenant_id="test_tenant_123")


class TestCanvaSyncServiceDesignsSyncedUntil:
    """Test suite for designs synced until tracking."""

    @pytest.mark.asyncio
    async def test_get_designs_synced_until_returns_datetime(self, sync_service):
        """Test getting designs synced until when value exists."""
        with patch(
            "connectors.canva.canva_sync_service.get_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_get_config:
            mock_get_config.return_value = "2024-01-15T10:30:00+00:00"

            result = await sync_service.get_designs_synced_until()

            assert result == datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
            mock_get_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_designs_synced_until_returns_none_when_empty(self, sync_service):
        """Test getting designs synced until when value is empty."""
        with patch(
            "connectors.canva.canva_sync_service.get_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_get_config:
            mock_get_config.return_value = ""

            result = await sync_service.get_designs_synced_until()

            assert result is None

    @pytest.mark.asyncio
    async def test_get_designs_synced_until_returns_none_when_not_set(self, sync_service):
        """Test getting designs synced until when key doesn't exist."""
        with patch(
            "connectors.canva.canva_sync_service.get_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_get_config:
            mock_get_config.return_value = None

            result = await sync_service.get_designs_synced_until()

            assert result is None

    @pytest.mark.asyncio
    async def test_get_designs_synced_until_handles_invalid_date(self, sync_service):
        """Test getting designs synced until with invalid date format."""
        with patch(
            "connectors.canva.canva_sync_service.get_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_get_config:
            mock_get_config.return_value = "invalid-date-format"

            result = await sync_service.get_designs_synced_until()

            assert result is None

    @pytest.mark.asyncio
    async def test_set_designs_synced_until(self, sync_service):
        """Test setting designs synced until timestamp."""
        with patch(
            "connectors.canva.canva_sync_service.set_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_set_config:
            timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

            await sync_service.set_designs_synced_until(timestamp)

            mock_set_config.assert_called_once()
            call_args = mock_set_config.call_args
            assert call_args[0][0] == "CANVA_DESIGNS_SYNCED_UNTIL"
            assert "2024-01-15" in call_args[0][1]


class TestCanvaSyncServiceFullBackfillComplete:
    """Test suite for full backfill completion tracking."""

    @pytest.mark.asyncio
    async def test_is_full_backfill_complete_returns_true(self, sync_service):
        """Test checking backfill complete when marked true."""
        with patch(
            "connectors.canva.canva_sync_service.get_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_get_config:
            mock_get_config.return_value = "true"

            result = await sync_service.is_full_backfill_complete()

            assert result is True

    @pytest.mark.asyncio
    async def test_is_full_backfill_complete_returns_true_case_insensitive(self, sync_service):
        """Test checking backfill complete handles case variations."""
        with patch(
            "connectors.canva.canva_sync_service.get_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_get_config:
            mock_get_config.return_value = "TRUE"

            result = await sync_service.is_full_backfill_complete()

            assert result is True

    @pytest.mark.asyncio
    async def test_is_full_backfill_complete_returns_false_when_false(self, sync_service):
        """Test checking backfill complete when marked false."""
        with patch(
            "connectors.canva.canva_sync_service.get_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_get_config:
            mock_get_config.return_value = "false"

            result = await sync_service.is_full_backfill_complete()

            assert result is False

    @pytest.mark.asyncio
    async def test_is_full_backfill_complete_returns_false_when_not_set(self, sync_service):
        """Test checking backfill complete when key doesn't exist."""
        with patch(
            "connectors.canva.canva_sync_service.get_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_get_config:
            mock_get_config.return_value = None

            result = await sync_service.is_full_backfill_complete()

            assert result is False

    @pytest.mark.asyncio
    async def test_is_full_backfill_complete_returns_false_for_empty_string(self, sync_service):
        """Test checking backfill complete when value is empty string."""
        with patch(
            "connectors.canva.canva_sync_service.get_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_get_config:
            mock_get_config.return_value = ""

            result = await sync_service.is_full_backfill_complete()

            assert result is False

    @pytest.mark.asyncio
    async def test_set_full_backfill_complete_true(self, sync_service):
        """Test marking backfill as complete."""
        with patch(
            "connectors.canva.canva_sync_service.set_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_set_config:
            await sync_service.set_full_backfill_complete(True)

            mock_set_config.assert_called_once()
            call_args = mock_set_config.call_args
            assert call_args[0][0] == "CANVA_FULL_BACKFILL_COMPLETE"
            assert call_args[0][1] == "true"

    @pytest.mark.asyncio
    async def test_set_full_backfill_complete_false(self, sync_service):
        """Test marking backfill as incomplete."""
        with patch(
            "connectors.canva.canva_sync_service.set_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_set_config:
            await sync_service.set_full_backfill_complete(False)

            mock_set_config.assert_called_once()
            call_args = mock_set_config.call_args
            assert call_args[0][1] == "false"

    @pytest.mark.asyncio
    async def test_set_full_backfill_complete_default(self, sync_service):
        """Test marking backfill complete with default parameter."""
        with patch(
            "connectors.canva.canva_sync_service.set_config_value_with_pool",
            new_callable=AsyncMock,
        ) as mock_set_config:
            await sync_service.set_full_backfill_complete()

            mock_set_config.assert_called_once()
            call_args = mock_set_config.call_args
            assert call_args[0][1] == "true"


class TestCanvaSyncServiceClearState:
    """Test suite for clearing sync state."""

    @pytest.mark.asyncio
    async def test_clear_sync_state(self, sync_service, mock_pool):
        """Test clearing all sync state."""
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        await sync_service.clear_sync_state()

        mock_conn.execute.assert_called_once()
        call_args = mock_conn.execute.call_args
        assert "DELETE FROM config" in call_args[0][0]
        assert "CANVA_DESIGNS_SYNCED_UNTIL" in call_args[0]
        assert "CANVA_FULL_BACKFILL_COMPLETE" in call_args[0]


class TestCanvaSyncServiceInitialization:
    """Test suite for sync service initialization."""

    def test_initialization(self, mock_pool):
        """Test sync service initializes with correct attributes."""
        service = CanvaSyncService(mock_pool, tenant_id="test_tenant_abc")

        assert service.db_pool is mock_pool
        assert service.tenant_id == "test_tenant_abc"

    def test_initialization_different_tenants(self, mock_pool):
        """Test multiple services can be created for different tenants."""
        service1 = CanvaSyncService(mock_pool, tenant_id="tenant_1")
        service2 = CanvaSyncService(mock_pool, tenant_id="tenant_2")

        assert service1.tenant_id != service2.tenant_id
        assert service1.tenant_id == "tenant_1"
        assert service2.tenant_id == "tenant_2"
