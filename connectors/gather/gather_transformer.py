"""
Transformer for Gather meetings artifacts to documents.
"""

import logging
import traceback
from typing import Any

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_gather_meeting_doc_id
from connectors.base.document_source import DocumentSource
from connectors.gather.gather_artifacts import (
    GatherChatMessageArtifact,
    GatherMeetingArtifact,
    GatherMeetingMemoArtifact,
    GatherMeetingTranscriptArtifact,
)
from connectors.gather.gather_meeting_document import GatherMeetingDocument
from src.ingest.repositories import ArtifactRepository
from src.permissions.models import PermissionPolicy
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class GatherTransformer(BaseTransformer[GatherMeetingDocument]):
    """Transformer for Gather meeting artifacts."""

    def __init__(self):
        super().__init__(DocumentSource.GATHER)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool, tenant_id: str | None = None
    ) -> list[GatherMeetingDocument]:
        """
        Transform meeting artifacts into documents.

        For each meeting_id (entity_id), we need to:
        1. Load the GatherMeetingArtifact (metadata + participants)
        2. Load all GatherMeetingMemoArtifacts (memos) for this meeting
        3. Load all GatherChatMessageArtifacts (chat messages) for this meeting
        4. Reconstruct the full meeting data structure
        5. Create a GatherMeetingDocument
        """
        repo = ArtifactRepository(readonly_db_pool)

        # Load meeting artifacts
        meeting_artifacts = await repo.get_artifacts_by_entity_ids(
            GatherMeetingArtifact, entity_ids
        )

        logger.info(
            f"Loaded {len(meeting_artifacts)} meeting artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}
        skipped_count = 0

        for meeting_artifact in meeting_artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform artifact {meeting_artifact.id}", counter
            ):
                meeting_id = meeting_artifact.metadata.meeting_id

                # Load memo artifacts for this meeting
                memo_artifacts = await self._load_memo_artifacts(repo, meeting_id)

                # Load chat message artifacts for this meeting
                chat_message_artifacts = await self._load_chat_message_artifacts(repo, meeting_id)

                logger.debug(
                    f"Meeting {meeting_id}: {len(memo_artifacts)} memos, "
                    f"{len(chat_message_artifacts)} chat messages"
                )

                # Reconstruct full meeting data
                document = await self._create_document(
                    meeting_artifact, memo_artifacts, chat_message_artifacts, repo
                )

                if document:
                    documents.append(document)

                    if len(documents) % 100 == 0:
                        logger.info(f"Processed {len(documents)}/{len(meeting_artifacts)} meetings")
                else:
                    skipped_count += 1
                    logger.warning(f"Skipped meeting {meeting_id} - no document created")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Gather transformation complete: {successful} successful, {failed} failed, {skipped_count} skipped. "
            f"Created {len(documents)} documents from {len(meeting_artifacts)} artifacts"
        )
        return documents

    async def _load_memo_artifacts(
        self, repo: ArtifactRepository, meeting_id: str
    ) -> list[GatherMeetingMemoArtifact]:
        """Load all memo artifacts for a meeting using metadata filter."""
        # Query artifacts where metadata contains the meeting_id
        artifacts = await repo.get_artifacts_by_metadata_filter(
            GatherMeetingMemoArtifact, {"meeting_id": meeting_id}
        )
        return artifacts

    async def _load_memo_transcript_artifacts(
        self, repo: ArtifactRepository, meeting_id: str, memo_id: str
    ) -> list[GatherMeetingTranscriptArtifact]:
        """Load all memo transcript artifacts for a meeting using metadata filter."""
        # Query artifacts where metadata contains the meeting_id
        artifacts = await repo.get_artifacts_by_metadata_filter(
            GatherMeetingTranscriptArtifact, {"meeting_id": meeting_id, "memo_id": memo_id}
        )
        return artifacts

    async def _load_chat_message_artifacts(
        self, repo: ArtifactRepository, meeting_id: str
    ) -> list[GatherChatMessageArtifact]:
        """Load all chat message artifacts for a meeting using metadata filter."""
        # Query artifacts where metadata contains the meeting_id
        artifacts = await repo.get_artifacts_by_metadata_filter(
            GatherChatMessageArtifact, {"meeting_id": meeting_id}
        )
        return artifacts

    async def _create_document(
        self,
        meeting_artifact: GatherMeetingArtifact,
        memo_artifacts: list[GatherMeetingMemoArtifact],
        chat_message_artifacts: list[GatherChatMessageArtifact],
        repo: ArtifactRepository,
    ) -> GatherMeetingDocument | None:
        """Create a GatherMeetingDocument by reconstructing the full meeting data."""
        try:
            meeting_id = meeting_artifact.metadata.meeting_id
            participants = [p.model_dump() for p in meeting_artifact.content.participants]
            # Reconstruct the full meeting data structure from separate artifacts
            meeting_data: dict[str, Any] = {
                "id": meeting_artifact.metadata.meeting_id,
                "type": meeting_artifact.content.meeting_type,
                "spaceId": meeting_artifact.metadata.space_id,
                "participants": participants,
                "source_created_at": meeting_artifact.metadata.source_created_at,
                "calendarEvent": {"title": meeting_artifact.content.calendar_event_title}
                if meeting_artifact.content.calendar_event_title
                else None,
                "startedAt": meeting_artifact.content.started_at
                if meeting_artifact.content.started_at
                else None,
                "endedAt": meeting_artifact.content.ended_at
                if meeting_artifact.content.ended_at
                else None,
                "meetingMemos": [],
                "chatChannel": {"messages": []},
            }
            # Add memo data
            for memo_artifact in memo_artifacts:
                # Convert notes from Pydantic models to dicts
                notes_data = None
                if memo_artifact.content.notes:
                    notes_data = [note.model_dump() for note in memo_artifact.content.notes]

                memo_data: dict[str, Any] = {
                    "id": memo_artifact.metadata.memo_id,
                    "summary": memo_artifact.content.summary,
                    "notes": notes_data,
                    "actionItems": memo_artifact.content.action_items,
                    "createdAt": memo_artifact.content.created_at
                    if memo_artifact.content.created_at
                    else None,
                    "transcript": [],
                }

                transcript_artifacts = await self._load_memo_transcript_artifacts(
                    repo=repo,
                    meeting_id=meeting_id,
                    memo_id=memo_artifact.metadata.memo_id,
                )

                for transcript_artifact in transcript_artifacts:
                    transcript_data = {
                        "id": transcript_artifact.metadata.transcript_id,
                        "memo_id": transcript_artifact.metadata.memo_id,
                        "meeting_id": transcript_artifact.metadata.meeting_id,
                        "speaker_id": transcript_artifact.metadata.speaker_id,
                        "speaker_name": transcript_artifact.content.speaker_name,
                        "transcript_ended_at_or_created_at": transcript_artifact.content.transcript_ended_at_or_created_at,
                        "content": transcript_artifact.content.content
                        if transcript_artifact.content.transcript_ended_at_or_created_at
                        else None,
                    }
                    memo_data["transcript"].append(transcript_data)

                meeting_data["meetingMemos"].append(memo_data)

            # Add chat message data
            for message_artifact in chat_message_artifacts:
                message_data = {
                    "id": message_artifact.metadata.message_id,
                    "text": message_artifact.content.text,
                    "author_user_id": message_artifact.content.author_user_id,
                    "author_user_name": message_artifact.content.author_user_name,
                    "createdAt": message_artifact.content.created_at
                    if message_artifact.content.created_at
                    else None,
                }
                meeting_data["chatChannel"]["messages"].append(message_data)

            # Default to private with participant-only access
            permission_policy: PermissionPolicy = "private"
            permission_allowed_tokens: list[str] | None = [
                f"e:{p.get('email')}" for p in participants
            ]

            # Create document from reconstructed meeting data
            document = GatherMeetingDocument(
                id=get_gather_meeting_doc_id(meeting_id),
                raw_data=meeting_data,
                source_updated_at=meeting_artifact.source_updated_at,
                permission_policy=permission_policy,
                permission_allowed_tokens=permission_allowed_tokens,
            )

            return document

        except Exception as e:
            logger.error(
                f"Failed to create document for meeting {meeting_artifact.metadata.meeting_id}: {e}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            return None
