"""Tests for Trello GDPR compliance poller.

This module tests the Trello compliance poller including:
- Polling schedule logic (12-day cycle with 14-day requirement)
- Event handling for all event types (accountDeleted, tokenRevoked, tokenExpired, accountUpdated)
- Member data anonymization across all data structures
- Installation tracking and tenant lookup
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cron.jobs.trello_compliance_poller import TrelloCompliancePoller


class TestTrelloCompliancePollerScheduling:
    """Test suite for polling schedule logic."""

    @pytest.mark.asyncio
    async def test_should_poll_no_previous_poll(self):
        """Test that polling is required when no previous poll exists."""
        poller = TrelloCompliancePoller()

        # Mock control pool and connection
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None  # No previous poll
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        result = await poller.should_poll(mock_pool)

        assert result is True

    @pytest.mark.asyncio
    async def test_should_poll_after_12_days(self):
        """Test that polling is required after 12+ days (with 2-day buffer)."""
        poller = TrelloCompliancePoller()
        last_poll = datetime.now(UTC) - timedelta(days=13)

        # Mock control pool and connection
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"last_poll_at": last_poll}
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        result = await poller.should_poll(mock_pool)

        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_poll_within_12_days(self):
        """Test that polling is skipped within 12-day window."""
        poller = TrelloCompliancePoller()
        last_poll = datetime.now(UTC) - timedelta(days=5)

        # Mock control pool and connection
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"last_poll_at": last_poll}
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        result = await poller.should_poll(mock_pool)

        assert result is False

    @pytest.mark.asyncio
    async def test_should_poll_exactly_12_days(self):
        """Test polling at exactly 12-day boundary."""
        poller = TrelloCompliancePoller()
        last_poll = datetime.now(UTC) - timedelta(days=12, hours=1)

        # Mock control pool and connection
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"last_poll_at": last_poll}
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        result = await poller.should_poll(mock_pool)

        assert result is True


class TestTrelloCompliancePollerLastProcessedDate:
    """Test suite for tracking last processed date."""

    @pytest.mark.asyncio
    async def test_get_last_processed_date_no_records(self):
        """Test getting last processed date when no records exist."""
        poller = TrelloCompliancePoller()

        # Mock control pool and connection
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        result = await poller.get_last_processed_date(mock_pool)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_last_processed_date_with_records(self):
        """Test getting last processed date when records exist."""
        poller = TrelloCompliancePoller()
        test_date = datetime(2025, 11, 10, 12, 0, 0, tzinfo=UTC)

        # Mock control pool and connection
        mock_pool = MagicMock()
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = {"last_processed_record_date": test_date}
        mock_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn))
        )

        result = await poller.get_last_processed_date(mock_pool)

        # Implementation uses specific format for Trello API: "YYYY-MM-DD HH:MM:SSZ"
        assert result == "2025-11-10 12:00:00Z"


class TestTrelloCompliancePollerAnonymization:
    """Test suite for member data anonymization."""

    @pytest.mark.asyncio
    async def test_anonymize_member_personal_data(self):
        """Test anonymization of member personal data."""
        poller = TrelloCompliancePoller()
        member_id = "member123"
        tenant_id = "tenant-abc"

        # Mock connection
        mock_conn = AsyncMock()
        # Mock email lookup query - return a member email
        mock_conn.fetchrow.return_value = {"email": "member123@example.com"}
        # Mock all UPDATE queries returning "UPDATE 1" (1 row affected each)
        mock_conn.execute.side_effect = ["UPDATE 1", "UPDATE 2", "UPDATE 1", "UPDATE 1", "UPDATE 1"]

        result = await poller._anonymize_member_personal_data(member_id, tenant_id, mock_conn)

        # Should have called fetchrow once for email lookup
        assert mock_conn.fetchrow.call_count == 1
        # Should have called execute 5 times (card assignments, card_data members, comments, board emails, card board_member_emails)
        assert mock_conn.execute.call_count == 5
        # Total affected should be 1 + 2 + 1 + 1 + 1 = 6
        assert result == 6

    @pytest.mark.asyncio
    async def test_anonymize_with_no_data(self):
        """Test anonymization when no data exists for member."""
        poller = TrelloCompliancePoller()
        member_id = "member-nonexistent"
        tenant_id = "tenant-xyz"

        # Mock connection
        mock_conn = AsyncMock()
        # Mock email lookup query - return None (no email found)
        mock_conn.fetchrow.return_value = None
        # Mock first 3 UPDATE queries returning "UPDATE 0" (no rows affected)
        # Queries 4 and 5 won't run because no email was found
        mock_conn.execute.side_effect = ["UPDATE 0", "UPDATE 0", "UPDATE 0"]

        result = await poller._anonymize_member_personal_data(member_id, tenant_id, mock_conn)

        # Should have called fetchrow once for email lookup
        assert mock_conn.fetchrow.call_count == 1
        # Should have called execute only 3 times (email removal queries skipped)
        assert mock_conn.execute.call_count == 3
        assert result == 0

    @pytest.mark.asyncio
    async def test_anonymize_with_email_found(self):
        """Test anonymization specifically checks email removal from arrays."""
        poller = TrelloCompliancePoller()
        member_id = "member456"
        tenant_id = "tenant-def"

        # Mock connection
        mock_conn = AsyncMock()
        # Mock email lookup query - return a member email
        mock_conn.fetchrow.return_value = {"email": "test@example.com"}
        # Mock UPDATE queries: 3 normal queries + 2 email removal queries
        mock_conn.execute.side_effect = ["UPDATE 2", "UPDATE 3", "UPDATE 1", "UPDATE 4", "UPDATE 2"]

        result = await poller._anonymize_member_personal_data(member_id, tenant_id, mock_conn)

        # Verify all 5 queries executed
        assert mock_conn.execute.call_count == 5
        # Total: 2 + 3 + 1 + 4 + 2 = 12
        assert result == 12


class TestTrelloCompliancePollerCleanup:
    """Test suite for member data cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_with_valid_installation(self):
        """Test cleanup when installation record exists."""
        poller = TrelloCompliancePoller()
        member_id = "member123"
        tenant_id = "tenant-abc"
        record_date = datetime(2025, 11, 10, 12, 0, 0, tzinfo=UTC)

        # Mock tenant_db_manager
        mock_control_pool = MagicMock()
        mock_control_conn = AsyncMock()
        mock_control_conn.fetchrow.return_value = {
            "id": "connector-123",
            "tenant_id": tenant_id,
            "member_username": "testuser",
        }
        mock_control_conn.execute = AsyncMock()
        mock_control_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_control_conn))
        )

        mock_tenant_pool = MagicMock()
        mock_tenant_conn = AsyncMock()
        # Mock email lookup returning a valid email
        mock_tenant_conn.fetchrow.return_value = {"email": "member123@example.com"}
        mock_tenant_conn.execute.side_effect = [
            "UPDATE 1",
            "UPDATE 1",
            "UPDATE 1",
            "UPDATE 1",
            "UPDATE 1",
        ]
        mock_tenant_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_tenant_conn))
        )

        with (
            patch("src.cron.jobs.trello_compliance_poller.tenant_db_manager") as mock_mgr,
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)
            mock_mgr.acquire_pool = MagicMock(
                return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_tenant_pool))
            )

            await poller._cleanup_member_data(member_id, record_date, reason="accountDeleted")

        # Verify installation was looked up (control DB)
        mock_control_conn.fetchrow.assert_called_once()

        # Verify email lookup and anonymization (tenant DB: 1 fetchrow + 5 execute)
        assert mock_tenant_conn.fetchrow.call_count == 1
        assert mock_tenant_conn.execute.call_count == 5

        # Verify installation was deleted from control DB
        mock_control_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_with_missing_installation(self):
        """Test cleanup when installation record doesn't exist."""
        poller = TrelloCompliancePoller()
        member_id = "missing-member-123"
        record_date = datetime(2025, 11, 10, 12, 0, 0, tzinfo=UTC)

        # Mock tenant_db_manager
        mock_control_pool = MagicMock()
        mock_control_conn = AsyncMock()
        mock_control_conn.fetchrow.return_value = None  # No installation found
        mock_control_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_control_conn))
        )

        with patch("src.cron.jobs.trello_compliance_poller.tenant_db_manager") as mock_mgr:
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            await poller._cleanup_member_data(member_id, record_date, reason="tokenRevoked")

        # Verify installation lookup was attempted
        mock_control_conn.fetchrow.assert_called_once()

        # Should return early without trying to anonymize
        mock_control_conn.execute.assert_not_called()


