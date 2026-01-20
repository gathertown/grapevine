import json

import pytest

from connectors.slack import SlackWebhookExtractor


class TestSlackWebhookFiltering:
    @pytest.fixture
    def extractor(self):
        return SlackWebhookExtractor()

    @pytest.fixture
    def slack_connect_payload(self):
        webhook_body = '{"token":"XZ7ArFjgTRNIBZ09P92heLqV","team_id":"T017NA5LEV9","context_team_id":"T02B9UTL2E4","context_enterprise_id":"E062XL0SJ3H","api_app_id":"A09AAE5FM8V","event":{"user":"U08S4NPGX7X","type":"message","ts":"1755205729.376419","client_msg_id":"aaae2419-7c06-43fc-be69-e059494d7bd8","text":"slack connect channel test message","team":"T017NA5LEV9","thread_ts":"1755203357.658399","parent_user_id":"U08S4NPGX7X","blocks":[{"type":"rich_text","block_id":"3AUuz","elements":[{"type":"rich_text_section","elements":[{"type":"text","text":"not a big deal if not "},{"type":"emoji","name":"slightly_smiling_face","unicode":"1f642"}]}]}],"channel":"C08UHAM34QM","event_ts":"1755205729.376419","channel_type":"channel"},"type":"event_callback","event_id":"Ev09AUNS4ABB","event_time":1755205729,"authorizations":[{"enterprise_id":null,"team_id":"T017NA5LEV9","user_id":"U09AERJ2868","is_bot":true,"is_enterprise_install":false}],"is_ext_shared_channel":true,"event_context":"4-eyJldCI6Im1lc3NhZ2UiLCJ0aWQiOiJUMDE3TkE1TEVWOSIsImFpZCI6IkEwOUFBRTVGTThWIiwiY2lkIjoiQzA4VUhBTTM0UU0ifQ"}'
        return json.loads(webhook_body)

    @pytest.fixture
    def private_channel_payload(self):
        webhook_body = '{"token":"KSA7L8k1nkkrkqCFCexoKem0","team_id":"T09ABMYAW3E","context_team_id":"T09ABMYAW3E","context_enterprise_id":null,"api_app_id":"A09B6A2UADN","event":{"user":"U09ABMYAW68","type":"message","ts":"1755207036.275549","client_msg_id":"eb851608-ad2f-4c18-b9c7-ada1ccb5684f","text":"slack private channel test message","team":"T09ABMYAW3E","blocks":[{"type":"rich_text","block_id":"bSP2r","elements":[{"type":"rich_text_section","elements":[{"type":"text","text":"another test for private chanel"}]}]}],"channel":"C09AUAK57PT","event_ts":"1755207036.275549","channel_type":"group"},"type":"event_callback","event_id":"Ev09AF8ZU1V3","event_time":1755207036,"authorizations":[{"enterprise_id":null,"team_id":"T09ABMYAW3E","user_id":"U09ADCG596W","is_bot":true,"is_enterprise_install":false}],"is_ext_shared_channel":false,"event_context":"4-eyJldCI6Im1lc3NhZ2UiLCJ0aWQiOiJUMDlBQk1ZQVczRSIsImFpZCI6IkEwOUI2QTJVQUROIiwiY2lkIjoiQzA5QVVBSzU3UFQifQ"}'
        return json.loads(webhook_body)

    @pytest.fixture
    def direct_message_payload(self):
        webhook_body = '{"token":"KSA7L8k1nkkrkqCFCexoKem0","team_id":"T09ABMYAW3E","context_team_id":"T09ABMYAW3E","context_enterprise_id":null,"api_app_id":"A09B6A2UADN","event":{"user":"U09ABMYAW68","type":"message","ts":"1755206774.642699","client_msg_id":"b6db98d2-fa64-40d5-8e41-9d5294f261a1","text":"slack direct message test message","team":"T09ABMYAW3E","blocks":[{"type":"rich_text","block_id":"ELyXN","elements":[{"type":"rich_text_section","elements":[{"type":"text","text":"another test for tou"}]}]}],"channel":"D09ADCG99GA","event_ts":"1755206774.642699","channel_type":"im"},"type":"event_callback","event_id":"Ev09AJ0GB1E2","event_time":1755206774,"authorizations":[{"enterprise_id":null,"team_id":"T09ABMYAW3E","user_id":"U09ADCG596W","is_bot":true,"is_enterprise_install":false}],"is_ext_shared_channel":false,"event_context":"4-eyJldCI6Im1lc3NhZ2UiLCJ0aWQiOiJUMDlBQk1ZQVczRSIsImFpZCI6IkEwOUI2QTJVQUROIiwiY2lkIjoiRDA5QURDRzk5R0EifQ"}'
        return json.loads(webhook_body)

    @pytest.fixture
    def regular_channel_payload(self):
        webhook_body = '{"token":"KSA7L8k1nkkrkqCFCexoKem0","team_id":"T09ABMYAW3E","context_team_id":"T09ABMYAW3E","context_enterprise_id":null,"api_app_id":"A09B6A2UADN","event":{"user":"U09ABMYAW68","type":"message","ts":"1755207036.275549","client_msg_id":"eb851608-ad2f-4c18-b9c7-ada1ccb5684f","text":"slack public channel test message","team":"T09ABMYAW3E","blocks":[{"type":"rich_text","block_id":"bSP2r","elements":[{"type":"rich_text_section","elements":[{"type":"text","text":"test for public channel"}]}]}],"channel":"C09AUAK57PT","event_ts":"1755207036.275549","channel_type":"channel"},"type":"event_callback","event_id":"Ev09AF8ZU1V3","event_time":1755207036,"authorizations":[{"enterprise_id":null,"team_id":"T09ABMYAW3E","user_id":"U09ADCG596W","is_bot":true,"is_enterprise_install":false}],"is_ext_shared_channel":false,"event_context":"4-eyJldCI6Im1lc3NhZ2UiLCJ0aWQiOiJUMDlBQk1ZQVczRSIsImFpZCI6IkEwOUI2QTJVQUROIiwiY2lkIjoiQzA5QVVBSzU3UFQifQ"}'
        return json.loads(webhook_body)

    def test_filters_real_slack_connect_payload(self, extractor, slack_connect_payload):
        decision = extractor._should_process_payload(slack_connect_payload)
        # Slack Connect channels should now be processed (indexed) but not sent to bot queue
        assert decision.should_process is True
        assert decision.should_delete_channel is False

    def test_filters_real_private_channel_payload(self, extractor, private_channel_payload):
        decision = extractor._should_process_payload(private_channel_payload)
        assert decision.should_process is False
        assert decision.should_delete_channel is True
        assert "private channel/DM" in decision.reason
        assert "group" in decision.reason

    def test_filters_real_direct_message_payload(self, extractor, direct_message_payload):
        decision = extractor._should_process_payload(direct_message_payload)
        assert decision.should_process is False
        assert decision.should_delete_channel is True
        assert "private channel/DM" in decision.reason
        assert "im" in decision.reason

    def test_allows_regular_channel_payload(self, extractor, regular_channel_payload):
        decision = extractor._should_process_payload(regular_channel_payload)
        assert decision.should_process is True
        assert decision.should_delete_channel is False
        assert decision.reason is None

    def test_missing_is_ext_shared_channel_field(self, extractor, slack_connect_payload):
        payload = slack_connect_payload.copy()
        del payload["is_ext_shared_channel"]

        decision = extractor._should_process_payload(payload)
        assert decision.should_process is True
        assert decision.should_delete_channel is False

    def test_conflicting_channel_type_info(self, extractor, private_channel_payload):
        payload = private_channel_payload.copy()
        payload["event"]["channel_type"] = "channel"
        payload["event"]["channel"] = "G09AUAK57PT"

        decision = extractor._should_process_payload(payload)
        assert decision.should_process is True
        assert decision.should_delete_channel is False

    def test_missing_channel_type_field(self, extractor, regular_channel_payload):
        payload = regular_channel_payload.copy()
        del payload["event"]["channel_type"]

        decision = extractor._should_process_payload(payload)
        assert decision.should_process is True
        assert decision.should_delete_channel is False
        assert decision.reason is None

    def test_external_user_indicators(self, extractor, regular_channel_payload):
        payload = regular_channel_payload.copy()
        payload["event"]["user_profile"] = {"is_stranger": True}

        decision = extractor._should_process_payload(payload)
        assert decision.should_process is False
        assert decision.should_delete_channel is False
        assert "external user" in decision.reason

    def test_cross_team_detection(self, extractor, regular_channel_payload):
        payload = regular_channel_payload.copy()
        payload["event"]["user_team"] = "T87654321"

        decision = extractor._should_process_payload(payload)
        assert decision.should_process is False
        assert decision.should_delete_channel is False
        assert "external team message" in decision.reason


