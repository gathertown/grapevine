import logging
from typing import Any
from uuid import uuid4

import asyncpg
from pydantic import BaseModel

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.notion.notion_base import NotionExtractor
from connectors.notion.notion_constants import (
    NOTION_PARENT_TYPE_BLOCK_ID,
    NOTION_PARENT_TYPE_PAGE_ID,
)
from connectors.notion.notion_parent_utils import extract_parent_info
from connectors.notion.notion_pruner import notion_pruner

logger = logging.getLogger(__name__)

# See https://developers.notion.com/reference/webhooks-events-delivery for all event types
NOTION_WEBHOOK_EVENT_TYPES_TO_PROCESS = [
    # Page events
    "page.created",
    "page.content_updated",
    "page.moved",
    "page.properties_updated",
    "page.deleted",
    "page.undeleted",
    # page.locked and page.unlocked intentionally ignored
    # Database events
    "database.created",
    "database.content_updated",
    "database.moved",
    "database.deleted",
    "database.undeleted",
    "database.schema_updated",
    # Data source events (newer API version, similar to database events)
    "data_source.created",
    "data_source.content_updated",
    "data_source.moved",
    "data_source.deleted",
    "data_source.undeleted",
    "data_source.schema_updated",
    # Comment events
    "comment.created",
    "comment.updated",
    "comment.deleted",
]

MAX_BLOCK_TRAVERSAL_DEPTH = 100
DATABASE_PAGE_BATCH_SIZE = 50


# See https://developers.notion.com/reference/webhooks-events-delivery
class NotionWebhookBody(BaseModel):
    type: str
    entity: dict[str, Any]
    data: dict[str, Any] | None = None


class NotionWebhookConfig(BaseModel):
    body: NotionWebhookBody
    tenant_id: str


