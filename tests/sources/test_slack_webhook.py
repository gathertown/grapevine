# TODO @vic rewrite tests for SlackWebhookExtractor
# """
# Comprehensive tests for SlackWebhookSource.

# Tests webhook payload processing, real-time message handling, database reconstruction,
# and document creation.
# """

# import json
# from datetime import UTC, datetime
# from unittest.mock import AsyncMock, Mock, patch

# import pytest

# from src.clients.slack import SlackClient
# from connectors.slack.slack_channel_document import SlackChannelDocument
# from src.sources.slack_webhook import SlackWebhookSource


# class TestSlackWebhookSource:
#     """Test suite for SlackWebhookSource."""

#     @pytest.fixture
#     def mock_slack_client(self):
#         """Create a mock Slack client."""
#         client = Mock(spec=SlackClient)

#         # Mock channel info
#         client.get_channel_info.side_effect = lambda channel_id: {
#             "C12345678": {"id": "C12345678", "name": "general"},
#             "C87654321": {"id": "C87654321", "name": "random"},
#         }.get(channel_id, {})

#         # Mock user info
#         client.get_user_info.side_effect = lambda user_id: {
#             "U12345678": {
#                 "id": "U12345678",
#                 "profile": {"display_name": "John", "real_name": "John Doe"},
#                 "real_name": "John Doe",
#                 "name": "john.doe",
#             },
#             "U87654321": {
#                 "id": "U87654321",
#                 "profile": {"display_name": "Jane", "real_name": "Jane Smith"},
#                 "real_name": "Jane Smith",
#                 "name": "jane.smith",
#             },
#         }.get(user_id)

#         return client

#     @pytest.fixture
#     def source(self, mock_slack_client):
#         """Create SlackWebhookSource instance."""
#         return SlackWebhookSource(slack_client=mock_slack_client)

#     # Input Validation Tests
#     def test_validate_input_valid_json_payload(self, source):
#         """Test input validation with valid JSON payload."""
#         body = json.dumps({"type": "event_callback", "event": {"type": "message"}}).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         assert source.validate_input(raw_data) == True

#     def test_validate_input_valid_form_payload(self, source):
#         """Test input validation with valid form-encoded payload."""
#         body = b"payload=%7B%22type%22%3A%22event_callback%22%7D"  # URL-encoded JSON
#         headers = {"content-type": "application/x-www-form-urlencoded"}
#         raw_data = (body, headers)

#         assert source.validate_input(raw_data) == True

#     def test_validate_input_invalid_format(self, source):
#         """Test input validation with invalid format."""
#         # Wrong data structure
#         assert source.validate_input("not_a_tuple") == False

#         # Wrong tuple length
#         assert source.validate_input((b"body",)) == False

#         # Wrong types
#         assert source.validate_input(("string_body", {})) == False
#         assert source.validate_input((b"body", "string_headers")) == False

#     def test_validate_input_unsupported_content_type(self, source):
#         """Test input validation with unsupported content type."""
#         body = b"some data"
#         headers = {"content-type": "text/plain"}
#         raw_data = (body, headers)

#         assert source.validate_input(raw_data) == False

#     def test_validate_input_missing_content_type(self, source):
#         """Test input validation with missing content type."""
#         body = b"some data"
#         headers = {}
#         raw_data = (body, headers)

#         assert source.validate_input(raw_data) == False

#     # Webhook Payload Parsing Tests
#     def test_parse_webhook_payload_json(self, source):
#         """Test parsing JSON webhook payload."""
#         payload_data = {"type": "event_callback", "event": {"type": "message", "text": "Hello"}}
#         body = json.dumps(payload_data).encode()
#         headers = {"content-type": "application/json"}

#         result = source._SlackWebhookSource__parse_webhook_payload(body, headers)

#         assert result == payload_data

#     def test_parse_webhook_payload_form_encoded_with_payload_field(self, source):
#         """Test parsing form-encoded payload with payload field."""
#         payload_data = {"type": "event_callback", "event": {"type": "message"}}
#         payload_json = json.dumps(payload_data)
#         body = f"payload={payload_json}".encode()
#         headers = {"content-type": "application/x-www-form-urlencoded"}

#         result = source._SlackWebhookSource__parse_webhook_payload(body, headers)

#         assert result == payload_data

#     def test_parse_webhook_payload_form_encoded_direct_fields(self, source):
#         """Test parsing form-encoded payload with direct fields."""
#         body = b"type=event_callback&team_id=T12345678"
#         headers = {"content-type": "application/x-www-form-urlencoded"}

