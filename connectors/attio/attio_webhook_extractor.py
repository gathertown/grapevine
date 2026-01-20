"""Attio webhook extractor for processing real-time webhook events."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from connectors.attio.attio_artifacts import (
    AttioCompanyArtifact,
    AttioDealArtifact,
    AttioObjectType,
    AttioPersonArtifact,
    AttioWebhookAction,
    AttioWebhookEntityType,
)
from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from src.clients.attio import get_attio_client_for_tenant
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AttioWebhookConfig(BaseModel):
    """Configuration for Attio webhook processing."""

    body: dict[str, Any]
    tenant_id: str


class AttioWebhookExtractor(BaseExtractor[AttioWebhookConfig]):
    """Extractor for processing Attio webhook events.

    Handles record.created, record.updated, record.deleted events
    for companies, people, and deals.

    Note: note.* and task.* events are received but not currently processed
    since we don't have separate document types for them.
    """

    source_name = "attio_webhook"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: AttioWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process an Attio webhook event.

        Attio webhooks have a wrapper structure:
        {
            "webhook_id": "...",
            "events": [
                {"event_type": "record.updated", "id": {...}, "actor": {...}},
                ...
            ]
        }

        Events are deduplicated by (object_id, record_id) to avoid processing
        the same record multiple times in a single webhook delivery.
        """
        payload = config.body
        tenant_id = config.tenant_id

        # Extract events from the wrapper structure
        events = payload.get("events", [])
        webhook_id = payload.get("webhook_id", "unknown")

        if not events:
            logger.warning(
                "Attio webhook has no events",
                webhook_id=webhook_id,
                payload_keys=list(payload.keys()) if payload else [],
            )
            return

        # Dedupe events by (object_id, record_id), keeping the last event for each record
        # This handles cases where multiple updates to the same record are batched together
        deduped_events: dict[tuple[str, str], dict[str, Any]] = {}
        for event in events:
            event_type = event.get("event_type", "")
            # Only dedupe record events
            if event_type.startswith("record."):
                id_obj = event.get("id", {})
                object_id = id_obj.get("object_id", "")
                record_id = id_obj.get("record_id", "")
                if object_id and record_id:
                    key = (object_id, record_id)
                    # Prefer delete events over other events for the same record
                    existing = deduped_events.get(key)
                    if (
                        existing is None
                        or event_type == "record.deleted"
                        or existing.get("event_type") != "record.deleted"
                    ):
                        deduped_events[key] = event
                else:
                    # Can't dedupe without object_id and record_id, process as-is
                    deduped_events[(event_type, str(id(event)))] = event
            else:
                # Non-record events (note.*, task.*) are processed as-is
                deduped_events[(event_type, str(id(event)))] = event

        deduped_list = list(deduped_events.values())
        original_count = len(events)
        deduped_count = len(deduped_list)

        logger.info(
            f"Processing Attio webhook with {deduped_count} event(s) (deduped from {original_count})",
            tenant_id=tenant_id,
            webhook_id=webhook_id,
            original_event_count=original_count,
            deduped_event_count=deduped_count,
        )

        # Process each unique event
        for event in deduped_list:
            await self._process_single_event(
                event=event,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )

    async def _process_single_event(
        self,
        event: dict[str, Any],
        job_id: str,
        config: AttioWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process a single event from an Attio webhook."""
        event_type = event.get("event_type", "")
        tenant_id = config.tenant_id

        logger.info(
            f"Processing Attio event: {event_type}",
            tenant_id=tenant_id,
            event_type=event_type,
        )

        # Parse event type (e.g., "record.updated", "note.created")
        parts = event_type.split(".")
        if len(parts) != 2:
            logger.warning(
                f"Unknown Attio event type format: '{event_type}'",
                event_keys=list(event.keys()) if event else [],
            )
            return

        entity_type_str, action_str = parts

        # Validate entity type
        try:
            entity_type = AttioWebhookEntityType(entity_type_str)
        except ValueError:
            logger.info(f"Unhandled Attio entity type: {entity_type_str}")
            return

        # Handle record events (companies, people, deals)
        if entity_type == AttioWebhookEntityType.RECORD:
            await self._handle_record_event(
                action=action_str,
                event=event,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )
        elif entity_type == AttioWebhookEntityType.NOTE:
            # Notes are attached to records - we could refresh the parent record
            # For now, just log
            logger.info(f"Received note.{action_str} event - not processing separately")
        elif entity_type == AttioWebhookEntityType.TASK:
            # Tasks are attached to records - we could refresh the parent record
            # For now, just log
            logger.info(f"Received task.{action_str} event - not processing separately")

    async def _handle_record_event(
        self,
        action: str,
        event: dict[str, Any],
        job_id: str,
        config: AttioWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Handle record.created, record.updated, record.deleted events."""
        tenant_id = config.tenant_id

        # Each event has `id` containing the identifiers
        # Structure: { "event_type": "record.created", "id": { "object_id": "...", "record_id": "..." }, ... }
        record_id_obj = event.get("id", {})

        object_id = record_id_obj.get("object_id")  # e.g., "companies", "people", "deals"
        record_id = record_id_obj.get("record_id")

        if not object_id or not record_id:
            logger.warning(
                "Attio webhook event missing object_id or record_id",
                event_keys=list(event.keys()) if event else [],
                id_obj=record_id_obj,
            )
            return

        # Validate action
        try:
            webhook_action = AttioWebhookAction(action)
        except ValueError:
            logger.warning(f"Unknown record action: {action}")
            return

        logger.info(
            f"Handling record.{webhook_action.value} for {object_id}/{record_id}",
            tenant_id=tenant_id,
            object_id=object_id,
            record_id=record_id,
        )

        if webhook_action == AttioWebhookAction.DELETED:
            # For deletes, we need to resolve the object slug to construct the correct entity_id
            # Try to resolve, but if it fails, use the object_id as-is
            object_slug: str | None = None
            try:
                attio_client = await get_attio_client_for_tenant(tenant_id, self.ssm_client)
                attio_object = attio_client.get_object(object_id)
                object_slug = attio_object.api_slug
            except Exception as e:
                logger.warning(
                    f"Failed to resolve object {object_id} for delete, using as-is: {e}",
                    tenant_id=tenant_id,
                )

            await self._handle_record_deleted(
                object_id=object_id,
                record_id=record_id,
                tenant_id=tenant_id,
                db_pool=db_pool,
                object_slug=object_slug,
            )
        elif webhook_action in (AttioWebhookAction.CREATED, AttioWebhookAction.UPDATED):
            # Fetch the full record and update
            await self._handle_record_upsert(
                object_id=object_id,
                record_id=record_id,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )

    async def _handle_record_upsert(
        self,
        object_id: str,
        record_id: str,
        job_id: str,
        config: AttioWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Handle record created or updated - fetch full record and store."""
        tenant_id = config.tenant_id

        try:
            attio_client = await get_attio_client_for_tenant(tenant_id, self.ssm_client)
        except Exception as e:
            logger.error(f"Failed to get Attio client for tenant {tenant_id}: {e}")
            return

        # Resolve object_id to api_slug (webhooks may send UUIDs instead of slugs)
        # Standard objects use slugs like "companies", custom objects use UUIDs
        object_slug = object_id
        try:
            attio_object = attio_client.get_object(object_id)
            object_slug = attio_object.api_slug
            if object_slug != object_id:
                logger.debug(
                    f"Resolved object UUID {object_id} to slug {object_slug}",
                    tenant_id=tenant_id,
                )
        except Exception as e:
            # If we can't resolve, try using the original object_id as the slug
            logger.warning(
                f"Failed to resolve object {object_id}, using as-is: {e}",
                tenant_id=tenant_id,
            )

        try:
            # Fetch the full record from Attio API using the resolved slug
            record = attio_client.get_record(object_slug=object_slug, record_id=record_id)
        except Exception as e:
            logger.error(
                f"Failed to fetch record {object_slug}/{record_id}: {e}",
                tenant_id=tenant_id,
            )
            return

        # Convert to artifact based on object type (using resolved slug)
        artifact: AttioCompanyArtifact | AttioPersonArtifact | AttioDealArtifact | None = None
        document_source: DocumentSource | None = None
        ingest_job_id = UUID(job_id)

        if object_slug == AttioObjectType.COMPANIES.value:
            artifact = AttioCompanyArtifact.from_api_response(
                record_data=record,
                ingest_job_id=ingest_job_id,
            )
            document_source = DocumentSource.ATTIO_COMPANY
        elif object_slug == AttioObjectType.PEOPLE.value:
            artifact = AttioPersonArtifact.from_api_response(
                record_data=record,
                ingest_job_id=ingest_job_id,
            )
            document_source = DocumentSource.ATTIO_PERSON
        elif object_slug == AttioObjectType.DEALS.value:
            # Fetch notes and tasks for deals to maintain consistency with backfill
            notes: list[dict[str, Any]] = []
            tasks: list[dict[str, Any]] = []

            try:
                notes = attio_client.get_notes_for_record(
                    object_slug=AttioObjectType.DEALS.value,
                    record_id=record_id,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to fetch notes for deal {record_id}: {e}",
                    tenant_id=tenant_id,
                    record_id=record_id,
                )

            try:
                tasks = attio_client.get_tasks_for_record(
                    object_slug=AttioObjectType.DEALS.value,
                    record_id=record_id,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to fetch tasks for deal {record_id}: {e}",
                    tenant_id=tenant_id,
                    record_id=record_id,
                )

            artifact = AttioDealArtifact.from_api_response(
                record_data=record,
                ingest_job_id=ingest_job_id,
                notes=notes,
                tasks=tasks,
            )
            document_source = DocumentSource.ATTIO_DEAL
        else:
            logger.info(f"Unhandled Attio object type: {object_slug}")
            return

        if artifact is not None and document_source is not None:
            # Override source_updated_at with current time for webhook events.
            # Attio's API doesn't reliably return an updated_at timestamp, but we know
            # the record was just created/updated because we received a webhook event.
            artifact.source_updated_at = datetime.now(UTC)

            # Store the artifact (force update to bypass timestamp comparison)
            await self.force_store_artifacts_batch(db_pool, [artifact])

            # Trigger indexing
            await trigger_indexing(
                [artifact.entity_id],
                document_source,
                tenant_id,
            )

            logger.info(
                f"Processed Attio {object_slug} record {record_id}",
                tenant_id=tenant_id,
                entity_id=artifact.entity_id,
            )

    async def _handle_record_deleted(
        self,
        object_id: str,
        record_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        object_slug: str | None = None,
    ) -> None:
        """Handle record deleted - delete document from all storage systems.

        Uses the AttioPruner to handle the complete deletion flow across
        PostgreSQL, OpenSearch, and Turbopuffer.

        Args:
            object_id: Original object ID from webhook (may be UUID)
            record_id: Record ID
            tenant_id: Tenant ID
            db_pool: Database connection pool
            object_slug: Resolved object slug (if already resolved)
        """
        from connectors.attio.attio_pruner import attio_pruner

        # Use provided slug or fall back to object_id
        slug = object_slug or object_id

        logger.info(
            f"Deleting Attio record via pruner: {slug}/{record_id}",
            tenant_id=tenant_id,
            object_slug=slug,
            record_id=record_id,
        )

        # Use the appropriate pruner method based on object type
        # Attio slugs are plural ("companies", "people", "deals")
        success = False
        if slug == AttioObjectType.COMPANIES.value:
            success = await attio_pruner.delete_company(record_id, tenant_id, db_pool)
        elif slug == AttioObjectType.PEOPLE.value:
            success = await attio_pruner.delete_person(record_id, tenant_id, db_pool)
        elif slug == AttioObjectType.DEALS.value:
            success = await attio_pruner.delete_deal(record_id, tenant_id, db_pool)
        else:
            logger.warning(f"Unhandled Attio object type for deletion: {slug}")
            return

        if success:
            logger.info(
                f"Successfully deleted Attio {slug} record: {record_id}",
                tenant_id=tenant_id,
            )
        else:
            logger.warning(
                f"Failed to delete Attio {slug} record: {record_id}",
                tenant_id=tenant_id,
            )
