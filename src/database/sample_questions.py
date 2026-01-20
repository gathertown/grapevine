"""Database operations for sample questions feature."""

import json
from typing import Any

from src.clients.tenant_db import tenant_db_manager
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def store_sample_questions(tenant_id: str, questions: list[dict[str, Any]]) -> int:
    """Store extracted questions in database using source-agnostic schema.

    Args:
        tenant_id: The tenant ID
        questions: List of question dictionaries with fields matching the schema

    Returns:
        Number of questions actually stored
    """
    if not questions:
        logger.info(f"No questions to store for tenant {tenant_id}")
        return 0

    logger.info(f"Storing {len(questions)} sample questions for tenant {tenant_id}")

    async with tenant_db_manager.acquire_connection(tenant_id) as conn:
        stored_count = 0

        # Insert or update questions
        for question in questions:
            try:
                # Prepare metadata from source-specific fields
                metadata = {}

                # For Slack questions, store Slack-specific data in metadata
                if question.get("source", "slack") == "slack":
                    if question.get("channel_name"):
                        metadata["channel_name"] = question["channel_name"]
                    if question.get("channel_id"):
                        metadata["channel_id"] = question["channel_id"]
                    if question.get("user_id"):
                        metadata["user_id"] = question["user_id"]
                    if question.get("username"):
                        metadata["username"] = question["username"]
                    if question.get("message_timestamp"):
                        metadata["message_timestamp"] = question["message_timestamp"]
                    if question.get("thread_reply_count") is not None:
                        metadata["thread_reply_count"] = question["thread_reply_count"]
                    if question.get("reaction_count") is not None:
                        metadata["reaction_count"] = question["reaction_count"]

                await conn.execute(
                    """
                    INSERT INTO sample_questions (
                        question_text, source, source_id, score, metadata
                    ) VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (source, source_id)
                    DO UPDATE SET
                        score = EXCLUDED.score,
                        metadata = EXCLUDED.metadata,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    question["question_text"],
                    question.get("source", "slack"),
                    question.get("source_message_id") or question.get("source_id"),
                    question.get("score", 0.0),
                    json.dumps(metadata),
                )
                stored_count += 1
            except Exception as e:
                logger.error(f"Failed to store question: {e}", exc_info=True)
                continue

        logger.info(f"Stored {stored_count} new questions for tenant {tenant_id}")

        return stored_count