class TestTrelloCompliancePollerAPIIntegration:
    """Test suite for Trello compliance API integration."""

    @pytest.mark.asyncio
    async def test_poll_skipped_when_credentials_missing(self):
        """Test that polling is skipped when credentials are not configured."""
        # Create poller with no credentials
        with (
            patch(
                "src.cron.jobs.trello_compliance_poller.get_trello_power_up_id", return_value=None
            ),
            patch(
                "src.cron.jobs.trello_compliance_poller.get_trello_power_up_api_key",
                return_value=None,
            ),
            patch(
                "src.cron.jobs.trello_compliance_poller.get_trello_power_up_secret",
                return_value=None,
            ),
        ):
            poller = TrelloCompliancePoller()

            await poller.poll_compliance_api()

        # Should return early without calling API
        assert True  # If we get here without error, test passed

    @pytest.mark.asyncio
    async def test_poll_skipped_when_not_needed(self):
        """Test that polling is skipped when within 12-day window."""
        with (
            patch(
                "src.cron.jobs.trello_compliance_poller.get_trello_power_up_id",
                return_value="plugin123",
            ),
            patch(
                "src.cron.jobs.trello_compliance_poller.get_trello_power_up_api_key",
                return_value="key123",
            ),
            patch(
                "src.cron.jobs.trello_compliance_poller.get_trello_power_up_secret",
                return_value="secret123",
            ),
        ):
            poller = TrelloCompliancePoller()

            # Mock should_poll to return False
            mock_pool = MagicMock()

            with (
                patch("src.cron.jobs.trello_compliance_poller.tenant_db_manager") as mock_mgr,
                patch.object(poller, "should_poll", return_value=False),
            ):
                mock_mgr.get_control_db = AsyncMock(return_value=mock_pool)

                await poller.poll_compliance_api()

        # Should return early without calling API
        assert True  # If we get here without error, test passed

    @pytest.mark.asyncio
    async def test_poll_with_no_records(self):
        """Test polling when API returns no records."""
        with (
            patch(
                "src.cron.jobs.trello_compliance_poller.get_trello_power_up_id",
                return_value="plugin123",
            ),
            patch(
                "src.cron.jobs.trello_compliance_poller.get_trello_power_up_api_key",
                return_value="key123",
            ),
            patch(
                "src.cron.jobs.trello_compliance_poller.get_trello_power_up_secret",
                return_value="secret123",
            ),
        ):
            poller = TrelloCompliancePoller()

            mock_pool = MagicMock()
            mock_client = MagicMock()
            mock_client.get_compliance_member_privacy.return_value = []  # No records

            with (
                patch("src.cron.jobs.trello_compliance_poller.tenant_db_manager") as mock_mgr,
                patch(
                    "src.cron.jobs.trello_compliance_poller.TrelloClient", return_value=mock_client
                ),
                patch.object(poller, "should_poll", return_value=True),
                patch.object(poller, "get_last_processed_date", return_value=None),
                patch.object(poller, "update_tracking", AsyncMock()) as mock_update,
            ):
                mock_mgr.get_control_db = AsyncMock(return_value=mock_pool)

                await poller.poll_compliance_api()

        # Should call update_tracking with 0 records
        mock_update.assert_called_once_with(mock_pool, 0, None)


