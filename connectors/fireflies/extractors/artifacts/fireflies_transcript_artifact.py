from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact
from connectors.fireflies.client.fireflies_models import FirefliesTranscript


class FirefliesTranscriptArtifactMetadata(BaseModel):
    transcript_id: str
    transcript_url: str
    date_string: str
    transcript_title: str | None
    organizer_email: str | None
    participants: list[str]
    duration: float | None
    summary_status: str | None  # processing | processed | failed | skipped


def fireflies_transcript_entity_id(transcript_id: str) -> str:
    return f"fireflies_transcript_{transcript_id}"


class FirefliesTranscriptArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.FIREFLIES_TRANSCRIPT
    content: FirefliesTranscript
    metadata: FirefliesTranscriptArtifactMetadata

    @classmethod
    def from_api_transcript(
        cls, transcript: FirefliesTranscript, ingest_job_id: UUID
    ) -> "FirefliesTranscriptArtifact":
        return FirefliesTranscriptArtifact(
            entity_id=fireflies_transcript_entity_id(transcript.id),
            content=transcript,
            metadata=FirefliesTranscriptArtifactMetadata(
                transcript_id=transcript.id,
                transcript_url=transcript.transcript_url,
                date_string=transcript.date_string,
                transcript_title=transcript.title,
                organizer_email=transcript.organizer_email,
                participants=transcript.participants,
                duration=transcript.duration,
                summary_status=transcript.meeting_info.summary_status,
            ),
            # there is no "modfied at" on fireflies transcripts, so use ingestion time to ensure update happens
            source_updated_at=datetime.now(UTC),
            ingest_job_id=ingest_job_id,
        )
