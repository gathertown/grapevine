from dataclasses import dataclass
from datetime import datetime
from functools import reduce
from typing import TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base.base_chunk import BaseChunk
from connectors.base.base_document import BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.fireflies.client.fireflies_models import FirefliesSentence, FirefliesSpeaker
from connectors.fireflies.extractors.artifacts.fireflies_transcript_artifact import (
    FirefliesTranscriptArtifact,
    fireflies_transcript_entity_id,
)
from src.permissions.utils import make_email_permission_token


class FirefliesTranscriptChunkMetadata(TypedDict):
    chunk_index: int
    total_chunks: int
    transcript_id: str


class FirefliesTranscriptChunkRawData(TypedDict):
    content: str
    chunk_index: int
    total_chunks: int
    transcript_id: str


class FirefliesTranscriptChunk(BaseChunk[FirefliesTranscriptChunkMetadata]):
    raw_data: FirefliesTranscriptChunkRawData

    def get_content(self) -> str:
        content = self.raw_data["content"]
        chunk_index = self.raw_data["chunk_index"]
        total_chunks = self.raw_data["total_chunks"]

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> FirefliesTranscriptChunkMetadata:
        return FirefliesTranscriptChunkMetadata(
            transcript_id=self.raw_data["transcript_id"],
            chunk_index=self.raw_data["chunk_index"],
            total_chunks=self.raw_data["total_chunks"],
        )


class FirefliesTranscriptDocumentMetadata(TypedDict):
    transcript_id: str
    transcript_url: str
    date_string: str
    transcript_title: str | None
    organizer_email: str | None
    meeting_participants: list[str]
    duration: float | None


@dataclass
class FirefliesTranscriptDocument(
    BaseDocument[FirefliesTranscriptChunk, FirefliesTranscriptDocumentMetadata]
):
    transcript_artifact: FirefliesTranscriptArtifact

    def to_embedding_chunks(self) -> list[FirefliesTranscriptChunk]:
        full_content = self.get_content()

        if not full_content.strip():
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        text_chunks = text_splitter.split_text(full_content)

        return [
            FirefliesTranscriptChunk(
                document=self,
                raw_data=FirefliesTranscriptChunkRawData(
                    content=chunk_text,
                    chunk_index=i,
                    total_chunks=len(text_chunks),
                    transcript_id=self.transcript_artifact.metadata.transcript_id,
                ),
            )
            for i, chunk_text in enumerate(text_chunks)
        ]

    def get_content(self) -> str:
        speakers_by_id: dict[int | None, FirefliesSpeaker] = {
            speaker.id: speaker for speaker in self.transcript_artifact.content.speakers or []
        }

        accumulated_sentences = reduce(
            self._sentence_accumulator,
            self.transcript_artifact.content.sentences or [],
            list[FirefliesSentence](),
        )

        content = "\n\n".join(
            self._get_sentence_content(speakers_by_id.get(s.speaker_id), s)
            for s in accumulated_sentences
        )

        summary_content = (
            self.transcript_artifact.content.summary.notes
            if self.transcript_artifact.content.summary
            and self.transcript_artifact.content.summary.notes
            else ""
        )

        return (
            self._get_header_content()
            + "\n\n# Summary\n\n"
            + summary_content
            + "\n\n# Full Transcript\n\n"
            + content
        )

    # Merge neighbouring sentences by the same speaker for a cleaner transcript
    def _sentence_accumulator(
        self, acc: list[FirefliesSentence], sentence: FirefliesSentence
    ) -> list[FirefliesSentence]:
        if acc:
            last_sentence = acc[-1]
            same_speaker = (
                last_sentence.speaker_id == sentence.speaker_id and sentence.speaker_id is not None
            )

            if same_speaker:
                return acc[:-1] + [
                    FirefliesSentence(
                        text=f"{last_sentence.text} {sentence.text}",
                        speaker_id=last_sentence.speaker_id,
                    )
                ]

        return acc + [sentence]

    def _get_sentence_content(
        self, speaker: FirefliesSpeaker | None, sentence: FirefliesSentence
    ) -> str:
        speaker_name = speaker.name if speaker and speaker.name else "Unknown Speaker"
        return f"{speaker_name}: {sentence.text}"

    def _get_header_content(self) -> str:
        date_string = self.transcript_artifact.metadata.date_string
        url = self.transcript_artifact.metadata.transcript_url
        title = self.transcript_artifact.metadata.transcript_title or ""
        organizer = self.transcript_artifact.metadata.organizer_email or ""
        participants = ", ".join(self.transcript_artifact.metadata.participants)

        lines: list[str] = []

        lines.append(f"# Meeting Transcript: {title}")
        lines.append(f"Date: {date_string}")
        lines.append(f"Organizer: {organizer}")
        lines.append(f"Participants: {participants}")
        lines.append(f"URL: {url}")

        return "\n".join(lines)

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.FIREFLIES_TRANSCRIPT

    def get_reference_id(self) -> str:
        return fireflies_transcript_entity_id(self.transcript_artifact.metadata.transcript_id)

    def get_metadata(self) -> FirefliesTranscriptDocumentMetadata:
        return {
            "transcript_id": self.transcript_artifact.metadata.transcript_id,
            "transcript_url": self.transcript_artifact.metadata.transcript_url,
            "date_string": self.transcript_artifact.metadata.date_string,
            "organizer_email": self.transcript_artifact.metadata.organizer_email,
            "transcript_title": self.transcript_artifact.metadata.transcript_title,
            "meeting_participants": self.transcript_artifact.metadata.participants,
            "duration": self.transcript_artifact.metadata.duration,
        }

    def get_source_created_at(self) -> datetime:
        return datetime.fromisoformat(self.transcript_artifact.metadata.date_string)

    @classmethod
    def from_artifacts(
        cls,
        transcript: FirefliesTranscriptArtifact,
    ) -> "FirefliesTranscriptDocument":
        allowed_emails = set(transcript.content.participants)
        if transcript.content.organizer_email:
            allowed_emails.add(transcript.content.organizer_email)

        return FirefliesTranscriptDocument(
            id=fireflies_transcript_document_id(transcript.metadata.transcript_id),
            permission_policy="private",
            permission_allowed_tokens=[
                make_email_permission_token(email) for email in allowed_emails
            ],
            transcript_artifact=transcript,
            source_updated_at=transcript.source_updated_at,
        )


def fireflies_transcript_reference_id(transcript_id: str) -> str:
    return f"r_fireflies_transcript_{transcript_id}"


def fireflies_transcript_document_id(transcript_id: str) -> str:
    return f"fireflies_transcript_{transcript_id}"
