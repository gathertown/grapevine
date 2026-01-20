"""
Pydantic models for SQS job messages.

WARNING: The backfill schemas in this file must be kept in sync with the TypeScript Zod schemas
in js-services/admin-backend/src/jobs/models.ts. Any changes here must be reflected there.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from connectors.base.document_source import DocumentSource
from connectors.base.external_source import ExternalSource
from connectors.base.models import BackfillIngestConfig


class IndexJobMessage(BaseModel):
    """Message for triggering index jobs via SQS."""

    entity_ids: list[str]
    source: DocumentSource
    tenant_id: str
    force_reindex: bool = False
    turbopuffer_only: bool = False
    backfill_id: str | None = None
    suppress_notification: bool = False


# WARNING: This must match the zod schema `WebhookMessage`!
class WebhookIngestJobMessage(BaseModel):
    """
    Processed webhook ready for ingestion.

    WARNING: This must match the zod schema `WebhookMessage`!
    Be sure to keep these two schemas in sync.
    """

    message_type: Literal["webhook"] = "webhook"
    webhook_body: str
    webhook_headers: dict[str, str]
    tenant_id: str
    source_type: ExternalSource
    timestamp: str


# WARNING: This must match the zod schema `ControlMessage`!
class SlackBotControlMessage(BaseModel):
    """
    Control message for Slack bot operations.

    WARNING: This must match the zod schema `ControlMessage`!
    Be sure to keep these two schemas in sync.
    """

    tenant_id: str
    control_type: Literal[
        "join_all_channels", "refresh_bot_credentials", "welcome_message", "triage_channel_welcome"
    ]
    source_type: Literal["control"] = "control"
    timestamp: str
    channel_ids: list[str] | None = None  # List of channel IDs for triage_channel_welcome


# WARNING: This must match the TypeScript SampleQuestionAnswererMessage!
class SampleQuestionAnswererMessage(BaseModel):
    """
    Sample question answerer message for triggering the sample question answerer job.

    WARNING: This must match the TypeScript SampleQuestionAnswererMessage!
    Be sure to keep these two schemas in sync.
    """

    source_type: Literal["sample_question_answerer"] = "sample_question_answerer"
    tenant_id: str
    timestamp: str
    iteration_count: int | None = None


class BackfillNotificationMessage(BaseModel):
    """
    Backfill notification message for notifying Slack bot when backfill starts.

    WARNING: This must match the TypeScript BackfillNotificationMessage!
    Be sure to keep these two schemas in sync.
    """

    source_type: Literal["backfill_notification"] = "backfill_notification"
    tenant_id: str
    source: ExternalSource


class BackfillCompleteNotificationMessage(BaseModel):
    """
    Backfill complete notification message for notifying Slack bot when backfill finishes.

    WARNING: This must match the TypeScript BackfillCompleteNotificationMessage!
    Be sure to keep these two schemas in sync.
    """

    source_type: Literal["backfill_complete_notification"] = "backfill_complete_notification"
    tenant_id: str
    source: ExternalSource
    backfill_id: str


# WARNING: This must match the zod schema `TenantDataDeletionMessage`!
class TenantDataDeletionMessage(BaseModel):
    """
    Message for triggering tenant data deletion.

    WARNING: This must match the zod schema `TenantDataDeletionMessage`!
    Be sure to keep these two schemas in sync.
    """

    message_type: Literal["tenant_data_deletion"] = "tenant_data_deletion"
    tenant_id: str


# WARNING: This must match the zod schema `ReindexJobMessage`!
class ReindexJobMessage(BaseModel):
    """
    Message for triggering full re-index of a source type.

    WARNING: This must match the zod schema `ReindexJobMessage`!
    Be sure to keep these two schemas in sync.
    """

    message_type: Literal["reindex"] = "reindex"
    tenant_id: str
    source: DocumentSource
    turbopuffer_only: bool = False


# WARNING: This must match the zod schema `DeleteJobMessage`!
class DeleteJobMessage(BaseModel):
    """
    Message for deleting documents from the search index.

    WARNING: This must match the zod schema `DeleteJobMessage`!
    Be sure to keep these two schemas in sync.
    """

    message_type: Literal["delete"] = "delete"
    tenant_id: str
    document_ids: list[str]


# Top-level discriminated union for all ingest job messages
IngestJobMessage = (
    WebhookIngestJobMessage | ReindexJobMessage | TenantDataDeletionMessage | BackfillIngestConfig
)


# Union type for messages that can be sent to the Slack bot queue
# This matches the discriminated union in the TypeScript code
SlackBotJobMessage = (
    WebhookIngestJobMessage
    | SlackBotControlMessage
    | SampleQuestionAnswererMessage
    | BackfillNotificationMessage
    | BackfillCompleteNotificationMessage
)