#         result = source._SlackWebhookSource__parse_webhook_payload(body, headers)

#         assert result == {"type": "event_callback", "team_id": "T12345678"}

#     def test_parse_webhook_payload_invalid_json(self, source):
#         """Test parsing invalid JSON payload."""
#         body = b"invalid json"
#         headers = {"content-type": "application/json"}

#         with pytest.raises(json.JSONDecodeError, match="Expecting value"):
#             source._SlackWebhookSource__parse_webhook_payload(body, headers)

#     def test_parse_webhook_payload_unsupported_content_type(self, source):
#         """Test parsing payload with unsupported content type."""
#         body = b"some data"
#         headers = {"content-type": "text/plain"}

#         with pytest.raises(ValueError, match="Unsupported content type"):
#             source._SlackWebhookSource__parse_webhook_payload(body, headers)

#     # Event Handling Tests
#     @pytest.mark.asyncio
#     async def test_handle_url_verification(self, source):
#         """Test handling URL verification challenge."""
#         body = json.dumps(
#             {
#                 "type": "url_verification",
#                 "challenge": "test_challenge_string",
#                 "token": "verification_token",
#             }
#         ).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         result = await source.process_data(raw_data)

#         assert result == []  # URL verification returns empty list

#     @pytest.mark.asyncio
#     async def test_handle_message_event(self, source):
#         """Test handling basic message event."""
#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Hello world!",
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1705339200.000100",
#                 "client_msg_id": "msg_001",
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         with patch.object(
#             source, "_SlackWebhookSource__create_complete_document", new_callable=AsyncMock
#         ) as mock_complete:
#             mock_complete.return_value = Mock(spec=SlackChannelDocument)

#             result = await source.process_data(raw_data)

#             assert len(result) == 1
#             mock_complete.assert_called_once()

#     @pytest.mark.asyncio
#     async def test_handle_message_event_with_files(self, source):
#         """Test handling message event with file attachments."""
#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Check this file!",
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1705339200.000100",
#                 "client_msg_id": "msg_001",
#                 "files": [
#                     {
#                         "name": "example.png",
#                         "mimetype": "image/png",
#                         "url_private": "https://files.slack.com/files-pri/example.png",
#                     }
#                 ],
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         with patch.object(
#             source, "_SlackWebhookSource__create_complete_document", new_callable=AsyncMock
#         ) as mock_complete:
#             mock_doc = Mock(spec=SlackChannelDocument)
#             mock_complete.return_value = mock_doc

#             result = await source.process_data(raw_data)

#             assert len(result) == 1
#             # Verify the document contains file info
#             call_args = mock_complete.call_args[0][0]  # First argument to create_complete_document
#             message_text = call_args.raw_data["messages"][0]["text"]
#             assert "[Image: example.png]" in message_text

#     @pytest.mark.asyncio
#     async def test_handle_message_event_with_thread(self, source):
#         """Test handling threaded message event."""
#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Reply in thread",
#                 "user": "U87654321",
#                 "channel": "C12345678",
#                 "ts": "1705339260.000200",
#                 "client_msg_id": "msg_002",
#                 "thread_ts": "1705339200.000100",
#                 "parent_user_id": "U12345678",
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         with patch.object(
#             source, "_SlackWebhookSource__create_complete_document", new_callable=AsyncMock
#         ) as mock_complete:
#             mock_doc = Mock(spec=SlackChannelDocument)
#             mock_complete.return_value = mock_doc

#             result = await source.process_data(raw_data)

#             assert len(result) == 1
#             # Verify thread information is preserved
#             call_args = mock_complete.call_args[0][0]
#             message_data = call_args.raw_data["messages"][0]
#             assert message_data["thread_ts"] == "1705339200.000100"
#             assert message_data["parent_user_id"] == "U12345678"

#     @pytest.mark.asyncio
#     async def test_handle_message_changed_event(self, source):
#         """Test handling message edit/change event."""
#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "subtype": "message_changed",
#                 "channel": "C12345678",
#                 "message": {
#                     "type": "message",
#                     "text": "Edited message content",
#                     "user": "U12345678",
#                     "ts": "1705339200.000100",
#                     "client_msg_id": "msg_001",
#                 },
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         with patch.object(
#             source, "_SlackWebhookSource__create_complete_document", new_callable=AsyncMock
#         ) as mock_complete:
#             mock_doc = Mock(spec=SlackChannelDocument)
#             mock_complete.return_value = mock_doc

#             result = await source.process_data(raw_data)

#             assert len(result) == 1
#             # Verify edited message content
#             call_args = mock_complete.call_args[0][0]
#             message_data = call_args.raw_data["messages"][0]
#             assert message_data["text"] == "Edited message content"

#     @pytest.mark.asyncio
#     async def test_handle_message_deleted_event(self, source):
#         """Test handling message deletion event."""
#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "subtype": "message_deleted",
#                 "channel": "C12345678",
#                 "deleted_ts": "1705339200.000100",
#                 "previous_message": {
#                     "type": "message",
#                     "text": "This message was deleted",
#                     "user": "U12345678",
#                     "ts": "1705339200.000100",
#                     "client_msg_id": "msg_001",
#                 },
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.fetchval = AsyncMock(return_value=0)  # No chunks remaining
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             mock_reconstruct.return_value = None  # No document remains after deletion

#             result = await source.process_data(raw_data)

#             assert result == []  # No documents returned for deletion
#             # Verify deletion operations were called
#             mock_conn.execute.assert_called()

#     @pytest.mark.asyncio
#     async def test_handle_invalid_message_event(self, source):
#         """Test handling message event with missing required fields."""
#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Hello",
#                 # Missing user, channel, ts
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         result = await source.process_data(raw_data)

#         assert result == []  # Invalid events return empty list

#     @pytest.mark.asyncio
#     async def test_handle_system_message_event(self, source):
#         """Test handling system message (should be ignored)."""
#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "subtype": "channel_join",
#                 "text": "User joined channel",
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1705339200.000100",
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         result = await source.process_data(raw_data)

#         assert result == []  # System messages should be ignored

#     @pytest.mark.asyncio
#     async def test_handle_unsupported_event_type(self, source):
#         """Test handling unsupported event types."""
#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "reaction_added",  # Unsupported event type
#                 "reaction": "thumbsup",
#                 "user": "U12345678",
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         result = await source.process_data(raw_data)

#         assert result == []  # Unsupported events return empty list

#     # Text Cleaning Tests
#     def test_clean_slack_text_basic(self, source):
#         """Test basic text cleaning."""
#         dirty_text = "  Hello   world!  \n\n  "
#         clean_text = source._clean_slack_text(dirty_text)
#         assert clean_text == "Hello world!"

#     def test_clean_slack_text_html_entities(self, source):
#         """Test HTML entity decoding."""
#         html_text = "Hello &amp; goodbye &lt;test&gt;"
#         clean_text = source._clean_slack_text(html_text)
#         assert clean_text == "Hello & goodbye <test>"

#     def test_clean_slack_text_empty(self, source):
#         """Test cleaning empty text."""
#         assert source._clean_slack_text("") == ""
#         assert source._clean_slack_text(None) == ""

#     # Database Reconstruction Tests
#     @pytest.mark.asyncio
#     async def test_reconstruct_from_database_success(self, source):
#         """Test successful document reconstruction from database."""
#         doc_id = "C12345678_2025-01-15"

#         # Mock database connection and responses
#         mock_conn = AsyncMock()

#         # Mock channel info fetchrow call
#         mock_conn.fetchrow.return_value = {"channel_name": "general"}

#         # Mock chunks
#         mock_conn.fetch.return_value = [
#             {
#                 "content": "Hello world!",
#                 "metadata": {
#                     "user_id": "U12345678",
#                     "username": "John",
#                     "text": "Hello world!",
#                     "timestamp": "1736942400.000100",
#                     "formatted_time": "2025-01-15 12:00:00",
#                     "message_id": "msg_001",
#                 },
#                 "created_at": datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC),
#             }
#         ]

#         result = await source._SlackWebhookSource__reconstruct_from_database(doc_id, mock_conn)

#         assert result is not None
#         assert isinstance(result, SlackChannelDocument)
#         assert result.id == doc_id
#         assert result.raw_data["channel_id"] == "C12345678"
#         assert len(result.raw_data["messages"]) == 1

#     @pytest.mark.asyncio
#     async def test_reconstruct_from_database_not_found(self, source):
#         """Test document reconstruction when document not found."""
#         doc_id = "C_NONEXISTENT_2025-01-15"

#         mock_conn = AsyncMock()
#         mock_conn.fetchrow.return_value = None  # Channel info not found
#         mock_conn.fetch.return_value = []  # No chunks found

#         result = await source._SlackWebhookSource__reconstruct_from_database(doc_id, mock_conn)

#         assert result is None

#     @pytest.mark.asyncio
#     async def test_reconstruct_from_database_no_chunks(self, source):
#         """Test document reconstruction when no chunks exist."""
#         doc_id = "C12345678_2025-01-15"

#         mock_conn = AsyncMock()
#         mock_conn.fetchrow.return_value = {
#             "metadata": {"channel_id": "C12345678", "channel_name": "general", "date": "2025-01-15"}
#         }
#         mock_conn.fetch.return_value = []  # No chunks

#         result = await source._SlackWebhookSource__reconstruct_from_database(doc_id, mock_conn)

#         assert result is None

#     @pytest.mark.asyncio
#     async def test_reconstruct_from_database_error_handling(self, source):
#         """Test error handling during database reconstruction."""
#         doc_id = "C12345678_2025-01-15"

#         mock_conn = AsyncMock()
#         mock_conn.fetchrow.side_effect = Exception("Database error")

#         result = await source._SlackWebhookSource__reconstruct_from_database(doc_id, mock_conn)

#         assert result is None  # Should return None on error

#     # Complete Document Creation Tests
#     @pytest.mark.asyncio
#     async def test_create_complete_document_new_document(self, source):
#         """Test creating complete document when no existing document."""
#         new_doc = SlackChannelDocument(
#             id="C12345678_2025-01-15",
#             raw_data={
#                 "channel_id": "C12345678",
#                 "channel_name": "general",
#                 "date": "2025-01-15",
#                 "messages": [
#                     {
#                         "user_id": "U12345678",
#                         "text": "New message",
#                         "client_msg_id": "msg_001",
#                         "timestamp": "2025-01-15T12:00:00+00:00",
#                     }
#                 ],
#             },
#         )

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             mock_reconstruct.return_value = None  # No existing document

#             result = await source._SlackWebhookSource__create_complete_document(new_doc)

#             assert result == new_doc  # Should return the new document as-is
#             # Verify old chunks were deleted
#             mock_conn.execute.assert_called()

#     @pytest.mark.asyncio
#     async def test_create_complete_document_merge_with_existing(self, source):
#         """Test merging new message with existing document."""
#         new_doc = SlackChannelDocument(
#             id="C12345678_2025-01-15",
#             raw_data={
#                 "channel_id": "C12345678",
#                 "channel_name": "general",
#                 "date": "2025-01-15",
#                 "messages": [
#                     {
#                         "user_id": "U87654321",
#                         "text": "New message",
#                         "client_msg_id": "msg_002",
#                         "timestamp": "1705339260.000200",
#                     }
#                 ],
#             },
#         )

#         existing_doc = SlackChannelDocument(
#             id="C12345678_2025-01-15",
#             raw_data={
#                 "channel_id": "C12345678",
#                 "channel_name": "general",
#                 "date": "2025-01-15",
#                 "messages": [
#                     {
#                         "user_id": "U12345678",
#                         "text": "Existing message",
#                         "client_msg_id": "msg_001",
#                         "timestamp": "1705339200.000100",
#                     }
#                 ],
#             },
#         )

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             mock_reconstruct.return_value = existing_doc

#             result = await source._SlackWebhookSource__create_complete_document(new_doc)

#             assert result is not None
#             # Should have both messages, sorted by timestamp
#             assert len(result.raw_data["messages"]) == 2
#             messages = result.raw_data["messages"]
#             assert messages[0]["client_msg_id"] == "msg_001"  # Earlier timestamp
#             assert messages[1]["client_msg_id"] == "msg_002"  # Later timestamp

#     @pytest.mark.asyncio
#     async def test_create_complete_document_update_existing_message(self, source):
#         """Test updating existing message in document."""
#         new_doc = SlackChannelDocument(
#             id="C12345678_2025-01-15",
#             raw_data={
#                 "channel_id": "C12345678",
#                 "channel_name": "general",
#                 "date": "2025-01-15",
#                 "messages": [
#                     {
#                         "user_id": "U12345678",
#                         "text": "Updated message text",
#                         "client_msg_id": "msg_001",  # Same ID as existing
#                         "timestamp": "1705339200.000100",
#                     }
#                 ],
#             },
#         )

#         existing_doc = SlackChannelDocument(
#             id="C12345678_2025-01-15",
#             raw_data={
#                 "channel_id": "C12345678",
#                 "channel_name": "general",
#                 "date": "2025-01-15",
#                 "messages": [
#                     {
#                         "user_id": "U12345678",
#                         "text": "Original message text",
#                         "client_msg_id": "msg_001",
#                         "timestamp": "1705339200.000100",
#                     }
#                 ],
#             },
#         )

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             mock_reconstruct.return_value = existing_doc

#             result = await source._SlackWebhookSource__create_complete_document(new_doc)

#             assert result is not None
#             # Should have one message with updated content
#             assert len(result.raw_data["messages"]) == 1
#             message = result.raw_data["messages"][0]
#             assert message["text"] == "Updated message text"
#             assert message["client_msg_id"] == "msg_001"

#     # Error Handling and Edge Cases
#     @pytest.mark.asyncio
#     async def test_process_data_malformed_json(self, source):
#         """Test handling malformed JSON payload."""
#         body = b"invalid json {"
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         with pytest.raises(ValueError):
#             await source.process_data(raw_data)

#     @pytest.mark.asyncio
#     async def test_process_data_empty_payload(self, source):
#         """Test handling empty payload."""
#         body = b""
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         with pytest.raises(ValueError, match="Invalid JSON payload"):
#             await source.process_data(raw_data)

#     @pytest.mark.asyncio
#     async def test_handle_message_event_api_failure(self, source):
#         """Test handling message event when Slack API calls fail."""
#         source.slack_client.get_channel_info.side_effect = Exception("API Error")

#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Hello!",
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1705339200.000100",
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         result = await source.process_data(raw_data)

#         assert result == []  # Should handle API failures gracefully

#     @pytest.mark.asyncio
#     async def test_handle_message_event_no_text_no_files(self, source):
#         """Test handling message with no text and no files (should be ignored)."""
#         event_data = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "",  # Empty text
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1705339200.000100",
#                 # No files or attachments
#             },
#         }
#         body = json.dumps(event_data).encode()
#         headers = {"content-type": "application/json"}
#         raw_data = (body, headers)

#         result = await source.process_data(raw_data)

#         assert result == []  # Messages with no content should be ignored


# class TestSlackWebhookMultiDayHandling:
#     """Test suite specifically for multi-day document handling in slack_webhook."""

#     @pytest.fixture
#     def mock_slack_client(self):
#         """Create a mock Slack client."""
#         client = Mock(spec=SlackClient)
#         client.get_channel_info.return_value = {"id": "C12345678", "name": "general"}
#         client.get_user_info.side_effect = lambda user_id: {
#             "U12345678": {
#                 "id": "U12345678",
#                 "profile": {"display_name": "John", "real_name": "John Doe"},
#                 "real_name": "John Doe",
#             },
#             "U87654321": {
#                 "id": "U87654321",
#                 "profile": {"display_name": "Jane", "real_name": "Jane Smith"},
#                 "real_name": "Jane Smith",
#             },
#         }.get(user_id)
#         return client

#     @pytest.fixture
#     def source(self, mock_slack_client):
#         """Create SlackWebhookSource instance."""
#         return SlackWebhookSource(slack_client=mock_slack_client)

#     @pytest.mark.asyncio
#     async def test_thread_root_and_reply_same_pt_day(self, source):
#         """Test thread root and reply both belong to same Pacific Time day."""
#         # Thread root at 2025-01-14 23:00 PST (07:00 UTC next day)
#         thread_root_event = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Thread root message",
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1736924400.000100",  # 2025-01-14 23:00:00 PST (07:00 UTC next day)
#                 "client_msg_id": "root_msg",
#             },
#         }

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             # No existing document - this is the first message
#             mock_reconstruct.return_value = None

#             # Process thread root
#             body = json.dumps(thread_root_event).encode()
#             result = await source.process_data((body, {"content-type": "application/json"}))

#             assert len(result) == 1

#             # Verify document ID uses thread root's PT date
#             doc = result[0]
#             assert doc.id == "C12345678_2025-01-14"
#             assert doc.raw_data["date"] == "2025-01-14"  # Pacific Time date
#             assert doc.raw_data["messages"][0]["text"] == "Thread root message"

#             # Verify reconstruction was called with correct document ID
#             mock_reconstruct.assert_called_once_with("C12345678_2025-01-14", mock_conn)

#     @pytest.mark.asyncio
#     async def test_thread_reply_different_pt_day_from_root(self, source):
#         """Test thread reply belongs to different PT day than thread root."""
#         # Thread reply at 2025-01-16 01:00 AM PST (09:00 UTC same day)
#         # but thread_ts points to message from 2025-01-14 PT day
#         thread_reply_event = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Reply to thread",
#                 "user": "U87654321",
#                 "channel": "C12345678",
#                 "ts": "1737018000.000200",  # 2025-01-16 01:00:00 PST (09:00 UTC same day)
#                 "client_msg_id": "reply_msg",
#                 "thread_ts": "1736924400.000100",  # Points to root from 2025-01-14 PT day
#                 "parent_user_id": "U12345678",
#             },
#         }

#         # Mock existing document from thread root's PT day
#         existing_doc = SlackChannelDocument(
#             id="C12345678_2025-01-14",
#             raw_data={
#                 "channel_id": "C12345678",
#                 "channel_name": "general",
#                 "date": "2025-01-14",  # Thread root's PT day
#                 "messages": [
#                     {
#                         "user_id": "U12345678",
#                         "text": "Original thread root",
#                         "timestamp": "2025-01-15T07:00:00+00:00",
#                         "message_ts": "1736924400.000100",
#                         "client_msg_id": "root_msg",
#                         "thread_ts": "",
#                         "channel_id": "C12345678",
#                         "channel_name": "general",
#                     }
#                 ],
#             },
#         )

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             mock_reconstruct.return_value = existing_doc

#             body = json.dumps(thread_reply_event).encode()
#             result = await source.process_data((body, {"content-type": "application/json"}))

#             assert len(result) == 1

#             # Verify document ID is routed to thread root's PT day (2025-01-14)
#             doc = result[0]
#             assert doc.id == "C12345678_2025-01-14"  # Should use thread_ts PT day

#             # Verify document date matches document ID date (not message date)
#             doc_id_date = doc.id.split("_")[-1]  # Extract date from document ID
#             assert doc.raw_data["date"] == doc_id_date, (
#                 f"Document date '{doc.raw_data['date']}' must match document ID date '{doc_id_date}'. "
#                 f"Thread replies should route to thread root's document with thread root's PT date, not message's PT date."
#             )
#             assert doc.raw_data["date"] == "2025-01-14", (
#                 "Document should use thread root's PT date (2025-01-14)"
#             )

#             # Verify reconstruction was called with thread root's PT day document ID
#             mock_reconstruct.assert_called_once_with("C12345678_2025-01-14", mock_conn)

#             # Verify the document has both messages: existing root + new reply
#             assert len(doc.raw_data["messages"]) == 2
#             messages = doc.raw_data["messages"]

#             # Thread root should be first (sorted by timestamp)
#             assert messages[0]["text"] == "Original thread root"
#             assert messages[0]["thread_ts"] == ""

#             # Thread reply should be second
#             assert messages[1]["text"] == "Reply to thread"
#             assert messages[1]["thread_ts"] == "1736924400.000100"  # Points to root
#             # Individual message should have its own PT date (2025-01-16)
#             assert messages[1]["date"] == "2025-01-16", "Message should have its own PT date"

#     @pytest.mark.asyncio
#     async def test_standalone_message_uses_message_pt_day(self, source):
#         """Test standalone message uses its own timestamp's PT day."""
#         # Standalone message at 2025-01-16 02:00 AM PST (10:00 UTC same day)
#         standalone_event = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Standalone message",
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1737021600.000300",  # 2025-01-16 02:00:00 PST (10:00 UTC same day)
#                 "client_msg_id": "standalone_msg",
#                 # No thread_ts - this is a standalone message
#             },
#         }

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             # No existing document - this is a new standalone message
#             mock_reconstruct.return_value = None

#             body = json.dumps(standalone_event).encode()
#             result = await source.process_data((body, {"content-type": "application/json"}))

#             assert len(result) == 1

#             # Verify document ID uses message timestamp's PT date
#             doc = result[0]
#             assert doc.id == "C12345678_2025-01-16"
#             assert doc.raw_data["date"] == "2025-01-16"
#             assert doc.raw_data["messages"][0]["text"] == "Standalone message"
#             assert doc.raw_data["messages"][0]["thread_ts"] == ""  # Empty thread_ts for standalone

#             # Verify document date matches document ID date
#             doc_id_date = doc.id.split("_")[-1]
#             assert doc.raw_data["date"] == doc_id_date, (
#                 f"Document date '{doc.raw_data['date']}' must match document ID date '{doc_id_date}'"
#             )

#             # Verify reconstruction was called with message's PT day document ID
#             mock_reconstruct.assert_called_once_with("C12345678_2025-01-16", mock_conn)

#     @pytest.mark.asyncio
#     async def test_document_reconstruction_cross_pt_days(self, source):
#         """Test document reconstruction includes messages from multiple UTC days but same PT day."""
#         # Message near PT day boundary - should reconstruct full PT day
#         boundary_event = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Message near PT boundary",
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1737018000.000400",  # 2025-01-16 01:00:00 PST (09:00 UTC same day)
#                 "client_msg_id": "boundary_msg",
#             },
#         }

#         # Mock existing document with messages spanning the PT day
#         existing_doc = SlackChannelDocument(
#             id="C12345678_2025-01-16",
#             raw_data={
#                 "channel_id": "C12345678",
#                 "channel_name": "general",
#                 "date": "2025-01-16",
#                 "messages": [
#                     {
#                         "user_id": "U12345678",
#                         "text": "Early PT day message",
#                         "timestamp": "2025-01-16T09:00:00+00:00",
#                         "message_ts": "1737018000.000001",
#                         "client_msg_id": "early_msg",
#                         "channel_id": "C12345678",
#                         "channel_name": "general",
#                     },
#                     {
#                         "user_id": "U87654321",
#                         "text": "Late PT day message",
#                         "timestamp": "2025-01-17T07:59:59+00:00",
#                         "message_ts": "1737104399.000002",
#                         "client_msg_id": "late_msg",
#                         "channel_id": "C12345678",
#                         "channel_name": "general",
#                     },
#                 ],
#             },
#         )

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             mock_reconstruct.return_value = existing_doc

#             body = json.dumps(boundary_event).encode()
#             result = await source.process_data((body, {"content-type": "application/json"}))

#             assert len(result) == 1

#             # Verify the complete document was created properly
#             doc = result[0]
#             assert doc.id == "C12345678_2025-01-16"

#             # Verify reconstruction was called with correct document ID
#             mock_reconstruct.assert_called_once_with("C12345678_2025-01-16", mock_conn)

#             # Verify all messages from the PT day are included plus the new message
#             assert len(doc.raw_data["messages"]) == 3
#             assert doc.raw_data["date"] == "2025-01-16"

#             # Check that new message was merged properly
#             message_texts = [msg["text"] for msg in doc.raw_data["messages"]]
#             assert "Message near PT boundary" in message_texts

#     @pytest.mark.asyncio
#     async def test_empty_thread_ts_treated_as_standalone(self, source):
#         """Test message with empty thread_ts is treated as standalone message."""
#         empty_thread_event = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Message with empty thread_ts",
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1737021600.000500",  # 2025-01-16 02:00:00 PST (10:00 UTC same day)
#                 "client_msg_id": "empty_thread_msg",
#                 "thread_ts": "",  # Empty string should be treated as no thread
#             },
#         }

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             # No existing document
#             mock_reconstruct.return_value = None

#             body = json.dumps(empty_thread_event).encode()
#             result = await source.process_data((body, {"content-type": "application/json"}))

#             assert len(result) == 1

#             # Verify document uses message timestamp's PT date, not thread logic
#             doc = result[0]
#             assert doc.id == "C12345678_2025-01-16"  # Should use message timestamp's PT date
#             assert doc.raw_data["date"] == "2025-01-16"

#             # Empty thread_ts should not affect PT day calculation
#             assert doc.raw_data["messages"][0]["thread_ts"] == ""
#             assert doc.raw_data["messages"][0]["text"] == "Message with empty thread_ts"

#             # Verify reconstruction was called with message's PT day document ID (not thread logic)
#             mock_reconstruct.assert_called_once_with("C12345678_2025-01-16", mock_conn)

#     @pytest.mark.asyncio
#     async def test_dst_boundary_handling(self, source):
#         """Test proper handling of messages around DST boundaries."""
#         # Test message during DST transition (Spring forward)
#         # 2025-03-09 23:00 PST (before DST starts)
#         dst_boundary_event = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Message during DST transition",
#                 "user": "U12345678",
#                 "channel": "C12345678",
#                 "ts": "1741586400.000600",  # 2025-03-09 23:00:00 PST (06:00 UTC next day)
#                 "client_msg_id": "dst_msg",
#             },
#         }

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             # No existing document
#             mock_reconstruct.return_value = None

#             body = json.dumps(dst_boundary_event).encode()
#             result = await source.process_data((body, {"content-type": "application/json"}))

#             assert len(result) == 1

#             # Verify proper PT date calculation during DST
#             doc = result[0]
#             assert doc.id == "C12345678_2025-03-09"  # Should handle DST correctly
#             assert doc.raw_data["date"] == "2025-03-09"
#             assert doc.raw_data["messages"][0]["text"] == "Message during DST transition"

#             # Verify reconstruction was called with correct DST-aware document ID
#             mock_reconstruct.assert_called_once_with("C12345678_2025-03-09", mock_conn)

#     @pytest.mark.asyncio
#     async def test_thread_reconstruction_includes_cross_day_messages(self, source):
#         """Test that thread reconstruction properly includes all thread messages across PT days."""
#         # Thread reply that should trigger reconstruction of thread root's PT day
#         cross_day_thread_event = {
#             "type": "event_callback",
#             "event": {
#                 "type": "message",
#                 "text": "Cross-day thread reply",
#                 "user": "U87654321",
#                 "channel": "C12345678",
#                 "ts": "1737093600.000700",  # 2025-01-16 22:00:00 PST (06:00 UTC next day)
#                 "client_msg_id": "cross_day_reply",
#                 "thread_ts": "1736924400.000100",  # Root from 2025-01-14 PT day
#                 "parent_user_id": "U12345678",
#             },
#         }

#         # Mock existing document from thread root's PT day with existing messages
#         existing_thread_doc = SlackChannelDocument(
#             id="C12345678_2025-01-14",
#             raw_data={
#                 "channel_id": "C12345678",
#                 "channel_name": "general",
#                 "date": "2025-01-14",  # Thread root's PT day
#                 "messages": [
#                     {
#                         "user_id": "U12345678",
#                         "text": "Original thread root",
#                         "timestamp": "2025-01-15T07:00:00+00:00",
#                         "message_ts": "1736924400.000100",
#                         "client_msg_id": "root_msg",
#                         "thread_ts": "",
#                         "channel_id": "C12345678",
#                         "channel_name": "general",
#                     },
#                     {
#                         "user_id": "U87654321",
#                         "text": "First reply",
#                         "timestamp": "2025-01-15T08:00:00+00:00",
#                         "message_ts": "1736928000.000101",
#                         "client_msg_id": "first_reply",
#                         "thread_ts": "1736924400.000100",
#                         "channel_id": "C12345678",
#                         "channel_name": "general",
#                     },
#                 ],
#             },
#         )

#         # Mock database operations
#         mock_conn = AsyncMock()
#         mock_conn.execute = AsyncMock()
#         mock_conn.close = AsyncMock()

#         mock_db = AsyncMock()
#         mock_db._get_connection = AsyncMock(return_value=mock_conn)

#         with (
#             patch("src.clients.supabase._db", mock_db),
#             patch.object(
#                 source, "_SlackWebhookSource__reconstruct_from_database", new_callable=AsyncMock
#             ) as mock_reconstruct,
#         ):
#             mock_reconstruct.return_value = existing_thread_doc

#             body = json.dumps(cross_day_thread_event).encode()
#             result = await source.process_data((body, {"content-type": "application/json"}))

#             assert len(result) == 1
#             reconstructed_doc = result[0]

#             # Verify reconstruction used thread root's PT day document ID
#             assert reconstructed_doc.id == "C12345678_2025-01-14"

#             # Verify document date matches document ID date
#             doc_id_date = reconstructed_doc.id.split("_")[-1]
#             assert reconstructed_doc.raw_data["date"] == doc_id_date, (
#                 f"Document date '{reconstructed_doc.raw_data['date']}' must match document ID date '{doc_id_date}'"
#             )

#             # Verify reconstruction was called with thread root's PT day document ID
#             mock_reconstruct.assert_called_once_with("C12345678_2025-01-14", mock_conn)

#             # Verify all thread messages are included across different calendar days
#             messages = reconstructed_doc.raw_data["messages"]
#             assert len(messages) == 3  # Original 2 + new cross-day reply

#             # Check that new cross-day message was merged properly
#             message_texts = [msg["text"] for msg in messages]
#             assert "Cross-day thread reply" in message_texts

#             # Verify thread structure is maintained
#             thread_replies = [
#                 msg for msg in messages if msg.get("thread_ts") == "1736924400.000100"
#             ]
#             assert len(thread_replies) == 2  # First reply + cross-day reply
