"""
Base extractor class for Gather-based extractors.
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from connectors.base import (
    BaseExtractor,
    BaseIngestArtifact,
    TriggerIndexingCallback,
    get_gather_chat_message_entity_id,
    get_gather_meeting_entity_id,
    get_gather_meeting_memo_entity_id,
    get_gather_meeting_transcript_entity_id,
)
from connectors.gather.gather_artifacts import (
    GatherChatMessageArtifact,
    GatherChatMessageArtifactContent,
    GatherChatMessageArtifactMetadata,
    GatherMeetingArtifact,
    GatherMeetingArtifactContent,
    GatherMeetingArtifactMetadata,
    GatherMeetingMemoArtifact,
    GatherMeetingMemoArtifactContent,
    GatherMeetingMemoArtifactMetadata,
    GatherMeetingParticipant,
    GatherMeetingTranscriptArtifact,
    GatherMeetingTranscriptArtifactContent,
    GatherMeetingTranscriptArtifactMetadata,
)
from connectors.gather.gather_models import GatherApiBackfillConfig
from src.clients.gather import GatherClient
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


GatherConfigType = TypeVar("GatherConfigType", bound=BaseModel)


class GatherExtractor(BaseExtractor[GatherConfigType], ABC):
    """Abstract base class for Gather-based extractors."""

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        self._gather_clients: dict[str, GatherClient] = {}

    async def get_gather_client(self, tenant_id: str) -> GatherClient:
        """Get GatherClient for the specified tenant."""
        if tenant_id not in self._gather_clients:
            api_key = await self.ssm_client.get_gather_api_key(tenant_id)
            if not api_key:
                raise ValueError(f"No Gather API key configured for tenant {tenant_id}")
            self._gather_clients[tenant_id] = GatherClient(api_key)
        return self._gather_clients[tenant_id]

    @abstractmethod
    async def process_job(
        self,
        job_id: str,
        config: GatherConfigType,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process an ingest job - must be implemented by subclasses."""
        pass

    async def _process_meeting(
        self, job_id: str, meeting_data: dict[str, Any], space_id: str, tenant_id: str
    ) -> list[BaseIngestArtifact]:
        """
        Process a single meeting and create artifacts.

        Creates multiple artifacts:
        - One meeting artifact (metadata only)
        - One memo artifact per memo
        - One chat message artifact per chat message

        Args:
            job_id: The ingest job ID
            meeting_data: Raw meeting data from Gather API
            space_id: The Gather space ID
            tenant_id: The tenant ID

        Returns:
            List of artifacts created for this meeting
        """
        meeting_id = meeting_data.get("id")
        if not meeting_id:
            raise ValueError(f"Meeting ID not found in meeting data: {meeting_data}")

        artifacts: list[BaseIngestArtifact] = []
        source_updated_at = datetime.now(tz=UTC)

        # Extract meeting metadata
        meeting_type = meeting_data.get("type", "")
        raw_participants = meeting_data.get("participants", [])
        meeting_memos = meeting_data.get("meetingMemos", [])
        chat_channel = meeting_data.get("chatChannel", {})
        messages = chat_channel.get("messages", []) if chat_channel else []
        calendar_event = meeting_data.get("calendarEvent", {})

        # Parse timestamps
        started_at = meeting_data.get("startedAt")
        ended_at = meeting_data.get("endedAt")

        # Convert participants to typed models
        participants = [
            GatherMeetingParticipant(
                space_user_id=p.get("spaceUserId", ""),
                display_name=p.get("displayName", ""),
                # Fallback to empty string if email is not present
                # Currently, the only known case this happens is when
                # we have the recording client added as a participant
                # There is a todo to filter this user out from the meeting serializer
                email=p.get("email", "") or "",
                response_status=p.get("responseStatus"),
                joined_at=p.get("joinedAt"),
                left_at=p.get("leftAt"),
            )
            for p in raw_participants
        ]

        # 1. Create meeting artifact (metadata only)
        meeting_artifact = GatherMeetingArtifact(
            entity_id=get_gather_meeting_entity_id(meeting_id=meeting_id),
            ingest_job_id=UUID(job_id),
            content=GatherMeetingArtifactContent(
                meeting_type=meeting_type,
                participants=participants,
                calendar_event_title=calendar_event.get("title") if calendar_event else None,
                started_at=started_at,
                ended_at=ended_at,
            ),
            metadata=GatherMeetingArtifactMetadata(
                meeting_id=meeting_id,
                meeting_type=meeting_type,
                space_id=space_id,
                calendar_event_title=calendar_event.get("title") if calendar_event else None,
                participant_count=len(participants),
                started_at=started_at,
                ended_at=ended_at,
                source_created_at=meeting_data.get("createdAt"),
            ),
            source_updated_at=source_updated_at,
        )
        artifacts.append(meeting_artifact)

        # 2. Create memo artifacts (one per memo)
        for memo in meeting_memos:
            memo_id = memo.get("id")
            if not memo_id:
                logger.warning(f"Skipping memo without ID in meeting {meeting_id}")
                continue

            memo_artifact = GatherMeetingMemoArtifact(
                entity_id=get_gather_meeting_memo_entity_id(meeting_id=meeting_id, memo_id=memo_id),
                ingest_job_id=UUID(job_id),
                content=GatherMeetingMemoArtifactContent(
                    summary=memo.get("summary"),
                    notes=memo.get("notes"),
                    action_items=memo.get("actionItems"),
                    created_at=memo.get("createdAt"),
                ),
                metadata=GatherMeetingMemoArtifactMetadata(
                    meeting_id=meeting_id,
                    memo_id=memo_id,
                    space_id=space_id,
                    created_at=memo.get("createdAt"),
                ),
                source_updated_at=source_updated_at,
            )

            # 2a. Create transcript artifacts (one per speaker transcript)
            for transcript_entry in memo.get("transcript", []):
                speaker_id = transcript_entry.get("speakerId")
                if not speaker_id:
                    logger.warning(
                        f"Skipping transcript entry without speaker ID in memo {memo_id} of meeting {meeting_id}"
                    )
                    continue

                # Create transcript artifact for each speaker's transcript entry
                transcript_artifact = GatherMeetingTranscriptArtifact(
                    entity_id=get_gather_meeting_transcript_entity_id(
                        meeting_id=meeting_id,
                        memo_id=memo_id,
                        transcript_id=transcript_entry.get("id", ""),
                    ),
                    ingest_job_id=UUID(job_id),
                    content=GatherMeetingTranscriptArtifactContent(
                        speaker_name=transcript_entry.get("speakerName", ""),
                        content=transcript_entry.get("content", ""),
                        transcript_ended_at_or_created_at=transcript_entry.get(
                            "transcriptEndedAtOrCreatedAt", ""
                        ),
                    ),
                    metadata=GatherMeetingTranscriptArtifactMetadata(
                        transcript_id=transcript_entry.get("id", ""),
                        meeting_id=meeting_id,
                        memo_id=memo_id,
                        space_id=space_id,
                        speaker_id=speaker_id,
                        transcript_ended_at_or_created_at=transcript_entry.get(
                            "transcriptEndedAtOrCreatedAt", ""
                        ),
                    ),
                    source_updated_at=source_updated_at,
                )

                artifacts.append(transcript_artifact)

            artifacts.append(memo_artifact)

        # 3. Create chat message artifacts (one per message)
        for message in messages:
            message_id = message.get("id")
            if not message_id:
                logger.warning(f"Skipping message without ID in meeting {meeting_id}")
                continue

            chat_message_artifact = GatherChatMessageArtifact(
                entity_id=get_gather_chat_message_entity_id(
                    meeting_id=meeting_id, message_id=message_id
                ),
                ingest_job_id=UUID(job_id),
                content=GatherChatMessageArtifactContent(
                    text=message.get("text", ""),
                    author_user_id=message.get("authorId"),
                    author_user_name=message.get("authorName"),
                    created_at=message.get("createdAt"),
                ),
                metadata=GatherChatMessageArtifactMetadata(
                    meeting_id=meeting_id,
                    message_id=message_id,
                    space_id=space_id,
                    author_user_id=message.get("authorId"),
                    author_user_name=message.get("authorName"),
                    created_at=message.get("createdAt"),
                ),
                source_updated_at=source_updated_at,
            )
            artifacts.append(chat_message_artifact)

        logger.info(
            f"Created {len(artifacts)} artifacts for meeting {meeting_id}: "
            f"1 meeting, {len(meeting_memos)} memos, {len(messages)} chat messages"
        )

        return artifacts

    async def send_backfill_child_job_message(
        self,
        config: GatherApiBackfillConfig,
        description: str = "job",
    ) -> None:
        """
        Send a Gather backfill job message.

        Args:
            config: The backfill job configuration to send
            description: Description for logging (e.g., "child job batch 0", "re-queued job")
        """
        try:
            await self.sqs_client.send_backfill_ingest_message(
                backfill_config=config,
            )

            # Log the message sending
            log_message = f"Sent {description} for tenant {config.tenant_id} with {len(config.meetings_data)} meetings"
            if config.start_timestamp:
                log_message += f". Was scheduled to start at {config.start_timestamp.isoformat()}"
            logger.info(log_message)

        except Exception as e:
            logger.error(f"Failed to send {description}: {e}")
            raise
