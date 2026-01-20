"""
Gather webhook extractor for processing Gather meeting webhook events.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import (
    get_gather_meeting_entity_id,
    get_gather_meeting_memo_entity_id,
    get_gather_meeting_transcript_entity_id,
)
from connectors.base.base_ingest_artifact import BaseIngestArtifact
from connectors.base.document_source import DocumentSource
from connectors.gather.gather_artifacts import (
    GatherMeetingMemoArtifact,
    GatherMeetingMemoArtifactContent,
    GatherMeetingMemoArtifactMetadata,
    GatherMeetingNote,
    GatherMeetingTranscriptArtifact,
    GatherMeetingTranscriptArtifactContent,
    GatherMeetingTranscriptArtifactMetadata,
)
from connectors.gather.gather_base import GatherExtractor
from connectors.gather.gather_models import GatherWebhookConfig

logger = logging.getLogger(__name__)


class GatherWebhookExtractor(GatherExtractor[GatherWebhookConfig]):
    """Extractor for processing Gather webhook events."""

    source_name = "gather_webhook"

    async def process_job(
        self,
        job_id: str,
        config: GatherWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing,
    ) -> None:
        """
        Process a Gather webhook job.

        Handles two event types:
        - MeetingEnded: Triggered when a meeting ends
        - MeetingTranscriptCompleted: Triggered when meeting transcript is ready

        Args:
            job_id: The ingest job ID
            config: The webhook configuration containing the webhook payload
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing for the meeting
        """
        tenant_id = config.tenant_id
        headers = config.headers

        # Event type is provided in X-Gather-Event header
        event_type = headers.get("x-gather-event", "")

        if not event_type:
            logger.warning(f"Webhook missing X-Gather-Event header: {headers}")
            return

        logger.info(f"Processing Gather webhook event '{event_type}' for tenant {tenant_id}")

        # Handle different event types
        if event_type == "MeetingEnded":
            await self._handle_meeting_ended(
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )
        elif event_type == "MeetingTranscriptCompleted":
            await self._handle_transcript_completed(
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )
        else:
            logger.warning(f"Unknown Gather webhook event type: {event_type}")

    async def _handle_meeting_ended(
        self,
        job_id: str,
        config: GatherWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing,
    ) -> None:
        """
        Handle MeetingEnded webhook event.

        Args:
            job_id: The ingest job ID
            config: The webhook configuration
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
        """
        tenant_id = config.tenant_id
        webhook_body = config.body
        webhook_data = webhook_body.get("data", {})

        space_id = webhook_data.get("spaceId")
        meeting_id = webhook_data.get("meetingId")
        meeting_data = webhook_data.get("meeting", {})

        if not space_id:
            logger.warning(f"MeetingEnded webhook missing spaceId: {webhook_data}")
            return

        if not meeting_id:
            logger.warning(f"MeetingEnded webhook missing meeting ID: {webhook_data}")
            return

        logger.info(f"Processing MeetingEnded event for meeting {meeting_id}")

        # Process the meeting and create artifacts
        artifacts = await self._process_meeting(
            job_id=job_id,
            meeting_data=meeting_data,
            space_id=space_id,
            tenant_id=tenant_id,
        )

        if not artifacts:
            logger.warning(f"No artifacts created for meeting {meeting_id}")
            return

        # Store artifacts in database
        await self.store_artifacts_batch(db_pool, artifacts)

        logger.info(f"Stored {len(artifacts)} artifacts for meeting {meeting_id}")
        # Trigger indexing for the meeting artifact (the main document)
        meeting_entity_id = get_gather_meeting_entity_id(meeting_id=meeting_id)

        await trigger_indexing(
            tenant_id=tenant_id,
            source=DocumentSource.GATHER,
            entity_ids=[meeting_entity_id],
        )

        logger.info(f"Triggered indexing for meeting {meeting_id}")

    async def _handle_transcript_completed(
        self,
        job_id: str,
        config: GatherWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing,
    ) -> None:
        """
        Handle MeetingTranscriptCompleted webhook event.

        Payload schema:
        {
          "data": {
            "meetingId": "string",
            "spaceId": "string",
            "meetingMemo": {
              "id": "uuid",
              "language": "string",
              "summary": "string",
              "notes": [...],
              "actionItems": [...],
              "startedAt": "datetime",
              "endedAt": "datetime"
            }
          }
        }

        Args:
            job_id: The ingest job ID
            config: The webhook configuration
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
        """
        tenant_id = config.tenant_id
        webhook_body = config.body
        data = webhook_body.get("data", {})

        meeting_id = data.get("meetingId")
        space_id = data.get("spaceId")
        meeting_memo = data.get("meetingMemo", {})

        if not meeting_id:
            logger.warning(f"MeetingTranscriptCompleted webhook missing meetingId: {data}")
            return

        if not space_id:
            logger.warning(f"MeetingTranscriptCompleted webhook missing spaceId: {data}")
            return

        memo_id = meeting_memo.get("id")
        if not memo_id:
            logger.warning(f"MeetingTranscriptCompleted webhook missing memo ID: {meeting_memo}")
            return

        logger.info(
            f"Processing MeetingTranscriptCompleted event for meeting {meeting_id}, memo {memo_id}"
        )

        # Parse notes into GatherMeetingNote objects
        raw_notes = meeting_memo.get("notes", [])
        notes = (
            [
                GatherMeetingNote(
                    heading=note.get("heading", ""),
                    bullets=note.get("bullets", []),
                )
                for note in raw_notes
            ]
            if raw_notes
            else None
        )

        # Create memo artifact directly from payload
        memo_artifact = GatherMeetingMemoArtifact(
            entity_id=get_gather_meeting_memo_entity_id(meeting_id=meeting_id, memo_id=memo_id),
            ingest_job_id=UUID(job_id),
            content=GatherMeetingMemoArtifactContent(
                summary=meeting_memo.get("summary"),
                notes=notes,
                action_items=meeting_memo.get("actionItems"),
                created_at=meeting_memo.get("startedAt"),
            ),
            metadata=GatherMeetingMemoArtifactMetadata(
                meeting_id=meeting_id,
                memo_id=memo_id,
                space_id=space_id,
                created_at=meeting_memo.get("startedAt"),
            ),
            source_updated_at=datetime.now(tz=UTC),
        )

        artifacts: list[BaseIngestArtifact] = [memo_artifact]

        for transcript_entry in meeting_memo.get("transcript", []):
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
                source_updated_at=datetime.now(tz=UTC),
            )

            artifacts.append(transcript_artifact)

        # Store artifact in database
        await self.store_artifacts_batch(db_pool, artifacts)

        logger.info(f"Stored memo artifact for meeting {meeting_id}, memo {memo_id}")

        # Trigger indexing for the meeting artifact (the parent document)
        # not the memo artifact itself
        meeting_entity_id = get_gather_meeting_entity_id(meeting_id=meeting_id)
        await trigger_indexing(
            tenant_id=tenant_id,
            source=DocumentSource.GATHER,
            entity_ids=[meeting_entity_id],
        )

        logger.info(f"Triggered indexing for meeting {meeting_id} (memo completed)")
