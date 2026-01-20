"""Integration tests for Trello GDPR compliance flows.

Tests compliance API-based (accountUpdated) member profile update handling
to ensure GDPR Article 5(1)(d) compliance.

NOTE: Trello's updateMember webhook event is DEPRECATED and unreliable.
We do not test webhook-based profile updates as they are not supported by Trello.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.cron.jobs.trello_compliance_poller import TrelloCompliancePoller


class TestTrelloCompliancePollerGDPRIntegration:
    """Integration tests for Trello compliance API-based GDPR compliance."""

    @pytest.mark.asyncio
    async def test_compliance_poller_handles_account_updated(self):
        """Test that compliance poller handles accountUpdated events correctly."""
        poller = TrelloCompliancePoller()

        # Mock control database with installation record
        mock_control_pool = MagicMock()
        mock_control_conn = AsyncMock()
        mock_control_conn.fetchrow.return_value = {
            "tenant_id": "test-tenant-xyz789",
            "member_username": "jane_smith",
        }
        mock_control_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_control_conn))
        )

        # Mock SQS client
        mock_sqs_client = AsyncMock()
        mock_sqs_client.send_backfill_ingest_message.return_value = "test-message-id-789"

        with (
            patch("src.cron.jobs.trello_compliance_poller.tenant_db_manager") as mock_mgr,
            patch("src.cron.jobs.trello_compliance_poller.SQSClient", return_value=mock_sqs_client),
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            # Process accountUpdated event
            await poller.handle_member_profile_update(
                member_id="5e8d7c6b5a4938271605f4e3",
                record_date=datetime(2025, 11, 11, 10, 30, 0, tzinfo=UTC),
            )

        # Assertions
        # 1. Installation lookup was performed
        mock_control_conn.fetchrow.assert_called_once()
        assert "connector_installations" in str(mock_control_conn.fetchrow.call_args)
        assert "type = 'trello'" in str(mock_control_conn.fetchrow.call_args)

        # 2. Backfill message was sent via high-level API
        assert mock_sqs_client.send_backfill_ingest_message.called
        call_args = mock_sqs_client.send_backfill_ingest_message.call_args

        # 3. Message contains correct tenant and force_update=True for GDPR compliance
        backfill_message = call_args.args[0]
        assert backfill_message.tenant_id == "test-tenant-xyz789"
        assert backfill_message.source == "trello_api_backfill_root"
        assert backfill_message.force_update is True  # Critical for GDPR profile updates

    @pytest.mark.asyncio
    async def test_compliance_poller_handles_missing_installation(self, caplog):
        """Test graceful handling when no installation exists for member."""
        poller = TrelloCompliancePoller()

        # Mock control database returning no installation
        mock_control_pool = MagicMock()
        mock_control_conn = AsyncMock()
        mock_control_conn.fetchrow.return_value = None  # No installation found
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

            await poller.handle_member_profile_update(
                member_id="nonexistent-member-123",
                record_date=datetime(2025, 11, 11, 10, 30, 0, tzinfo=UTC),
            )

        # Assertions
        # 1. Installation lookup was attempted
        mock_control_conn.fetchrow.assert_called_once()

        # 2. NO backfill message sent (no installation = no tenant to backfill)
        mock_sqs_client.send_backfill_ingest_message.assert_not_called()

        # 3. Warning logged
        assert "No Trello installation found" in caplog.text

    @pytest.mark.asyncio
    async def test_compliance_poller_handles_sqs_failure(self, caplog):
        """Test handling when SQS message sending fails.

        CRITICAL: When SQS fails, an exception must be raised to prevent marking
        the compliance record as processed. This ensures failed GDPR profile updates
        are retried on the next poll.
        """
        poller = TrelloCompliancePoller()

        # Mock control database with installation
        mock_control_pool = MagicMock()
        mock_control_conn = AsyncMock()
        mock_control_conn.fetchrow.return_value = {
            "tenant_id": "test-tenant-failed",
            "member_username": "test_user",
        }
        mock_control_pool.acquire = MagicMock(
            return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_control_conn))
        )

        # Mock SQS client to return None (failure)
        mock_sqs_client = AsyncMock()
        mock_sqs_client.send_backfill_ingest_message.return_value = None

        with (
            patch("src.cron.jobs.trello_compliance_poller.tenant_db_manager") as mock_mgr,
            patch("src.cron.jobs.trello_compliance_poller.SQSClient", return_value=mock_sqs_client),
        ):
            mock_mgr.get_control_db = AsyncMock(return_value=mock_control_pool)

            # Should raise RuntimeError when SQS fails
            with pytest.raises(RuntimeError, match="Failed to trigger Trello backfill"):
                await poller.handle_member_profile_update(
                    member_id="test-member-123",
                    record_date=datetime(2025, 11, 11, 10, 30, 0, tzinfo=UTC),
                )

        # Assertions
        # 1. Backfill send was attempted
        assert mock_sqs_client.send_backfill_ingest_message.called

        # 2. Error logged with GDPR context
        assert "Failed to trigger Trello backfill" in caplog.text
        assert "GDPR Article 5(1)(d)" in caplog.text
