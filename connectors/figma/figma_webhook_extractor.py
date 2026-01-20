"""Figma webhook extractor for processing real-time webhook events."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.figma.client import get_figma_client_for_tenant
from connectors.figma.figma_models import FigmaCommentArtifact, FigmaFileArtifact
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


class FigmaWebhookConfig(BaseModel):
    """Configuration for Figma webhook processing."""

    body: dict[str, Any]
    tenant_id: str


class FigmaWebhookExtractor(BaseExtractor[FigmaWebhookConfig]):
    """Extractor for processing Figma webhook events.

    Handles FILE_UPDATE, FILE_DELETE, and FILE_COMMENT events.
    """

    source_name = "figma_webhook"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: FigmaWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process a Figma webhook event.

        Figma webhook payload structure:
        {
            "event_type": "FILE_UPDATE" | "FILE_DELETE" | "FILE_COMMENT" | "LIBRARY_PUBLISH",
            "passcode": "...",
            "timestamp": "...",
            "webhook_id": "...",
            "file_key": "...",
            "file_name": "...",
            "team_id": "...",
            ...event-specific fields
        }
        """
        payload = config.body
        tenant_id = config.tenant_id

        event_type = payload.get("event_type", "")
        file_key = payload.get("file_key", "")
        webhook_id = payload.get("webhook_id", "unknown")

        logger.info(
            f"Processing Figma webhook: {event_type}",
            tenant_id=tenant_id,
            webhook_id=webhook_id,
            file_key=file_key,
            event_type=event_type,
        )

        if event_type == "FILE_UPDATE":
            await self._handle_file_update(
                file_key=file_key,
                payload=payload,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )
        elif event_type == "FILE_DELETE":
            await self._handle_file_delete(
                file_key=file_key,
                tenant_id=tenant_id,
                db_pool=db_pool,
            )
        elif event_type == "FILE_COMMENT":
            await self._handle_file_comment(
                file_key=file_key,
                payload=payload,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )
        elif event_type == "LIBRARY_PUBLISH":
            # Library publish events - refresh the file to get updated components
            await self._handle_file_update(
                file_key=file_key,
                payload=payload,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )
        else:
            logger.info(
                f"Unhandled Figma event type: {event_type}",
                tenant_id=tenant_id,
                webhook_id=webhook_id,
            )

    async def _handle_file_update(
        self,
        file_key: str,
        payload: dict[str, Any],
        job_id: str,
        config: FigmaWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Handle FILE_UPDATE event - fetch and update the file artifact."""
        tenant_id = config.tenant_id

        if not file_key:
            logger.warning("FILE_UPDATE event missing file_key")
            return

        try:
            async with await get_figma_client_for_tenant(tenant_id) as client:
                # Fetch the full file data
                file_response = await client.get_file(file_key)
                # Convert Pydantic model to dict for artifact creation
                file_data = file_response.model_dump(by_alias=True)
        except Exception as e:
            logger.error(
                f"Failed to fetch Figma file {file_key}: {e}",
                tenant_id=tenant_id,
                file_key=file_key,
            )
            return

        # Create artifact from file data
        ingest_job_id = UUID(job_id)
        artifact = FigmaFileArtifact.from_api_response(
            file_key=file_key,
            file_data=file_data,
            ingest_job_id=ingest_job_id,
            project_id=payload.get("project_id"),
            team_id=payload.get("team_id"),
        )

        # Override source_updated_at with current time (we know it was just updated)
        artifact.source_updated_at = datetime.now(UTC)

        # Store the artifact
        await self.force_store_artifacts_batch(db_pool, [artifact])

        # Trigger indexing
        await trigger_indexing(
            [artifact.entity_id],
            DocumentSource.FIGMA_FILE,
            tenant_id,
        )

        logger.info(
            f"Processed Figma file update: {file_key}",
            tenant_id=tenant_id,
            entity_id=artifact.entity_id,
        )

    async def _handle_file_delete(
        self,
        file_key: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> None:
        """Handle FILE_DELETE event - delete the file from the index."""
        from connectors.figma.figma_pruner import figma_pruner

        if not file_key:
            logger.warning("FILE_DELETE event missing file_key")
            return

        logger.info(
            f"Deleting Figma file via pruner: {file_key}",
            tenant_id=tenant_id,
            file_key=file_key,
        )

        success = await figma_pruner.delete_file(file_key, tenant_id, db_pool)

        if success:
            logger.info(
                f"Successfully deleted Figma file: {file_key}",
                tenant_id=tenant_id,
            )
        else:
            logger.warning(
                f"Failed to delete Figma file: {file_key}",
                tenant_id=tenant_id,
            )

    async def _handle_file_comment(
        self,
        file_key: str,
        payload: dict[str, Any],
        job_id: str,
        config: FigmaWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Handle FILE_COMMENT event - process comment updates.

        FILE_COMMENT events include a 'comments' array with the comment data.
        """
        tenant_id = config.tenant_id

        if not file_key:
            logger.warning("FILE_COMMENT event missing file_key")
            return

        comments = payload.get("comments", [])
        if not comments:
            logger.warning(
                "FILE_COMMENT event has no comments",
                tenant_id=tenant_id,
                file_key=file_key,
            )
            return

        file_name = payload.get("file_name", "Unknown File")
        ingest_job_id = UUID(job_id)
        artifacts: list[FigmaCommentArtifact] = []
        entity_ids: list[str] = []

        for comment_data in comments:
            # Add file_key to comment data for artifact creation
            comment_data["file_key"] = file_key

            # Note: Webhook payload doesn't include editor_type, so we pass None
            # The citation resolver will default to 'design' URL format
            artifact = FigmaCommentArtifact.from_api_response(
                comment_data=comment_data,
                file_name=file_name,
                ingest_job_id=ingest_job_id,
                editor_type=None,
            )

            # Override source_updated_at with current time
            artifact.source_updated_at = datetime.now(UTC)

            artifacts.append(artifact)
            entity_ids.append(artifact.entity_id)

        if artifacts:
            # Store artifacts
            await self.force_store_artifacts_batch(db_pool, artifacts)

            # Trigger indexing
            await trigger_indexing(
                entity_ids,
                DocumentSource.FIGMA_COMMENT,
                tenant_id,
            )

            logger.info(
                f"Processed {len(artifacts)} Figma comment(s) for file {file_key}",
                tenant_id=tenant_id,
                file_key=file_key,
            )