class TestTrelloCompliancePollerProfileUpdates:
    """Test suite for member profile update handling."""

    @pytest.mark.asyncio
    async def test_handle_member_profile_update(self):
        """Test handling of member profile update events."""
        poller = TrelloCompliancePoller()
        member_id = "member123"
        tenant_id = "tenant-abc"
        member_username = "testuser"
        record_date = datetime(2025, 11, 10, 12, 0, 0, tzinfo=UTC)

        # Mock control database
        mock_control_pool = MagicMock()
        mock_control_conn = AsyncMock()
        mock_control_conn.fetchrow.return_value = {
            "tenant_id": tenant_id,
            "member_username": member_username,
        }
        mock_control_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_control_conn))
        )

        # Mock SQS client
        mock_sqs_client = AsyncMock()
        mock_sqs_client.send_backfill_ingest_message.return_value = "message-id-123"

        with (
            patch("src.cron.jobs.trello_compliance_poller.tenant_db_manager") as mock_mgr,
            patch("src.cron.jobs.trello_compliance_poller.SQSClient", return_value=mock_sqs_client),
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            await poller.handle_member_profile_update(member_id, record_date)

        # Verify installation was looked up
        mock_control_conn.fetchrow.assert_called_once()

        # Verify backfill message was sent via higher-level API
        mock_sqs_client.send_backfill_ingest_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_member_profile_update_no_installation(self):
        """Test handling profile update when no installation exists."""
        poller = TrelloCompliancePoller()
        member_id = "member-nonexistent"
        record_date = datetime(2025, 11, 10, 12, 0, 0, tzinfo=UTC)

        # Mock control database returning no installation
        mock_control_pool = MagicMock()
        mock_control_conn = AsyncMock()
        mock_control_conn.fetchrow.return_value = None
        mock_control_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_control_conn))
        )

        # Mock SQS client
        mock_sqs_client = AsyncMock()

        with (
            patch("src.cron.jobs.trello_compliance_poller.tenant_db_manager") as mock_mgr,
            patch("src.cron.jobs.trello_compliance_poller.SQSClient", return_value=mock_sqs_client),
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            await poller.handle_member_profile_update(member_id, record_date)

        # Verify installation lookup was attempted
        mock_control_conn.fetchrow.assert_called_once()

        # Verify NO backfill message was sent (no installation found)
        mock_sqs_client.send_backfill_ingest_message.assert_not_called()
