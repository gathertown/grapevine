"""Gather meetings artifact models."""

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact

# ============================================================================
# Meeting Artifact (metadata only)
# ============================================================================


class GatherMeetingParticipant(BaseModel):
    """Structure for a single participant in a Gather meeting."""

    space_user_id: str
    display_name: str
    email: str
    response_status: str | None = None
    joined_at: str | None = None
    left_at: str | None = None


class GatherMeetingArtifactMetadata(BaseModel):
    """Metadata for Gather meeting artifacts."""

    meeting_id: str
    meeting_type: str  # "Scheduled" or "Unplanned"
    space_id: str
    calendar_event_title: str | None = None
    participant_count: int = 0
    started_at: str | None = None
    ended_at: str | None = None
    source_created_at: str | None = None


class GatherMeetingArtifactContent(BaseModel):
    """Content for Gather meeting artifacts (metadata only, no memos/messages)."""

    meeting_type: str
    participants: list[GatherMeetingParticipant]
    calendar_event_title: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


class GatherMeetingArtifact(BaseIngestArtifact):
    """Typed Gather meeting artifact with meeting metadata only."""

    entity: ArtifactEntity = ArtifactEntity.GATHER_MEETING
    content: GatherMeetingArtifactContent
    metadata: GatherMeetingArtifactMetadata


# ============================================================================
# Meeting Memo Artifact
# ============================================================================


class GatherMeetingNote(BaseModel):
    """Structure for a single note section in a Gather meeting memo."""

    heading: str
    bullets: list[str]


class GatherMeetingActionItem(BaseModel):
    """Structure for a single action item in a Gather meeting memo."""

    description: str
    due_date: str | None = None
    assignee: str | None = None


class GatherMeetingMemoArtifactMetadata(BaseModel):
    """Metadata for Gather meeting memo artifacts."""

    memo_id: str
    meeting_id: str
    space_id: str
    created_at: str | None = None


class GatherMeetingMemoArtifactContent(BaseModel):
    """Content for Gather meeting memo artifacts."""

    summary: str | None = None
    notes: list[GatherMeetingNote] | None = None
    action_items: list[GatherMeetingActionItem] | None = None
    created_at: str | None = None


class GatherMeetingMemoArtifact(BaseIngestArtifact):
    """Typed Gather meeting memo artifact for meeting memos."""

    entity: ArtifactEntity = ArtifactEntity.GATHER_MEETING_MEMO
    content: GatherMeetingMemoArtifactContent
    metadata: GatherMeetingMemoArtifactMetadata


# ============================================================================
# Chat Message Artifact
# ============================================================================


class GatherChatMessageArtifactMetadata(BaseModel):
    """Metadata for Gather chat message artifacts."""

    meeting_id: str
    message_id: str
    space_id: str
    author_user_id: str | None = None
    author_user_name: str | None = None
    created_at: str | None = None


class GatherChatMessageArtifactContent(BaseModel):
    """Content for Gather chat message artifacts."""

    text: str
    author_user_id: str | None = None
    author_user_name: str | None = None
    created_at: str | None = None


class GatherChatMessageArtifact(BaseIngestArtifact):
    """Typed Gather chat message artifact."""

    entity: ArtifactEntity = ArtifactEntity.GATHER_CHAT_MESSAGE
    content: GatherChatMessageArtifactContent
    metadata: GatherChatMessageArtifactMetadata


# ============================================================================
# Meeting Transcript Artifact
# ============================================================================


class GatherMeetingTranscriptArtifactMetadata(BaseModel):
    """Metadata for Gather meeting transcript (memo) artifacts."""

    transcript_id: str
    meeting_id: str
    memo_id: str
    space_id: str
    speaker_id: str
    transcript_ended_at_or_created_at: str | None = None


class GatherMeetingTranscriptArtifactContent(BaseModel):
    """Content for Gather meeting transcript artifacts."""

    speaker_name: str
    content: str
    transcript_ended_at_or_created_at: str | None = None


class GatherMeetingTranscriptArtifact(BaseIngestArtifact):
    """Typed Gather meeting transcript artifact for meeting memos."""

    entity: ArtifactEntity = ArtifactEntity.GATHER_MEETING_TRANSCRIPT
    content: GatherMeetingTranscriptArtifactContent
    metadata: GatherMeetingTranscriptArtifactMetadata