class TestSlackChannelDeletion:
    """Test suite for Slack channel deletion webhook handling."""

    @pytest.fixture
    def extractor(self):
        return SlackWebhookExtractor()

    @pytest.fixture
    def channel_deleted_payload(self):
        """Sample channel_deleted webhook payload."""
        return {
            "token": "VERIFICATION_TOKEN",
            "team_id": "T123456789",
            "api_app_id": "A123456789",
            "event": {
                "type": "channel_deleted",
                "channel": "C123456789",
                "event_ts": "1234567890.123456",
            },
            "type": "event_callback",
            "event_id": "Ev123456789",
            "event_time": 1234567890,
        }

    @pytest.mark.asyncio
    async def test_channel_deleted_event_handling(self, extractor, channel_deleted_payload):
        """Test that channel_deleted events are handled correctly."""
        from unittest.mock import AsyncMock, patch

        # Create mock dependencies
        mock_db_pool = AsyncMock()
        AsyncMock()

        with patch(
            "connectors.slack.slack_webhook_extractor.slack_pruner.delete_channel"
        ) as mock_delete_channel:
            mock_delete_channel.return_value = True

            # Call the event handler directly
            result = await extractor._handle_channel_deleted_event(
                event=channel_deleted_payload["event"],
                db_pool=mock_db_pool,
                tenant_id="test-tenant",
            )

            # Verify pruner was called with correct parameters
            mock_delete_channel.assert_called_once_with(
                channel_id="C123456789", tenant_id="test-tenant", db_pool=mock_db_pool
            )

            # Should return empty list (no artifacts created for deletions)
            assert result == []

    @pytest.mark.asyncio
    async def test_channel_deleted_event_missing_channel_id(self, extractor):
        """Test that channel_deleted events without channel ID are handled gracefully."""
        from unittest.mock import AsyncMock, patch

        event = {
            "type": "channel_deleted",
            "event_ts": "1234567890.123456",
            # Missing channel field
        }

        mock_db_pool = AsyncMock()

        with patch(
            "connectors.slack.slack_webhook_extractor.slack_pruner.delete_channel"
        ) as mock_delete_channel:
            result = await extractor._handle_channel_deleted_event(
                event=event, db_pool=mock_db_pool, tenant_id="test-tenant"
            )

            # Should not call pruner
            mock_delete_channel.assert_not_called()

            # Should return empty list
            assert result == []

    @pytest.mark.asyncio
    async def test_channel_deleted_event_pruner_failure(self, extractor, channel_deleted_payload):
        """Test that channel_deleted events handle pruner failures gracefully."""
        from unittest.mock import AsyncMock, patch

        mock_db_pool = AsyncMock()

        with patch(
            "connectors.slack.slack_webhook_extractor.slack_pruner.delete_channel"
        ) as mock_delete_channel:
            mock_delete_channel.return_value = False  # Simulate failure

            result = await extractor._handle_channel_deleted_event(
                event=channel_deleted_payload["event"],
                db_pool=mock_db_pool,
                tenant_id="test-tenant",
            )

            # Should still return empty list even on failure
            assert result == []

    @pytest.mark.asyncio
    async def test_slack_event_routing_channel_deleted(self, extractor, channel_deleted_payload):
        """Test that _handle_slack_event routes channel_deleted events correctly."""
        from unittest.mock import AsyncMock, patch

        mock_db_pool = AsyncMock()
        mock_trigger_indexing = AsyncMock()

        with patch.object(extractor, "_handle_channel_deleted_event") as mock_handler:
            mock_handler.return_value = []

            result = await extractor._handle_slack_event(
                job_id="test-job-123",
                event=channel_deleted_payload["event"],
                db_pool=mock_db_pool,
                tenant_id="test-tenant",
                trigger_indexing=mock_trigger_indexing,
            )

            # Verify the channel deletion handler was called
            mock_handler.assert_called_once_with(
                channel_deleted_payload["event"], mock_db_pool, "test-tenant"
            )

            assert result == []


