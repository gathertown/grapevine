"""
Slack document classes for structured channel and message representation.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource


class SlackChannelChunkMetadata(TypedDict):
    """Metadata for Slack channel chunks."""

    user_id: str | None
    username: str | None
    timestamp: str | None
    formatted_time: str | None
    message_id: str | None
    channel_id: str | None
    channel_name: str | None
    date: str | None
    thread_ts: str | None
    parent_user_id: str | None
    parent_username: str | None
    team_id: str | None
    team_domain: str | None


class SlackChannelDocumentMetadata(TypedDict):
    """Metadata for Slack channel documents."""

    channel_id: str | None
    channel_name: str | None
    date: str | None
    source: str
    type: str
    message_count: int
    team_id: str | None
    team_domain: str | None
    source_created_at: str | None


@dataclass
class SlackChannelChunk(BaseChunk[SlackChannelChunkMetadata]):
    """Represents a single Slack message chunk."""

    def get_unique_key(self) -> str | None:
        """Get a unique key for this chunk within its document.

        For Slack messages, we use message_ts which is unique per message.
        For header chunks, we use a fixed "header" key.
        """
        # Check if this is a header chunk
        if self.raw_data.get("chunk_type") == "header":
            return "header"

        # For message chunks, use message_ts
        message_ts = self.raw_data.get("message_ts")
        if message_ts:
            return f"msg:{message_ts}"

        return None

    def get_content(self) -> str:
        """Get the formatted message content."""
        # Header chunks store content directly
        if self.raw_data.get("chunk_type") == "header":
            return self.raw_data.get("content", "")

        user_id = self.raw_data.get("user_id", "")
        username = self.raw_data.get("username", "")
        formatted_time = self.raw_data.get("formatted_time", "")
        text = self.raw_data.get("text", "")

        # Compress to single line for display only (text is already cleaned during processing)
        single_line_text = text.replace("\n", " ").replace("\r", " ")
        single_line_text = " ".join(single_line_text.split())
        return f"{formatted_time} <@{user_id}|@{username}> : {single_line_text}"

    def get_metadata(self) -> SlackChannelChunkMetadata:
        """Get chunk-specific metadata."""
        metadata: SlackChannelChunkMetadata = {
            "user_id": self.raw_data.get("user_id"),
            "username": self.raw_data.get("username"),
            "timestamp": self.raw_data.get("message_ts"),
            "formatted_time": self.raw_data.get("formatted_time"),
            "message_id": self.raw_data.get("client_msg_id"),
            "channel_id": self.raw_data.get("channel_id"),
            "channel_name": self.raw_data.get("channel_name"),
            "date": self.raw_data.get("date"),
            "thread_ts": self.raw_data.get("thread_ts"),
            "parent_user_id": self.raw_data.get("parent_user_id"),
            "parent_username": self.raw_data.get("parent_username"),
            "team_id": self.raw_data.get("team_id"),
            "team_domain": self.raw_data.get("team_domain"),
        }

        return metadata


@dataclass
class SlackChannelDocument(BaseDocument[SlackChannelChunk, SlackChannelDocumentMetadata]):
    """Represents a collection of Slack messages from a channel for a specific date."""

    raw_data: dict[str, Any]

    def _get_channel_id(self) -> str | None:
        return self.raw_data.get("channel_id")

    def _get_channel_name(self) -> str | None:
        return self.raw_data.get("channel_name")

    def get_header_content(self) -> str:
        """Get the formatted header section of the document."""
        channel_id = self._get_channel_id()
        channel_name = self._get_channel_name()
        date = self.raw_data.get("date", "")
        messages = self.raw_data.get("messages", [])

        # Build participants list from messages with most recent username per user_id
        user_map = {}
        for msg in reversed(messages):  # Process in reverse to get most recent names first
            user_id = msg.get("user_id", "")
            username = msg.get("username", "")
            if user_id and username and user_id not in user_map:
                user_map[user_id] = username

        participants_list = [f"<@{uid}|@{uname}>" for uid, uname in sorted(user_map.items())]

        lines = [
            f"Channel: <#{channel_id}|#{channel_name}>",
            f"Date: {date}",
            f"Participants: {', '.join(participants_list)}",
        ]

        return "\n".join(lines)

    def get_content(self) -> str:
        """Get the formatted document content with all thread replies inlined."""
        messages = self.raw_data.get("messages", [])
        channel_id = self._get_channel_id()
        channel_name = self._get_channel_name()

        lines = [self.get_header_content()]
        lines.extend(["", "Messages:", ""])

        # Group messages by threads
        threads: dict[str, list] = {}
        root_messages = []

        for msg in messages:
            thread_ts = msg.get("thread_ts", "")
            message_ts = msg.get("message_ts", "")

            if thread_ts and thread_ts != message_ts:
                # This is a thread reply
                if thread_ts not in threads:
                    threads[thread_ts] = []
                threads[thread_ts].append(msg)
            else:
                # This is a standalone message or thread root
                root_messages.append(msg)

        # Sort root messages by timestamp
        root_messages.sort(key=lambda msg: float(msg.get("message_ts", msg.get("timestamp", "0"))))

        # Display messages with their threads
        for msg_data in root_messages:
            chunk = SlackChannelChunk(
                document=self,
                slack_channel_id=channel_id,
                slack_channel_name=channel_name,
                raw_data=msg_data,
            )

            # Check if this is a missing thread root placeholder
            if msg_data.get("is_missing_placeholder"):
                lines.append("[Missing thread root - original message not available]")
            else:
                lines.append(chunk.get_content())

            # Add thread replies for this root
            msg_ts = msg_data.get("message_ts", "")
            if msg_ts in threads:
                # Sort thread replies by timestamp
                thread_replies = threads[msg_ts]
                thread_replies.sort(
                    key=lambda msg: float(msg.get("message_ts", msg.get("timestamp", "0")))
                )

                for thread_msg in thread_replies:
                    thread_chunk = SlackChannelChunk(
                        document=self,
                        slack_channel_id=channel_id,
                        slack_channel_name=channel_name,
                        raw_data=thread_msg,
                    )
                    lines.append(f"    |-- {thread_chunk.get_content()}")

        # Note: We no longer display orphaned threads as they should all be properly
        # included in their thread root's Pacific Time day document

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[SlackChannelChunk]:
        """Convert to embedding chunk format."""
        chunks = []
        messages = self.raw_data.get("messages", [])
        channel_id = self._get_channel_id()
        channel_name = self._get_channel_name()

        # Add header chunk
        header_chunk = SlackChannelChunk(
            document=self,
            slack_channel_id=channel_id,
            slack_channel_name=channel_name,
            raw_data={
                "content": self.get_header_content(),
                "channel_id": channel_id,
                "channel_name": channel_name,
                "date": self.raw_data.get("date"),
                "source": self.get_source(),
                "type": "slack_channel_header",
                "chunk_type": "header",
                "message_count": len(messages),
                "team_id": self.raw_data.get("team_id"),
                "team_domain": self.raw_data.get("team_domain"),
            },
        )
        chunks.append(header_chunk)

        # Then add all message chunks
        for msg_data in messages:
            chunk = SlackChannelChunk(
                document=self,
                slack_channel_id=channel_id,
                slack_channel_name=channel_name,
                raw_data=msg_data,
            )
            chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.SLACK

    def get_reference_id(self) -> str:
        # TODO: AIVP-384 figure out how to handle references to Slack docs
        return "r_slack_docs_unsupported_" + self.id

    def get_metadata(self) -> SlackChannelDocumentMetadata:
        """Get document metadata."""
        messages = self.raw_data.get("messages", [])

        # Calculate source_created_at as the earliest message timestamp
        source_created_at = None
        if messages:
            earliest_ts = None
            for msg in messages:
                timestamp_str = msg.get("timestamp")  # ISO format
                if timestamp_str:
                    try:
                        from datetime import datetime

                        msg_dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        if earliest_ts is None or msg_dt < earliest_ts:
                            earliest_ts = msg_dt
                    except (ValueError, TypeError):
                        continue

            if earliest_ts:
                source_created_at = earliest_ts.isoformat()

        metadata: SlackChannelDocumentMetadata = {
            "channel_id": self._get_channel_id(),
            "channel_name": self._get_channel_name(),
            "date": self.raw_data.get("date"),
            "source": self.get_source(),
            "type": "slack_channel_document",
            "message_count": len(messages),
            "team_id": self.raw_data.get("team_id"),
            "team_domain": self.raw_data.get("team_domain"),
            "source_created_at": source_created_at,
        }

        return metadata
