"""Utility functions for filtering Slack messages."""

from typing import Any


def is_bot_message(event: dict[str, Any]) -> bool:
    """Check if a Slack message event is from a bot.

    Args:
        event: Slack message event dictionary

    Returns:
        True if the message is from a bot, False otherwise
    """
    subtype = event.get("subtype")
    return subtype == "bot_message" or "bot_id" in event