class NotionWebhookExtractor(NotionExtractor[NotionWebhookConfig]):
    source_name = "notion_webhook"

    async def process_job(
        self,
        job_id: str,
        config: NotionWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        event_type = config.body.type
        entity = config.body.entity

        logger.info(f"Processing Notion webhook job for {event_type} with entity {entity}")

        if event_type not in NOTION_WEBHOOK_EVENT_TYPES_TO_PROCESS:
            logger.warning(f"Ignoring Notion webhook event type: {event_type}")
            return

        entity_id = entity.get("id")
        entity_type = entity.get("type")

        # Handle page events
        if entity_type == "page" and entity_id:
            await self._handle_page_event(
                job_id, event_type, entity_id, config.tenant_id, db_pool, trigger_indexing
            )
        # Handle database events
        elif entity_type == "database" and entity_id or entity_type == "data_source" and entity_id:
            await self._handle_database_event(
                job_id, event_type, entity_id, config.tenant_id, db_pool, trigger_indexing
            )
        # Handle comment events
        elif entity_type == "comment" and entity_id:
            comment_data = config.body.data or {}
            await self._handle_comment_event(
                job_id,
                event_type,
                entity_id,
                comment_data,
                config.tenant_id,
                db_pool,
                trigger_indexing,
            )
        else:
            raise ValueError(f"Unsupported Notion entity: {entity_type} {entity_id}")

    async def _handle_page_event(
        self,
        job_id: str,
        event_type: str,
        page_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Handle page-related webhook events."""
        if event_type == "page.deleted":
            logger.info(f"Deleting Notion page {page_id}")
            success = await notion_pruner.delete_page(page_id, tenant_id, db_pool)
            if success:
                logger.info(f"Successfully deleted Notion page {page_id}")
            else:
                raise ValueError(f"Failed to delete page {page_id}")
        else:
            notion_client = await self.get_notion_client(tenant_id)
            page_data = notion_client.get_page(page_id)
            page_artifact = await self.process_page(job_id, page_data, tenant_id)
            logger.info(f"Storing updated Notion page artifact for page {page_id}")
            await self.store_artifact(db_pool, page_artifact)

            logger.info(f"Triggering index job for page {page_id}")
            await trigger_indexing([page_artifact.entity_id], DocumentSource.NOTION, tenant_id)

    async def _handle_database_event(
        self,
        job_id: str,
        event_type: str,
        database_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Handle database-related webhook events."""
        notion_client = await self.get_notion_client(tenant_id)

        if event_type in ["database.deleted", "data_source.deleted"]:
            logger.info(f"Deleting all pages in Notion database {database_id}")
            await self._delete_database_pages(database_id, tenant_id, db_pool)
        elif event_type in ["database.schema_updated", "data_source.schema_updated"]:
            logger.info(
                f"Re-indexing all pages in Notion database {database_id} due to schema update"
            )
            await self._reindex_database_pages(database_id, tenant_id, db_pool, trigger_indexing)
        elif event_type in [
            "database.content_updated",
            "data_source.content_updated",
            "database.undeleted",
            "data_source.undeleted",
        ]:
            logger.info(
                f"Re-indexing all pages in Notion database {database_id} due to {event_type}"
            )
            await self._reindex_database_pages(database_id, tenant_id, db_pool, trigger_indexing)
        else:
            logger.info(f"Processing Notion database {database_id} as a page for {event_type}")
            try:
                page_data = notion_client.get_page(database_id)
                page_artifact = await self.process_page(job_id, page_data, tenant_id)
                logger.info(f"Storing updated Notion database artifact for database {database_id}")
                await self.store_artifact(db_pool, page_artifact)

                logger.info(f"Triggering index job for database {database_id}")
                await trigger_indexing([page_artifact.entity_id], DocumentSource.NOTION, tenant_id)
            except Exception as e:
                logger.warning(
                    f"Failed to process database {database_id} as page (may not be accessible): {e}"
                )
                await self._reindex_database_pages(
                    database_id, tenant_id, db_pool, trigger_indexing
                )

    async def _handle_comment_event(
        self,
        job_id: str,
        event_type: str,
        comment_id: str,
        comment_data: dict[str, Any],
        tenant_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Handle comment-related webhook events."""
        parent = comment_data.get("parent", {})
        page_id: str | None = comment_data.get("page_id")

        if not page_id:
            parent_info = extract_parent_info(parent, comment_id)

            if parent_info.is_page:
                page_id = parent_info.parent_id
            elif parent_info.is_block and parent_info.parent_id:
                notion_client = await self.get_notion_client(tenant_id)
                try:
                    block_data = notion_client.get_block(parent_info.parent_id)
                    block_parent = block_data.get("parent", {})

                    traversal_depth = 0
                    while block_parent and traversal_depth < MAX_BLOCK_TRAVERSAL_DEPTH:
                        traversal_depth += 1
                        if block_parent.get("type") == NOTION_PARENT_TYPE_PAGE_ID:
                            page_id = block_parent.get("page_id")
                            break
                        elif block_parent.get("type") == NOTION_PARENT_TYPE_BLOCK_ID:
                            parent_block_id = block_parent.get("block_id")
                            if parent_block_id:
                                block_data = notion_client.get_block(parent_block_id)
                                block_parent = block_data.get("parent", {})
                            else:
                                break
                        else:
                            break

                    if traversal_depth >= MAX_BLOCK_TRAVERSAL_DEPTH:
                        logger.warning(
                            f"Reached max traversal depth ({MAX_BLOCK_TRAVERSAL_DEPTH}) while finding parent page for block {parent_info.parent_id}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to get block {parent_info.parent_id} for comment: {e}")

        if not page_id:
            logger.warning(
                f"Could not determine parent page for comment event {event_type} on comment {comment_id}, skipping"
            )
            return

        logger.info(
            f"Re-indexing Notion page {page_id} due to comment event {event_type} on comment {comment_id}"
        )

        notion_client = await self.get_notion_client(tenant_id)
        try:
            page_data = notion_client.get_page(page_id)
            page_artifact = await self.process_page(job_id, page_data, tenant_id)
            logger.info(f"Storing updated Notion page artifact for page {page_id}")
            await self.store_artifact(db_pool, page_artifact)

            logger.info(f"Triggering index job for page {page_id}")
            await trigger_indexing([page_artifact.entity_id], DocumentSource.NOTION, tenant_id)
        except Exception as e:
            logger.error(f"Failed to re-index page {page_id} for comment event: {e}")
            raise

    async def _reindex_database_pages(
        self,
        database_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Re-index all pages in a database, processing in batches for efficiency."""
        notion_client = await self.get_notion_client(tenant_id)
        page_ids: list[str] = []

        try:
            for page_summary in notion_client.get_all_pages(database_id=database_id):
                page_ids.append(page_summary["id"])

            if not page_ids:
                logger.info(f"No pages found in database {database_id}")
                return

            total_pages = len(page_ids)
            logger.info(
                f"Found {total_pages} pages in database {database_id}, re-indexing in batches of {DATABASE_PAGE_BATCH_SIZE}"
            )

            total_processed = 0
            for batch_start in range(0, total_pages, DATABASE_PAGE_BATCH_SIZE):
                batch_end = min(batch_start + DATABASE_PAGE_BATCH_SIZE, total_pages)
                batch_page_ids = page_ids[batch_start:batch_end]
                batch_num = (batch_start // DATABASE_PAGE_BATCH_SIZE) + 1
                total_batches = (
                    total_pages + DATABASE_PAGE_BATCH_SIZE - 1
                ) // DATABASE_PAGE_BATCH_SIZE

                logger.info(
                    f"Processing batch {batch_num}/{total_batches} ({len(batch_page_ids)} pages) for database {database_id}"
                )

                entity_ids: list[str] = []
                for page_id in batch_page_ids:
                    try:
                        page_data = notion_client.get_page(page_id)
                        page_artifact = await self.process_page(str(uuid4()), page_data, tenant_id)
                        await self.store_artifact(db_pool, page_artifact)
                        entity_ids.append(page_artifact.entity_id)
                        total_processed += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to process page {page_id} in database {database_id}: {e}"
                        )
                        continue

                if entity_ids:
                    logger.info(
                        f"Triggering index jobs for batch {batch_num}/{total_batches} ({len(entity_ids)} pages) in database {database_id}"
                    )
                    await trigger_indexing(entity_ids, DocumentSource.NOTION, tenant_id)

            logger.info(
                f"Completed re-indexing database {database_id}: processed {total_processed}/{total_pages} pages successfully"
            )

        except Exception as e:
            logger.error(f"Failed to re-index pages in database {database_id}: {e}")
            raise

    async def _delete_database_pages(
        self, database_id: str, tenant_id: str, db_pool: asyncpg.Pool
    ) -> None:
        """Delete all pages in a database, processing in batches for efficiency."""
        notion_client = await self.get_notion_client(tenant_id)
        page_ids: list[str] = []

        try:
            for page_summary in notion_client.get_all_pages(database_id=database_id):
                page_ids.append(page_summary["id"])

            if not page_ids:
                logger.info(f"No pages found in database {database_id}")
                return

            total_pages = len(page_ids)
            logger.info(
                f"Found {total_pages} pages in database {database_id}, deleting in batches of {DATABASE_PAGE_BATCH_SIZE}"
            )

            total_deleted = 0
            for batch_start in range(0, total_pages, DATABASE_PAGE_BATCH_SIZE):
                batch_end = min(batch_start + DATABASE_PAGE_BATCH_SIZE, total_pages)
                batch_page_ids = page_ids[batch_start:batch_end]
                batch_num = (batch_start // DATABASE_PAGE_BATCH_SIZE) + 1
                total_batches = (
                    total_pages + DATABASE_PAGE_BATCH_SIZE - 1
                ) // DATABASE_PAGE_BATCH_SIZE

                logger.info(
                    f"Deleting batch {batch_num}/{total_batches} ({len(batch_page_ids)} pages) for database {database_id}"
                )

                batch_deleted = 0
                for page_id in batch_page_ids:
                    try:
                        success = await notion_pruner.delete_page(page_id, tenant_id, db_pool)
                        if success:
                            batch_deleted += 1
                            total_deleted += 1
                    except Exception as e:
                        logger.warning(
                            f"Failed to delete page {page_id} in database {database_id}: {e}"
                        )

                logger.info(
                    f"Completed batch {batch_num}/{total_batches}: deleted {batch_deleted}/{len(batch_page_ids)} pages"
                )

            logger.info(
                f"Completed deleting database {database_id}: deleted {total_deleted}/{total_pages} pages successfully"
            )

        except Exception as e:
            logger.error(f"Failed to delete pages in database {database_id}: {e}")
            raise
