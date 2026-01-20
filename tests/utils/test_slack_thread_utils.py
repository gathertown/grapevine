"""Tests for Slack thread utilities."""

from typing import Any

from connectors.slack.slack_thread_utils import (
    create_missing_thread_root_placeholder,
    group_messages_by_threads,
    identify_missing_thread_roots,
    resolve_thread_relationships_with_placeholders,
    sort_messages_for_display,
    validate_thread_structure,
)


class TestSlackThreadUtilities:
    """Test Slack thread handling utilities."""

    def test_group_messages_by_threads(self):
        """Test grouping messages by their thread relationships."""
        messages = [
            {
                "message_ts": "1705320000.000001",
                "thread_ts": "",  # Standalone message
                "text": "Standalone message",
            },
            {
                "message_ts": "1705320001.000001",
                "thread_ts": "",  # Thread root
                "text": "Thread root",
            },
            {
                "message_ts": "1705320002.000001",
                "thread_ts": "1705320001.000001",  # Reply to root
                "text": "Thread reply 1",
            },
            {
                "message_ts": "1705320003.000001",
                "thread_ts": "1705320001.000001",  # Another reply
                "text": "Thread reply 2",
            },
        ]

        threads = group_messages_by_threads(messages)

        # Should have 2 threads: 1 standalone, 1 thread with root + 2 replies
        assert len(threads) == 2

        # Check standalone message
        assert "1705320000.000001" in threads
        assert len(threads["1705320000.000001"]) == 1

        # Check thread with replies
        assert "1705320001.000001" in threads
        assert len(threads["1705320001.000001"]) == 3  # Root + 2 replies

    def test_identify_missing_thread_roots(self):
        """Test identifying thread_ts values without corresponding root messages."""
        messages = [
            {
                "message_ts": "1705320001.000001",
                "thread_ts": "",  # This root exists
                "text": "Thread root",
            },
            {
                "message_ts": "1705320002.000001",
                "thread_ts": "1705320001.000001",  # Reply to existing root
                "text": "Thread reply",
            },
            {
                "message_ts": "1705320003.000001",
                "thread_ts": "1705320000.000001",  # Reply to MISSING root
                "text": "Orphaned reply",
            },
        ]

        missing_roots = identify_missing_thread_roots(messages)

        assert len(missing_roots) == 1
        assert "1705320000.000001" in missing_roots
        assert "1705320001.000001" not in missing_roots  # This root exists

    def test_identify_missing_thread_roots_no_missing(self):
        """Test case where no thread roots are missing."""
        messages = [
            {"message_ts": "1705320001.000001", "thread_ts": "", "text": "Thread root"},
            {
                "message_ts": "1705320002.000001",
                "thread_ts": "1705320001.000001",
                "text": "Thread reply",
            },
        ]

        missing_roots = identify_missing_thread_roots(messages)
        assert len(missing_roots) == 0

    def test_create_missing_thread_root_placeholder(self):
        """Test creating placeholder for missing thread root."""
        thread_ts = "1705320000.000001"
        channel_id = "C12345678"
        channel_name = "general"

        placeholder = create_missing_thread_root_placeholder(thread_ts, channel_id, channel_name)

        assert placeholder["message_ts"] == thread_ts
        assert placeholder["channel_id"] == channel_id
        assert placeholder["channel_name"] == channel_name
        assert placeholder["username"] == "MISSING_MESSAGE"
        assert placeholder["thread_ts"] == ""  # This IS the thread root
        assert placeholder["is_missing_placeholder"] == True
        assert "Missing thread root message" in placeholder["text"]

        # Should now use Pacific Time formatting
        assert "PST" in placeholder["formatted_time"] or "PDT" in placeholder["formatted_time"]

    def test_create_missing_thread_root_placeholder_invalid_timestamp(self):
        """Test placeholder creation with invalid timestamp."""
        thread_ts = "invalid_timestamp"
        channel_id = "C12345678"
        channel_name = "general"

        placeholder = create_missing_thread_root_placeholder(thread_ts, channel_id, channel_name)

        assert placeholder["message_ts"] == thread_ts
        assert placeholder["formatted_time"] == "Unknown time"
        assert placeholder["timestamp"] == thread_ts
        assert placeholder["is_missing_placeholder"] == True

    def test_resolve_thread_relationships_with_placeholders(self):
        """Test resolving thread relationships and adding placeholders."""
        messages = [
            {
                "message_ts": "1705320001.000001",
                "thread_ts": "",  # Root exists
                "text": "Thread root",
                "timestamp": "2024-01-15T12:00:01+00:00",
            },
            {
                "message_ts": "1705320002.000001",
                "thread_ts": "1705320001.000001",  # Reply to existing root
                "text": "Thread reply",
                "timestamp": "2024-01-15T12:00:02+00:00",
            },
            {
                "message_ts": "1705320003.000001",
                "thread_ts": "1705320000.000001",  # Reply to MISSING root
                "text": "Orphaned reply",
                "timestamp": "2024-01-15T12:00:03+00:00",
            },
        ]

        channel_id = "C12345678"
        channel_name = "general"

        result = resolve_thread_relationships_with_placeholders(messages, channel_id, channel_name)

        # Should have original 3 messages + 1 placeholder
        assert len(result) == 4

        # Find the placeholder
        placeholders = [msg for msg in result if msg.get("is_missing_placeholder")]
        assert len(placeholders) == 1

        placeholder = placeholders[0]
        assert placeholder["message_ts"] == "1705320000.000001"
        assert placeholder["username"] == "MISSING_MESSAGE"

        # Messages should be sorted by timestamp
        timestamps = [float(msg.get("message_ts", "0")) for msg in result]
        assert timestamps == sorted(timestamps)

    def test_validate_thread_structure(self):
        """Test validating thread structure and getting statistics."""
        messages: list[dict[str, Any]] = [
            {
                "message_ts": "1705320000.000001",
                "thread_ts": "",  # Standalone message
                "text": "Standalone",
            },
            {
                "message_ts": "1705320001.000001",
                "thread_ts": "",  # Thread root
                "text": "Thread root",
            },
            {
                "message_ts": "1705320002.000001",
                "thread_ts": "1705320001.000001",  # Thread reply
                "text": "Thread reply",
            },
            {
                "message_ts": "1705320003.000001",
                "thread_ts": "1705320099.000001",  # Orphaned reply (missing root)
                "text": "Orphaned reply",
            },
            {
                "message_ts": "1705320004.000001",
                "thread_ts": "",
                "text": "Placeholder",
                "is_missing_placeholder": True,  # Placeholder
            },
        ]

        stats = validate_thread_structure(messages)

        assert stats["total_messages"] == 5
        assert stats["standalone_messages"] == 1  # First message
        assert stats["thread_roots"] == 1  # Second message
        assert stats["thread_replies"] == 2  # Third and fourth messages
        assert stats["placeholders_added"] == 1  # Fifth message
        assert stats["orphaned_replies"] == 1  # Fourth message (missing root)
        assert stats["threads_count"] == 4  # All different thread groups

    def test_sort_messages_for_display(self):
        """Test sorting messages for optimal display (threads together)."""
        messages = [
            {
                "message_ts": "1705320003.000001",
                "thread_ts": "1705320001.000001",  # Thread reply (out of order)
                "text": "Thread reply",
            },
            {
                "message_ts": "1705320000.000001",
                "thread_ts": "",  # Standalone message
                "text": "Standalone",
            },
            {
                "message_ts": "1705320001.000001",
                "thread_ts": "",  # Thread root (out of order)
                "text": "Thread root",
            },
            {
                "message_ts": "1705320002.000001",
                "thread_ts": "1705320001.000001",  # Another thread reply
                "text": "Thread reply 2",
            },
        ]

        sorted_messages = sort_messages_for_display(messages)

        # Should be sorted by thread root timestamp, with replies following their roots
        expected_order = [
            "1705320000.000001",  # Standalone (earliest root)
            "1705320001.000001",  # Thread root (second earliest root)
            "1705320002.000001",  # First reply to thread root
            "1705320003.000001",  # Second reply to thread root
        ]

        actual_order = [msg["message_ts"] for msg in sorted_messages]
        assert actual_order == expected_order

    def test_sort_messages_for_display_with_placeholders(self):
        """Test sorting messages that include placeholders."""
        messages: list[dict[str, Any]] = [
            {
                "message_ts": "1705320002.000001",
                "thread_ts": "1705320001.000001",  # Reply to placeholder
                "text": "Reply to missing root",
            },
            {
                "message_ts": "1705320001.000001",
                "thread_ts": "",  # Placeholder for missing root
                "text": "Missing root placeholder",
                "is_missing_placeholder": True,
            },
            {
                "message_ts": "1705320003.000001",
                "thread_ts": "",  # Regular message
                "text": "Regular message",
            },
        ]

        sorted_messages = sort_messages_for_display(messages)

        # Should have placeholder first (earliest timestamp), then its reply, then regular message
        expected_order = [
            "1705320001.000001",  # Placeholder root
            "1705320002.000001",  # Reply to placeholder
            "1705320003.000001",  # Regular message
        ]

        actual_order = [msg["message_ts"] for msg in sorted_messages]
        assert actual_order == expected_order

    def test_complex_thread_scenario(self):
        """Test a complex scenario with multiple threads and missing roots."""
        messages = [
            # Thread 1 - complete
            {"message_ts": "1705320001.000001", "thread_ts": "", "text": "Thread 1 root"},
            {
                "message_ts": "1705320002.000001",
                "thread_ts": "1705320001.000001",
                "text": "Thread 1 reply 1",
            },
            {
                "message_ts": "1705320003.000001",
                "thread_ts": "1705320001.000001",
                "text": "Thread 1 reply 2",
            },
            # Thread 2 - missing root
            {
                "message_ts": "1705320005.000001",
                "thread_ts": "1705320004.000001",
                "text": "Thread 2 reply 1",
            },
            {
                "message_ts": "1705320006.000001",
                "thread_ts": "1705320004.000001",
                "text": "Thread 2 reply 2",
            },
            # Standalone message
            {"message_ts": "1705320007.000001", "thread_ts": "", "text": "Standalone"},
        ]

        channel_id = "C12345678"
        channel_name = "general"

        # Resolve relationships and add placeholders
        resolved = resolve_thread_relationships_with_placeholders(
            messages, channel_id, channel_name
        )

        # Should have 6 original + 1 placeholder = 7 messages
        assert len(resolved) == 7

        # Validate structure
        stats = validate_thread_structure(resolved)
        assert stats["total_messages"] == 7
        assert stats["thread_roots"] == 2  # 1 real + 1 placeholder
        assert stats["thread_replies"] == 4  # 2 for each thread
        assert stats["standalone_messages"] == 1
        assert stats["placeholders_added"] == 1

        # Sort for display
        sorted_msgs = sort_messages_for_display(resolved)

        # Verify thread grouping - replies should follow their roots
        for i, msg in enumerate(sorted_msgs):
            if msg.get("thread_ts") and msg.get("thread_ts") != msg.get("message_ts"):
                # This is a thread reply - find its root
                thread_ts = msg.get("thread_ts")
                root_found = False
                for j in range(i):
                    if sorted_msgs[j].get("message_ts") == thread_ts:
                        root_found = True
                        break
                assert root_found, (
                    f"Thread reply {msg['message_ts']} appears before its root {thread_ts}"
                )
