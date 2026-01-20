"""Extract and score questions from Slack messages for sample questions feature."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Constants for question filtering
MAX_QUESTIONS_PER_CHANNEL_DAY = 5

# Pre-compiled regex patterns for better performance
QUESTION_PATTERN = re.compile(r"\?+\s*$")  # Ends with one or more question marks
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)
MENTION_PATTERN = re.compile(r"<@[^>]+>")
CHANNEL_PATTERN = re.compile(r"<#[^>]+>")


def extract_questions_from_messages(
    messages: list[dict[str, Any]], channel_id: str, channel_name: str, date: str
) -> list[dict[str, Any]]:
    """Extract and score questions from processed Slack messages.

    Args:
        messages: List of processed message dictionaries from SlackTransformer
        channel_id: Slack channel ID
        channel_name: Human-readable channel name
        date: Date string in YYYY-MM-DD format

    Returns:
        List of question dictionaries sorted by score (highest first)
    """
    logger.info(
        f"Starting question extraction from {len(messages)} messages in channel {channel_name} ({channel_id}) for date {date}"
    )

    if not messages:
        logger.info("No messages to process")
        return []

    logger.info("Processing messages for question extraction: %d messages", len(messages))

    # Filter out old message
    # TODO: Revisit this cut-off - the sample data I had was unfortunately > 1 month old
    cutoff_time = datetime.now(UTC) - timedelta(days=45)
    original_count = len(messages)

    filtered_messages = []
    for message in messages:
        message_time = _parse_timestamp(message.get("timestamp"))
        if message_time and message_time >= cutoff_time:
            filtered_messages.append(message)

    messages = filtered_messages
    filtered_count = original_count - len(messages)

    if filtered_count > 0:
        logger.info(
            f"Filtered out {filtered_count} old messages, processing {len(messages)} remaining messages"
        )

    if not messages:
        logger.info("No messages remaining after age filtering")
        return []

    # Group messages by thread for engagement analysis
    threads = _group_messages_by_thread(messages)

    # Calculate channel activity metrics
    channel_stats = _calculate_channel_stats(messages)

    questions = []

    for message in messages:
        if not _is_question_candidate(message):
            continue

        # Find thread replies for this message
        thread_replies = threads.get(message.get("message_ts", ""), [])

        # Calculate question score
        score = _calculate_question_score(message, channel_stats, thread_replies)

        question = {
            "question_text": message["text"],
            "source": "slack",
            "source_id": message.get("message_ts"),
            "score": score,
            # Store Slack-specific data that will be put in metadata
            "channel_name": channel_name,
            "channel_id": channel_id,
            "user_id": message.get("user_id"),
            "username": message.get("username"),
            "message_timestamp": message.get("timestamp"),
            "thread_reply_count": len(thread_replies),
            "reaction_count": 0,  # Not available in processed messages
            # Keep source_message_id for backward compatibility
            "source_message_id": message.get("message_ts"),
        }
        questions.append(question)

    # Sort by score (highest first) and limit
    questions.sort(key=lambda q: q["score"], reverse=True)
    top_questions = questions[:MAX_QUESTIONS_PER_CHANNEL_DAY]

    logger.info(
        f"Question extraction complete for {channel_name} on {date}: "
        f"found {len(questions)} candidates, returning top {len(top_questions)} "
        f"(scores: {[round(q['score'], 1) for q in top_questions] if top_questions else 'none'})"
    )

    return top_questions


def _is_question_candidate(message: dict[str, Any]) -> bool:
    """Check if message is a valid question candidate."""
    text = message.get("text", "").strip()

    if not text:
        return False

    # Must end with question mark(s)
    if not QUESTION_PATTERN.search(text):
        return False

    # Filter out very short questions (less than 10 chars excluding question marks)
    text_without_qmarks = QUESTION_PATTERN.sub("", text).strip()
    if len(text_without_qmarks) < 10:
        return False

    # Skip system/bot-like patterns
    user_id = message.get("user_id", "")
    if user_id in ["USLACKBOT", ""] or user_id.startswith("B"):  # Bot users often start with B
        return False

    # Skip very simple yes/no questions
    simple_patterns = [
        r"^(yes|no|ok|okay)\?+$",
        r"^(anyone|anybody)\?+$",
        r"^(what|when|where|why|how)\?+$",  # Single word questions
    ]

    return all(not re.match(pattern, text.lower().strip()) for pattern in simple_patterns)


def _group_messages_by_thread(messages: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group messages by thread timestamp for engagement analysis."""
    threads: dict[str, list[dict[str, Any]]] = {}

    for message in messages:
        thread_ts = message.get("thread_ts")
        message_ts = message.get("message_ts")

        if thread_ts and thread_ts != message_ts:
            # This is a thread reply
            if thread_ts not in threads:
                threads[thread_ts] = []
            threads[thread_ts].append(message)

    return threads


