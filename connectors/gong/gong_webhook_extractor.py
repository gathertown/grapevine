"""Gong webhook extractor for real-time call updates."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.gong.gong_artifacts import (
    GongCallArtifact,
    GongCallContent,
    GongCallMetadata,
)
from connectors.gong.gong_models import GongWebhookConfig
from src.ingest.repositories import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


class GongWebhookExtractor(BaseExtractor[GongWebhookConfig]):
    """Process Gong webhook events for real-time call updates.

    Gong sends webhooks when automation rules trigger, containing:
    - callData: Full call metadata (same structure as API)
    - isTest: Flag indicating test webhook (handled by gatekeeper)

    Note: Webhooks provide call metadata and parties but not transcripts.
    A full backfill or separate transcript fetch would be needed for transcripts.
    """

    source_name = "gong_webhook"

    async def process_job(
        self,
        job_id: str,
        config: GongWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process a Gong webhook event.

        Args:
            job_id: The ingest job ID
            config: Webhook configuration with payload and tenant ID
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing for updated calls
        """
        logger.info("Processing Gong webhook job", job_id=job_id, tenant_id=config.tenant_id)

        payload = config.body

        # Extract call data from webhook payload
        # The payload structure is: {"callData": {...}, "isTest": false}
        call_data = payload.get("callData")
        if not call_data:
            logger.warning("Gong webhook missing callData field", job_id=job_id)
            return

        # Extract call ID from metadata
        meta = call_data.get("metaData", {})
        call_id = str(meta.get("id")) if meta.get("id") else None
        if not call_id:
            # Extract call ID from call data (same as API structure)
            call_id = str(call_data.get("id")) if call_data.get("id") else None

        if not call_id:
            logger.warning("Gong webhook call data missing ID", job_id=job_id)
            return

        logger.info(
            "Processing Gong call from webhook",
            job_id=job_id,
            call_id=call_id,
            tenant_id=config.tenant_id,
        )

        # Create call artifact from webhook data
        try:
            # Parse datetime
            started_dt = self._parse_datetime(meta.get("started"))
            source_created_at_str = started_dt.isoformat() if started_dt else None

            # Extract workspace ID if available (may not be in webhook payload)
            workspace_id = meta.get("workspaceId")

            call_metadata = GongCallMetadata(
                call_id=call_id,
                workspace_id=workspace_id,
                owner_user_id=str(meta.get("primaryUserId")) if meta.get("primaryUserId") else None,
                is_private=bool(meta.get("isPrivate", False)),
                library_folder_ids=[],
                explicit_access_user_ids=[],
                source_created_at=source_created_at_str,
            )

            parties = call_data.get("parties", [])
            call_artifact = GongCallArtifact(
                entity_id=f"gong_call_{call_id}",
                ingest_job_id=UUID(job_id),
                content=GongCallContent(meta_data=meta, parties=parties),
                metadata=call_metadata,
                source_updated_at=self._parse_datetime(meta.get("updated"))
                or self._parse_datetime(meta.get("started"))
                or datetime.now(tz=UTC),
            )

            # Store the artifact
            # Use force_upsert to ensure workspace attribution is always updated when provided
            repository = ArtifactRepository(db_pool)
            await repository.force_upsert_artifact(call_artifact)

            logger.info(
                "Stored Gong call artifact from webhook",
                job_id=job_id,
                call_id=call_id,
                tenant_id=config.tenant_id,
            )

            # Trigger indexing for this call
            await trigger_indexing(
                [call_artifact.entity_id],
                DocumentSource.GONG,
                config.tenant_id,
            )

            logger.info(
                "Triggered indexing for Gong call from webhook",
                job_id=job_id,
                call_id=call_id,
                entity_id=call_artifact.entity_id,
            )

        except Exception as e:
            logger.error(
                "Failed to create artifact for Gong call from webhook",
                job_id=job_id,
                call_id=call_id,
                error=str(e),
            )
            raise

    def _parse_datetime(self, value: str | None) -> datetime | None:
        """Parse ISO datetime string to datetime object."""
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            return None
