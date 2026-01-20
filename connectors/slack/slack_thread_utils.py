"""Utilities for handling Slack thread relationships and message processing."""

import logging
from datetime import UTC, datetime
from typing import Any

from src.utils.pacific_time import format_pacific_time

logger = logging.getLogger(__name__)


def group_messages_by_threads(messages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """
    Group messages by their thread relationships.

    Args:
        messages: List of message dictionaries

    Returns:
        Dict mapping thread_ts -> list of thread messages (including root)
    """
    threads: dict[str, list] = {}

    for message in messages:
        thread_ts = message.get("thread_ts", "")
        message_ts = message.get("message_ts", message.get("timestamp", ""))

        # Determine the thread timestamp
        thread_key = thread_ts or message_ts

        if thread_key:
            if thread_key not in threads:
                threads[thread_key] = []
            threads[thread_key].append(message)

    return threads


def identify_missing_thread_roots(messages: list[dict[str, Any]]) -> set[str]:
    """
    Identify thread_ts values that don't have corresponding root messages.

    Args:
        messages: List of message dictionaries

    Returns:
        Set of thread_ts values that are missing their root messages
    """
    # Get all message timestamps (potential thread roots)
    message_timestamps = set()
    thread_timestamps = set()

    for message in messages:
        message_ts = message.get("message_ts", message.get("timestamp", ""))
        thread_ts = message.get("thread_ts", "")

        if message_ts:
            message_timestamps.add(message_ts)

        if thread_ts and thread_ts != message_ts:
            thread_timestamps.add(thread_ts)

    # Find thread_ts values that don't have corresponding message_ts
    missing_roots = thread_timestamps - message_timestamps
    return missing_roots


def create_missing_thread_root_placeholder(
    thread_ts: str, channel_id: str, channel_name: str
) -> dict[str, Any]:
    """
    Create a placeholder message for a missing thread root.

    Args:
        thread_ts: The timestamp of the missing thread root
        channel_id: Channel ID
        channel_name: Channel name for display

    Returns:
        Dict representing a placeholder message
    """
    try:
        # Convert timestamp to readable date in Pacific Time
        root_time = datetime.fromtimestamp(float(thread_ts), tz=UTC)
        formatted_time = format_pacific_time(thread_ts)  # Use Pacific Time formatting
        timestamp_iso = root_time.isoformat()
        date_str = root_time.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        formatted_time = "Unknown time"
        timestamp_iso = thread_ts
        date_str = "Unknown date"

    return {
        "user_id": "",
        "username": "MISSING_MESSAGE",
        "text": f"[Missing thread root message from {formatted_time}]",
        "timestamp": timestamp_iso,
        "formatted_time": formatted_time,
        "message_ts": thread_ts,
        "client_msg_id": f"missing_root_{thread_ts}",
        "channel_id": channel_id,
        "channel_name": channel_name,
        "date": date_str,
        "thread_ts": "",  # This IS the thread root
        "parent_user_id": "",
        "parent_username": "",
        "is_missing_placeholder": True,  # Flag to identify placeholders
    }


def resolve_thread_relationships_with_placeholders(
    messages: list[dict[str, Any]], channel_id: str, channel_name: str
) -> list[dict[str, Any]]:
    """
    Resolve thread relationships and add placeholders for missing roots.

    Args:
        messages: List of message dictionaries
        channel_id: Channel ID
        channel_name: Channel name

    Returns:
        List of messages with placeholders added for missing thread roots
    """
    # Identify missing thread roots
    missing_roots = identify_missing_thread_roots(messages)

    # Create placeholders for missing roots
    placeholders = []
    for missing_root_ts in missing_roots:
        placeholder = create_missing_thread_root_placeholder(
            missing_root_ts, channel_id, channel_name
        )
        placeholders.append(placeholder)
        logger.info(f"Created placeholder for missing thread root: {missing_root_ts}")

    # Combine original messages with placeholders
    all_messages = messages + placeholders

    # Sort by timestamp to maintain chronological order
    all_messages.sort(key=lambda msg: float(msg.get("message_ts", msg.get("timestamp", "0"))))

    return all_messages


def validate_thread_structure(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Validate the thread structure of a set of messages and return statistics.

    Args:
        messages: List of message dictionaries

    Returns:
        Dict with validation statistics
    """
    stats = {
        "total_messages": len(messages),
        "standalone_messages": 0,
        "thread_roots": 0,
        "thread_replies": 0,
        "threads_count": 0,
        "missing_thread_roots": 0,
        "orphaned_replies": 0,
        "placeholders_added": 0,
    }

    threads = group_messages_by_threads(messages)
    stats["threads_count"] = len(threads)

    message_timestamps = set()
    for message in messages:
        message_ts = message.get("message_ts", message.get("timestamp", ""))
        thread_ts = message.get("thread_ts", "")
        is_placeholder = message.get("is_missing_placeholder", False)

        if is_placeholder:
            stats["placeholders_added"] += 1

        if message_ts:
            message_timestamps.add(message_ts)

        if not thread_ts or thread_ts == message_ts:
            # This is a standalone message or thread root
            # Check if this message starts a thread (has replies)
            has_replies = any(
                other_msg.get("thread_ts") == message_ts
                for other_msg in messages
                if other_msg != message
            )

            if has_replies or thread_ts == message_ts:
                stats["thread_roots"] += 1
            else:
                # Only count as standalone if it's not a placeholder
                if not is_placeholder:
                    stats["standalone_messages"] += 1
        else:
            # This is a thread reply
            stats["thread_replies"] += 1

            # Check if the thread root exists
            if thread_ts not in message_timestamps:
                stats["orphaned_replies"] += 1

    # Count missing thread roots
    missing_roots = identify_missing_thread_roots(messages)
    stats["missing_thread_roots"] = len(missing_roots)

    return stats


def sort_messages_for_display(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Sort messages for optimal display, grouping threads together.

    Args:
        messages: List of message dictionaries

    Returns:
        List of messages sorted for display
    """
    threads = group_messages_by_threads(messages)

    # Get thread roots sorted by timestamp
    thread_roots = []
    for thread_ts, thread_messages in threads.items():
        # Find the root message (the one with thread_ts == message_ts or no thread_ts)
        root_message = None
        for msg in thread_messages:
            msg_ts = msg.get("message_ts", msg.get("timestamp", ""))
            msg_thread_ts = msg.get("thread_ts", "")

            if not msg_thread_ts or msg_thread_ts == msg_ts:
                root_message = msg
                break

        if root_message:
            thread_roots.append((thread_ts, root_message, thread_messages))

    # Sort thread roots by timestamp
    thread_roots.sort(key=lambda x: float(x[1].get("message_ts", x[1].get("timestamp", "0"))))

    # Build final sorted list
    sorted_messages = []
    for _thread_ts, root_message, thread_messages in thread_roots:
        # Add root message first
        sorted_messages.append(root_message)

        # Add thread replies sorted by timestamp
        replies = [msg for msg in thread_messages if msg != root_message]
        replies.sort(key=lambda msg: float(msg.get("message_ts", msg.get("timestamp", "0"))))
        sorted_messages.extend(replies)

    return sorted_messages