def _calculate_channel_stats(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate channel activity statistics for scoring."""
    if not messages:
        return {"daily_message_count": 0}

    # Count unique users for diversity metric
    unique_users = set()
    for message in messages:
        user_id = message.get("user_id")
        if user_id:
            unique_users.add(user_id)

    return {
        "daily_message_count": len(messages),
        "unique_users": len(unique_users),
    }


def _calculate_question_score(
    message: dict[str, Any], channel_stats: dict[str, Any], thread_replies: list[dict[str, Any]]
) -> float:
    """Calculate question score based on engagement and content quality."""
    text = message.get("text", "")

    # Base score from question length (10-200 chars = 1-20 points)
    text_length = len(text.strip())
    base_score = min(text_length * 0.1, 20.0)

    # Channel activity bonus (active channels = more important questions)
    daily_messages = channel_stats.get("daily_message_count", 1)
    channel_bonus = min(daily_messages / 20.0, 3.0)  # Max 3 points

    # Thread engagement scoring
    thread_bonus = _calculate_thread_bonus(message, thread_replies)

    # Recency factor (slight boost for recent questions)
    recency_factor = _calculate_recency_factor(message.get("timestamp"))

    total_score = (base_score + channel_bonus + thread_bonus) * recency_factor

    logger.debug(
        f"Question score breakdown: base={base_score:.1f}, channel={channel_bonus:.1f}, "
        f"thread={thread_bonus:.1f}, recency={recency_factor:.2f} -> total={total_score:.1f}"
    )

    return total_score


def _calculate_thread_bonus(message: dict[str, Any], thread_replies: list[dict[str, Any]]) -> float:
    """Calculate thread engagement bonus."""
    if not thread_replies:
        # Unanswered questions get a slight boost (users might need help with these)
        return 0.5

    # Base thread bonus (more replies = more engaging question)
    reply_bonus = min(len(thread_replies) * 0.5, 4.0)  # Max 4 points

    # Quick response bonus (answered within 1 hour)
    message_time = _parse_timestamp(message.get("timestamp"))
    if message_time:
        for reply in thread_replies:
            reply_time = _parse_timestamp(reply.get("timestamp"))
            if reply_time and (reply_time - message_time).total_seconds() < 3600:  # 1 hour
                reply_bonus += 1.0
                break

    return min(reply_bonus, 5.0)  # Cap total thread bonus at 5


def _calculate_recency_factor(timestamp_str: str | None) -> float:
    """Calculate recency factor (1.0 = today, decays over 30 days)."""
    if not timestamp_str:
        return 0.5

    try:
        message_time = _parse_timestamp(timestamp_str)
        if not message_time:
            return 0.5

        now = datetime.now(UTC)
        days_old = (now - message_time).days

        # Linear decay over 30 days, minimum 0.3
        recency = max(1.0 - (days_old / 30.0), 0.3)
        return recency

    except Exception as e:
        logger.warning(f"Failed to parse timestamp {timestamp_str}: {e}")
        return 0.5


def _parse_timestamp(timestamp_str: str | None) -> datetime | None:
    """Parse ISO timestamp string to datetime object."""
    if not timestamp_str:
        return None

    try:
        # Handle ISO format timestamps from SlackTransformer
        return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    except Exception as e:
        logger.warning(f"Failed to parse timestamp {timestamp_str}: {e}")
        return None