class TestNonPublicChannelDeletion:
    """Test suite for non-public Slack channel deletion handling."""

    @pytest.fixture
    def extractor(self):
        return SlackWebhookExtractor()

    @pytest.fixture
    def private_group_message_payload(self):
        """Sample private group message payload."""
        return {
            "token": "VERIFICATION_TOKEN",
            "team_id": "T123456789",
            "api_app_id": "A123456789",
            "event": {
                "user": "U123456789",
                "type": "message",
                "ts": "1755207036.275549",
                "client_msg_id": "test-msg-id",
                "text": "private group message",
                "team": "T123456789",
                "channel": "G123456789",
                "event_ts": "1755207036.275549",
                "channel_type": "group",
            },
            "type": "event_callback",
            "event_id": "Ev123456789",
            "event_time": 1755207036,
        }

    @pytest.fixture
    def direct_message_payload(self):
        """Sample direct message payload."""
        return {
            "token": "VERIFICATION_TOKEN",
            "team_id": "T123456789",
            "api_app_id": "A123456789",
            "event": {
                "user": "U123456789",
                "type": "message",
                "ts": "1755207036.275549",
                "client_msg_id": "test-msg-id",
                "text": "direct message",
                "team": "T123456789",
                "channel": "D123456789",
                "event_ts": "1755207036.275549",
                "channel_type": "im",
            },
            "type": "event_callback",
            "event_id": "Ev123456789",
            "event_time": 1755207036,
        }

    @pytest.fixture
    def multi_party_dm_payload(self):
        """Sample multi-party DM payload."""
        return {
            "token": "VERIFICATION_TOKEN",
            "team_id": "T123456789",
            "api_app_id": "A123456789",
            "event": {
                "user": "U123456789",
                "type": "message",
                "ts": "1755207036.275549",
                "client_msg_id": "test-msg-id",
                "text": "multi-party dm message",
                "team": "T123456789",
                "channel": "G987654321",
                "event_ts": "1755207036.275549",
                "channel_type": "mpim",
            },
            "type": "event_callback",
            "event_id": "Ev123456789",
            "event_time": 1755207036,
        }

    def test_should_process_payload_returns_delete_channel_for_private_group(
        self, extractor, private_group_message_payload
    ):
        """Test that private group messages trigger deletion."""
        decision = extractor._should_process_payload(private_group_message_payload)
        assert decision.should_process is False
        assert decision.should_delete_channel is True
        assert "private channel/DM" in decision.reason
        assert "group" in decision.reason

    def test_should_process_payload_returns_delete_channel_for_direct_message(
        self, extractor, direct_message_payload
    ):
        """Test that direct messages trigger deletion."""
        decision = extractor._should_process_payload(direct_message_payload)
        assert decision.should_process is False
        assert decision.should_delete_channel is True
        assert "private channel/DM" in decision.reason
        assert "im" in decision.reason

    def test_should_process_payload_returns_delete_channel_for_multi_party_dm(
        self, extractor, multi_party_dm_payload
    ):
        """Test that multi-party DMs trigger deletion."""
        decision = extractor._should_process_payload(multi_party_dm_payload)
        assert decision.should_process is False
        assert decision.should_delete_channel is True
        assert "private channel/DM" in decision.reason
        assert "mpim" in decision.reason

    @pytest.mark.asyncio
    async def test_handle_non_public_channel_deletion_success(self, extractor):
        """Test successful non-public channel deletion."""
        from unittest.mock import AsyncMock, patch

        event = {
            "type": "message",
            "channel": "G123456789",
            "channel_type": "group",
            "text": "test message",
        }

        mock_db_pool = AsyncMock()

        with patch(
            "connectors.slack.slack_webhook_extractor.slack_pruner.delete_channel"
        ) as mock_delete_channel:
            mock_delete_channel.return_value = True

            await extractor._handle_non_public_channel_deletion(
                job_id="test-job-123",
                event=event,
                db_pool=mock_db_pool,
                tenant_id="test-tenant",
            )

            # Verify pruner was called with correct parameters
            mock_delete_channel.assert_called_once_with(
                channel_id="G123456789",
                tenant_id="test-tenant",
                db_pool=mock_db_pool,
            )

    @pytest.mark.asyncio
    async def test_handle_non_public_channel_deletion_missing_channel_id(self, extractor):
        """Test graceful handling when channel ID is missing."""
        from unittest.mock import AsyncMock, patch

        event = {
            "type": "message",
            "channel_type": "group",
            "text": "test message",
            # Missing channel field
        }

        mock_db_pool = AsyncMock()

        with patch(
            "connectors.slack.slack_webhook_extractor.slack_pruner.delete_channel"
        ) as mock_delete_channel:
            await extractor._handle_non_public_channel_deletion(
                job_id="test-job-123",
                event=event,
                db_pool=mock_db_pool,
                tenant_id="test-tenant",
            )

            # Should not call pruner when channel ID is missing
            mock_delete_channel.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_non_public_channel_deletion_pruner_failure(self, extractor):
        """Test handling when pruner deletion fails."""
        from unittest.mock import AsyncMock, patch

        event = {
            "type": "message",
            "channel": "G123456789",
            "channel_type": "group",
            "text": "test message",
        }

        mock_db_pool = AsyncMock()

        with patch(
            "connectors.slack.slack_webhook_extractor.slack_pruner.delete_channel"
        ) as mock_delete_channel:
            mock_delete_channel.return_value = False  # Simulate failure

            # Should not raise an exception even when deletion fails
            await extractor._handle_non_public_channel_deletion(
                job_id="test-job-123",
                event=event,
                db_pool=mock_db_pool,
                tenant_id="test-tenant",
            )

            # Verify pruner was still called
            mock_delete_channel.assert_called_once_with(
                channel_id="G123456789",
                tenant_id="test-tenant",
                db_pool=mock_db_pool,
            )

    @pytest.mark.asyncio
    async def test_handle_non_public_channel_deletion_exception_handling(self, extractor):
        """Test handling when pruner raises an exception."""
        from unittest.mock import AsyncMock, patch

        event = {
            "type": "message",
            "channel": "G123456789",
            "channel_type": "group",
            "text": "test message",
        }

        mock_db_pool = AsyncMock()

        with patch(
            "connectors.slack.slack_webhook_extractor.slack_pruner.delete_channel"
        ) as mock_delete_channel:
            mock_delete_channel.side_effect = Exception("Database error")

            # Should not raise an exception even when pruner throws
            await extractor._handle_non_public_channel_deletion(
                job_id="test-job-123",
                event=event,
                db_pool=mock_db_pool,
                tenant_id="test-tenant",
            )

            # Verify pruner was called
            mock_delete_channel.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_job_handles_non_public_channel_deletion(self, extractor):
        """Test that process_job handles non-public channel deletion flow."""
        from unittest.mock import AsyncMock, patch

        from connectors.slack import SlackWebhookConfig

        config = SlackWebhookConfig(
            body={
                "token": "VERIFICATION_TOKEN",
                "team_id": "T123456789",
                "api_app_id": "A123456789",
                "event": {
                    "user": "U123456789",
                    "type": "message",
                    "channel": "G123456789",
                    "channel_type": "group",
                    "text": "private group message",
                },
                "type": "event_callback",
                "event_id": "Ev123456789",
            },
            tenant_id="test-tenant",
        )

        mock_db_pool = AsyncMock()
        mock_trigger_indexing = AsyncMock()

        with patch.object(extractor, "_handle_non_public_channel_deletion") as mock_delete:
            await extractor.process_job(
                job_id="test-job-123",
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

            # Verify deletion handler was called
            mock_delete.assert_called_once_with(
                "test-job-123",
                config.body["event"],
                mock_db_pool,
                "test-tenant",
            )

        # Verify no artifacts were stored (deletion flow shouldn't create artifacts)
        with patch.object(extractor, "store_artifacts_batch") as mock_store:
            await extractor.process_job(
                job_id="test-job-123",
                config=config,
                db_pool=mock_db_pool,
                trigger_indexing=mock_trigger_indexing,
            )

            mock_store.assert_not_called()
