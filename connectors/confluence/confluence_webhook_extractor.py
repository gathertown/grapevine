"""
Confluence webhook extractor for processing real-time webhook events.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import asyncpg

from connectors.base import TriggerIndexingCallback, get_confluence_space_entity_id
from connectors.base.document_source import DocumentSource
from connectors.confluence.confluence_artifacts import (
    ConfluencePageArtifact,
    ConfluenceSpaceArtifact,
    ConfluenceSpaceArtifactContent,
    ConfluenceSpaceArtifactMetadata,
)
from connectors.confluence.confluence_base import ConfluenceExtractor
from connectors.confluence.confluence_models import ConfluenceWebhookConfig
from connectors.confluence.confluence_pruner import confluence_pruner
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


class ConfluenceWebhookExtractor(ConfluenceExtractor[ConfluenceWebhookConfig]):
    """Extractor for processing Confluence webhook events."""

    source_name = "confluence_webhook"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__(ssm_client, sqs_client)

    async def process_job(
        self,
        job_id: str,
        config: ConfluenceWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process Confluence webhook event."""
        logger.info(f"Processing Confluence webhook event for tenant {config.tenant_id}")

        try:
            webhook_body = config.body
            event_type = webhook_body.get("eventType")

            logger.debug(f"Processing Confluence webhook event: {event_type}")

            if not event_type:
                logger.warning("No eventType found in Confluence webhook body")
                return

            # Extract page/space information based on event type
            artifacts: list[ConfluencePageArtifact | ConfluenceSpaceArtifact] = []

            if event_type in [
                "avi:confluence:created:page",
                "avi:confluence:updated:page",
                "avi:confluence:restored:page",
                "avi:confluence:permissions_updated:page",
                "avi:confluence:trashed:page",
                "avi:confluence:deleted:page",
            ]:
                artifacts.extend(
                    await self._process_page_event(webhook_body, config.tenant_id, db_pool)
                )
            elif event_type in [
                "avi:confluence:created:space",
                "avi:confluence:updated:space",
            ]:
                artifacts.extend(
                    await self._process_space_event(webhook_body, config.tenant_id, db_pool)
                )
            else:
                logger.info(f"Ignoring unsupported Confluence webhook event: {event_type}")
                return

            # Store artifacts if any were created
            if artifacts:
                logger.info(f"Storing {len(artifacts)} Confluence artifacts from webhook")
                await self.store_artifacts_batch(db_pool, artifacts)

                # Trigger indexing for pages (spaces are not indexed directly)
                page_entity_ids = [
                    artifact.entity_id
                    for artifact in artifacts
                    if isinstance(artifact, ConfluencePageArtifact)
                ]

                if page_entity_ids:
                    await trigger_indexing(
                        page_entity_ids,
                        DocumentSource.CONFLUENCE,
                        config.tenant_id,
                    )
                    logger.info(f"Triggered indexing for {len(page_entity_ids)} Confluence pages")

                # Log space artifacts (they're stored but not indexed directly)
                space_count = len([a for a in artifacts if isinstance(a, ConfluenceSpaceArtifact)])
                if space_count > 0:
                    logger.info(f"Stored {space_count} Confluence space artifacts")

            logger.info(f"Successfully processed Confluence webhook event: {event_type}")

        except Exception as e:
            logger.error(f"Failed to process Confluence webhook: {e}")
            logger.debug(f"Webhook body: {json.dumps(config.body, indent=2)}")
            raise

    async def _process_page_event(
        self, webhook_body: dict[str, Any], tenant_id: str, db_pool: asyncpg.Pool
    ) -> list[ConfluencePageArtifact]:
        """Process page-related webhook events."""
        try:
            event_type = webhook_body.get("eventType")
            page_info = webhook_body.get("content", {})

            if not page_info:
                logger.warning(f"No page information found in {event_type} webhook")
                return []

            page_id = page_info.get("id")
            if not page_id:
                logger.warning(f"No page ID found in {event_type} webhook")
                return []

            # For delete/trash events, we might not be able to fetch the page details
            if event_type in ["avi:confluence:deleted:page", "avi:confluence:trashed:page"]:
                # Handle page deletion/trashing - remove from all data stores
                action = "deleted" if event_type == "avi:confluence:deleted:page" else "trashed"
                logger.info(f"Page {page_id} was {action}, removing from all data stores")

                # Use the confluence pruner to delete the page from all data stores
                success = await confluence_pruner.delete_page(page_id, tenant_id, db_pool)
                if success:
                    logger.info(f"Successfully deleted Confluence page {page_id}")
                else:
                    logger.error(f"Failed to delete Confluence page {page_id}")

                return []

            # Fetch current page details from API
            confluence_client = await self.get_confluence_client(tenant_id)
            page_data = confluence_client.get_page(page_id)

            if not page_data:
                logger.warning(f"Could not fetch page {page_id} from Confluence API")
                return []

            # Load space info from page data or webhook
            space_id = None
            if page_data:
                space_data = page_data.get("space", {})
                if space_data and space_data.get("id"):
                    space_id = space_data["id"]

            # Fallback to webhook space info
            if not space_id:
                webhook_space = page_info.get("space", {})
                if webhook_space and webhook_space.get("id"):
                    space_id = webhook_space["id"]

            if space_id:
                await self._load_space_info(space_id, tenant_id)

            # Process the page and create artifacts
            return await self._process_page("webhook", page_data, tenant_id)

        except Exception as e:
            logger.error(f"Failed to process page event: {e}")
            return []

    async def _process_space_event(
        self, webhook_body: dict[str, Any], tenant_id: str, db_pool: asyncpg.Pool
    ) -> list[ConfluenceSpaceArtifact]:
        """Process space-related webhook events."""
        try:
            event_type = webhook_body.get("eventType")
            space_info = webhook_body.get("content", {})

            if not space_info:
                logger.warning(f"No space information found in {event_type} webhook")
                return []

            space_id = space_info.get("id")
            if not space_id:
                logger.warning(f"No space ID found in {event_type} webhook")
                return []

            # For delete events, we might not be able to fetch the space details
            if event_type == "avi:confluence:deleted:space":
                # Handle space deletion - remove from all data stores (cascading)
                logger.info(f"Space {space_id} was deleted, removing from all data stores")

                # Use the confluence pruner to delete the space and all its pages
                success = await confluence_pruner.delete_space(space_id, tenant_id, db_pool)
                if success:
                    logger.info(f"Successfully deleted Confluence space {space_id}")
                else:
                    logger.error(f"Failed to delete Confluence space {space_id}")

                return []

            # Fetch current space details from API
            confluence_client = await self.get_confluence_client(tenant_id)
            space_data = confluence_client.get_space(space_id)

            if not space_data:
                logger.warning(f"Could not fetch space {space_id} from Confluence API")
                return []

            # Create space artifact following the same pattern as the root backfill extractor
            try:
                site_domain = await confluence_client.get_site_domain(tenant_id)

                space_artifact = ConfluenceSpaceArtifact(
                    entity_id=get_confluence_space_entity_id(space_id=space_id),
                    ingest_job_id=uuid4(),
                    content=ConfluenceSpaceArtifactContent(space_data=space_data),
                    metadata=ConfluenceSpaceArtifactMetadata(
                        space_id=space_data.get("id", space_id),
                        space_key=space_data.get("key", ""),
                        space_name=space_data.get("name", ""),
                        space_type=space_data.get("type"),
                        site_domain=site_domain,
                    ),
                    source_updated_at=datetime.now(UTC),
                )

                logger.info(
                    f"Created space artifact for {space_data.get('name')} "
                    f"({space_data.get('key')}) from {event_type}"
                )
                return [space_artifact]

            except Exception as e:
                logger.error(f"Failed to create space artifact for {space_id}: {e}")
                return []

        except Exception as e:
            logger.error(f"Failed to process space event: {e}")
            return []
