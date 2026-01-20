"""
Gather meetings document classes for structured meeting representation.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource


class GatherMeetingChunkMetadata(TypedDict):
    """Metadata for Gather meeting chunks."""

    meeting_id: str | None
    meeting_type: str | None  # "Scheduled" or "Unplanned"
    calendar_event_title: str | None
    chunk_type: str | None  # "header", "memo", "chat_message"
    # For memo chunks
    memo_id: str | None
    memo_language: str | None
    # For chat message chunks
    message_id: str | None
    message_author_id: str | None
    message_author_name: str | None
    message_timestamp: str | None
    # Timestamps
    started_at: str | None
    ended_at: str | None


class GatherMeetingDocumentMetadata(TypedDict):
    """Metadata for Gather meeting documents."""

    meeting_id: str | None
    meeting_type: str | None
    calendar_event_title: str | None
    participant_count: int
    memo_count: int
    message_count: int
    started_at: str | None
    ended_at: str | None
    source: str
    type: str
    source_created_at: str | None


@dataclass
class GatherMeetingChunk(BaseChunk[GatherMeetingChunkMetadata]):
    """Represents a single Gather meeting chunk (header, memo, or chat message)."""

    def get_content(self) -> str:
        """Get the formatted chunk content."""
        chunk_type = self.raw_data.get("chunk_type", "")

        if chunk_type == "header":
            return self._format_header()
        elif chunk_type == "memo":
            return self._format_memo()
        elif chunk_type == "chat_message":
            return self._format_chat_message()
        else:
            return ""

    def _format_header(self) -> str:
        """Format the header chunk content."""
        lines = []
        meeting_type = self.raw_data.get("meeting_type", "")
        calendar_event_title = self.raw_data.get("calendar_event_title", "")
        started_at = self.raw_data.get("started_at", "")
        ended_at = self.raw_data.get("ended_at", "")
        participants = self.raw_data.get("participants", [])

        if calendar_event_title:
            lines.append(f"Meeting: {calendar_event_title}")
        else:
            lines.append(f"Meeting: {meeting_type}")

        lines.append(f"Type: {meeting_type}")

        if started_at:
            lines.append(f"Started: {started_at}")
        if ended_at:
            lines.append(f"Ended: {ended_at}")

        if participants:
            participant_names = []
            for p in participants:
                display_name = p.get("display_name", "")
                email = p.get("email", "")
                if display_name:
                    participant_names.append(f"{display_name} ({email})")
                elif email:
                    participant_names.append(email)

            if participant_names:
                lines.append(f"Participants: {', '.join(participant_names)}")

        return "\n".join(lines)

    def _format_memo(self) -> str:
        """Format the memo chunk content."""
        lines = []
        summary = self.raw_data.get("memo_summary", "")
        notes = self.raw_data.get("memo_notes", [])
        action_items = self.raw_data.get("memo_action_items", [])
        started_at = self.raw_data.get("memo_started_at", "")
        ended_at = self.raw_data.get("memo_ended_at", "")
        transcript = self.raw_data.get("transcript", [])

        lines.append("Meeting Memo")
        if started_at and ended_at:
            lines.append(f"Recorded: {started_at} to {ended_at}")

        if summary:
            lines.append("")
            lines.append("Summary:")
            lines.append(summary)

        if notes:
            lines.append("")
            lines.append("Notes:")
            for note in notes:
                heading = note.get("heading", "")
                bullets = note.get("bullets", [])
                if heading:
                    lines.append(f"\n{heading}:")
                for bullet in bullets:
                    lines.append(f"  - {bullet}")

        if action_items:
            lines.append("")
            lines.append("Action Items:")
            for item in action_items:
                if isinstance(item, dict):
                    description = item.get("description", "")
                    due_date = item.get("due_date", "")
                    assignee = item.get("assignee", "")
                    item_text = f"  - {description}"
                    if assignee:
                        item_text += f" (assigned to: {assignee})"
                    if due_date:
                        item_text += f" [due: {due_date}]"
                    lines.append(item_text)
                else:
                    # Fallback for legacy string format
                    lines.append(f"  - {item}")

        if transcript:
            lines.append("")
            lines.append("Transcript:")
            for transcript_entry in transcript:
                speaker_id = transcript_entry.get("speaker_id", "")
                speaker_name = transcript_entry.get("speaker_name", "")
                transcript_text = transcript_entry.get("content", "")
                lines.append(f"  - {speaker_id}|{speaker_name}: {transcript_text}")

        return "\n".join(lines)

    def _format_chat_message(self) -> str:
        """Format the chat message chunk content."""
        author_name = self.raw_data.get("message_author_name", "")
        author_id = self.raw_data.get("message_author_id", "")
        text = self.raw_data.get("message_text", "")
        timestamp = self.raw_data.get("message_timestamp", "")

        if author_name and author_id:
            return f"{timestamp} <@{author_id}|@{author_name}>: {text}"
        elif author_name:
            return f"{timestamp} {author_name}: {text}"
        else:
            return f"{timestamp}: {text}"

    def get_metadata(self) -> GatherMeetingChunkMetadata:
        """Get chunk-specific metadata."""
        metadata: GatherMeetingChunkMetadata = {
            "meeting_id": self.raw_data.get("meeting_id"),
            "meeting_type": self.raw_data.get("meeting_type"),
            "calendar_event_title": self.raw_data.get("calendar_event_title"),
            "chunk_type": self.raw_data.get("chunk_type"),
            "memo_id": self.raw_data.get("memo_id"),
            "memo_language": self.raw_data.get("memo_language"),
            "message_id": self.raw_data.get("message_id"),
            "message_author_id": self.raw_data.get("message_author_id"),
            "message_author_name": self.raw_data.get("message_author_name"),
            "message_timestamp": self.raw_data.get("message_timestamp"),
            "started_at": self.raw_data.get("started_at"),
            "ended_at": self.raw_data.get("ended_at"),
        }

        return metadata


@dataclass
class GatherMeetingDocument(BaseDocument[GatherMeetingChunk, GatherMeetingDocumentMetadata]):
    """Represents a complete Gather meeting with memos and chat messages."""

    raw_data: dict[str, Any]

    def get_header_content(self) -> str:
        """Get the formatted header section of the document."""
        meeting_id = self.raw_data.get("id", "")
        meeting_type = self.raw_data.get("type", "")
        started_at = self.raw_data.get("startedAt", "")
        ended_at = self.raw_data.get("endedAt", "")
        participants = self.raw_data.get("participants", [])
        calendar_event = self.raw_data.get("calendarEvent", {})

        lines = []
        calendar_title = calendar_event.get("title", "") if calendar_event else ""

        if calendar_title:
            lines.append(f"Meeting: {calendar_title}")
        else:
            lines.append(f"Meeting ID: {meeting_id}")

        lines.append(f"Type: {meeting_type}")

        if started_at:
            lines.append(f"Started: {started_at}")
        if ended_at:
            lines.append(f"Ended: {ended_at}")

        if participants:
            participant_names = []
            for p in participants:
                display_name = p.get("display_name", "")
                email = p.get("email", "")
                joined_at = p.get("joined_at", "")
                left_at = p.get("left_at", "")

                if display_name:
                    participant_info = f"{display_name} ({email})"
                    if joined_at:
                        participant_info += f" joined at {joined_at}"
                    if left_at:
                        participant_info += f", left at {left_at}"
                    participant_names.append(participant_info)
                elif email:
                    participant_names.append(email)

            if participant_names:
                lines.append("")
                lines.append("Participants:")
                for name in participant_names:
                    lines.append(f"  - {name}")

        if calendar_event:
            description = calendar_event.get("description", "")
            if description:
                lines.append("")
                lines.append("Description:")
                lines.append(description)

        return "\n".join(lines)

    def get_content(self) -> str:
        """Get the formatted document content."""
        meeting_memos = self.raw_data.get("meetingMemos", [])
        chat_channel = self.raw_data.get("chatChannel", {})
        messages = chat_channel.get("messages", []) if chat_channel else []

        lines = [self.get_header_content()]

        # Add meeting memos
        if meeting_memos:
            lines.extend(["", "", "Meeting Memos:", ""])
            for memo in meeting_memos:
                chunk = self._create_memo_chunk(memo)
                lines.append(chunk.get_content())
                lines.append("")

        # Add chat messages
        if messages:
            lines.extend(["", "Chat Messages:", ""])
            for message in messages:
                chunk = self._create_message_chunk(message)
                lines.append(chunk.get_content())

        return "\n".join(lines)

    def _create_memo_chunk(self, memo_data: dict) -> GatherMeetingChunk:
        """Create a memo chunk from memo data."""
        meeting_id = self.raw_data.get("id", "")
        meeting_type = self.raw_data.get("type", "")
        calendar_event = self.raw_data.get("calendarEvent", {})
        calendar_title = calendar_event.get("title", "") if calendar_event else ""

        chunk_data = {
            "meeting_id": meeting_id,
            "meeting_type": meeting_type,
            "calendar_event_title": calendar_title,
            "chunk_type": "memo",
            "memo_id": memo_data.get("id"),
            "memo_language": memo_data.get("language"),
            "memo_summary": memo_data.get("summary"),
            "memo_notes": memo_data.get("notes"),
            "memo_action_items": memo_data.get("actionItems"),
            "memo_started_at": memo_data.get("startedAt"),
            "memo_ended_at": memo_data.get("endedAt"),
            "transcript": memo_data.get("transcript", []),
        }

        return GatherMeetingChunk(document=self, raw_data=chunk_data)

    def _create_message_chunk(self, message_data: dict) -> GatherMeetingChunk:
        """Create a chat message chunk from message data."""
        meeting_id = self.raw_data.get("id", "")
        meeting_type = self.raw_data.get("type", "")
        calendar_event = self.raw_data.get("calendarEvent", {})
        calendar_title = calendar_event.get("title", "") if calendar_event else ""

        chunk_data = {
            "meeting_id": meeting_id,
            "meeting_type": meeting_type,
            "calendar_event_title": calendar_title,
            "chunk_type": "chat_message",
            "message_id": message_data.get("id"),
            "message_text": message_data.get("text"),
            "message_author_id": message_data.get("author_user_id"),
            "message_author_name": message_data.get("author_user_name"),
            "message_timestamp": message_data.get("createdAt"),
        }

        return GatherMeetingChunk(document=self, raw_data=chunk_data)

    def to_embedding_chunks(self) -> list[GatherMeetingChunk]:
        """Convert to embedding chunk format."""
        chunks = []
        meeting_id = self.raw_data.get("id", "")
        meeting_type = self.raw_data.get("type", "")
        started_at = self.raw_data.get("startedAt", "")
        ended_at = self.raw_data.get("endedAt", "")
        participants = self.raw_data.get("participants", [])
        calendar_event = self.raw_data.get("calendarEvent", {})
        calendar_title = calendar_event.get("title", "") if calendar_event else ""

        # Add header chunk
        header_chunk = GatherMeetingChunk(
            document=self,
            raw_data={
                "chunk_type": "header",
                "meeting_id": meeting_id,
                "meeting_type": meeting_type,
                "calendar_event_title": calendar_title,
                "started_at": started_at,
                "ended_at": ended_at,
                "participants": participants,
            },
        )
        chunks.append(header_chunk)

        # Add memo chunks
        meeting_memos = self.raw_data.get("meetingMemos", [])
        for memo in meeting_memos:
            chunk = self._create_memo_chunk(memo)
            chunks.append(chunk)

        # Add chat message chunks
        chat_channel = self.raw_data.get("chatChannel", {})
        messages = chat_channel.get("messages", []) if chat_channel else []
        for message in messages:
            chunk = self._create_message_chunk(message)
            chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.GATHER

    def get_metadata(self) -> GatherMeetingDocumentMetadata:
        """Get document metadata."""
        meeting_memos = self.raw_data.get("meetingMemos", [])
        chat_channel = self.raw_data.get("chatChannel", {})
        messages = chat_channel.get("messages", []) if chat_channel else []
        participants = self.raw_data.get("participants", [])
        calendar_event = self.raw_data.get("calendarEvent", {})

        metadata: GatherMeetingDocumentMetadata = {
            "meeting_id": self.raw_data.get("id"),
            "meeting_type": self.raw_data.get("type"),
            "calendar_event_title": calendar_event.get("title") if calendar_event else None,
            "participant_count": len(participants),
            "memo_count": len(meeting_memos),
            "message_count": len(messages),
            "started_at": self.raw_data.get("startedAt"),
            "ended_at": self.raw_data.get("endedAt"),
            "source": self.get_source(),
            "type": "gather_meeting_document",
            "source_created_at": self.raw_data.get("source_created_at"),
        }

        return metadata
