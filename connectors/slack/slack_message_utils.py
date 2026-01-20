"""Utilities for processing and cleaning Slack messages."""

import html
import logging
from typing import Any

logger = logging.getLogger(__name__)


def clean_slack_text(text: str) -> str:
    """
    Clean up Slack message text.

    Args:
        text: Raw Slack message text

    Returns:
        str: Cleaned text
    """
    if not text:
        return ""

    # Remove extra whitespace
    text = " ".join(text.split())

    # Decode HTML entities
    text = html.unescape(text)

    return text


def deduplicate_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove duplicate messages based on message_ts and client_msg_id.

    Args:
        messages: List of message dicts

    Returns:
        List of deduplicated messages
    """
    seen_messages = set()
    deduplicated = []

    for message in messages:
        # Create a unique key for the message
        message_ts = message.get("message_ts", "")
        client_msg_id = message.get("client_msg_id", "")

        # Use both timestamp and client_msg_id for deduplication
        key = (message_ts, client_msg_id) if client_msg_id else (message_ts,)

        if key not in seen_messages and message_ts:
            seen_messages.add(key)
            deduplicated.append(message)
        elif not message_ts:
            # Keep messages without timestamps (like placeholders)
            deduplicated.append(message)

    return deduplicated
