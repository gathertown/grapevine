"""Utility functions for Slack message processing."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from connectors.base import get_slack_message_entity_id
from connectors.slack.slack_artifacts import (
    SlackMessageArtifact,
    SlackMessageContent,
    SlackMessageMetadata,
)


def create_slack_message_artifact(
    msg: dict[str, Any], job_id: str, channel_id: str
) -> SlackMessageArtifact:
    """Create a SlackMessageArtifact from a message dict with proper source_updated_at.

    Args:
        msg: The Slack message dictionary
        job_id: The ingest job ID
        channel_id: The channel ID for the message

    Returns:
        SlackMessageArtifact with source_updated_at set to the later of ts and edited.ts
    """
    # Generate entity_id using standardized format: {channel_id}_{ts}
    entity_id = get_slack_message_entity_id(channel_id=channel_id, ts=msg.get("ts", ""))

    # Calculate source_updated_at as the later of ts and edited.ts
    ts_float = float(msg.get("ts", "0"))
    edited_info = msg.get("edited", {})
    edited_ts = float(edited_info.get("ts", "0")) if edited_info else 0
    latest_ts = max(ts_float, edited_ts)
    source_updated_at = datetime.fromtimestamp(latest_ts, tz=UTC)

    # Create artifact
    return SlackMessageArtifact(
        entity_id=entity_id,
        ingest_job_id=UUID(job_id),
        content=SlackMessageContent(**msg),
        metadata=SlackMessageMetadata(channel_id=channel_id),
        source_updated_at=source_updated_at,
    )
