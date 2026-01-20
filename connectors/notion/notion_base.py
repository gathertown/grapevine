"""
Base extractor class for Notion-based extractors.
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
    get_notion_page_entity_id,
    get_notion_user_entity_id,
)
from connectors.notion.notion_artifacts import (
    NotionPageArtifact,
    NotionPageArtifactContent,
    NotionPageArtifactMetadata,
    NotionUserArtifact,
    NotionUserArtifactContent,
    NotionUserArtifactMetadata,
)
from connectors.notion.notion_models import NotionApiBackfillConfig
from src.clients.notion import NotionClient
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


NotionConfigType = TypeVar("NotionConfigType", bound=BaseModel)


class NotionExtractor(BaseExtractor[NotionConfigType], ABC):
    """Abstract base class for Notion-based extractors."""

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        self._notion_clients: dict[str, NotionClient] = {}

    async def get_notion_client(self, tenant_id: str) -> NotionClient:
        """Get NotionClient for the specified tenant."""
        if tenant_id not in self._notion_clients:
            token = await self.ssm_client.get_notion_token(tenant_id)
            if not token:
                raise ValueError(f"No Notion token configured for tenant {tenant_id}")
            self._notion_clients[tenant_id] = NotionClient(token)
        return self._notion_clients[tenant_id]

    @abstractmethod
    async def process_job(
        self,
        job_id: str,
        config: NotionConfigType,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process an ingest job - must be implemented by subclasses."""
        pass

    async def process_page(
        self, job_id: str, page_data: dict[str, Any], tenant_id: str
    ) -> NotionPageArtifact:
        """
        Process a Notion page into a NotionPageArtifact.

        Args:
            job_id: The ingest job ID
            page_data: Raw, fresh page data from Notion API. This should have been freshly pulled from API.

        Returns:
            NotionPageArtifact or raises an exception if processing fails
        """
        page_id = page_data.get("id")
        assert isinstance(page_id, str), "page_data['id'] must be a string"

        notion_client = await self.get_notion_client(tenant_id)
        blocks_data = notion_client.get_page_content(page_id)

        # Fetch comments for the page and all blocks
        # Note: This requires "Read comments" permission in the Notion integration
        comments_data = []

        # Try to fetch page-level comments
        try:
            comments_data = notion_client.get_all_comments(page_id)
        except Exception as e:
            # Integration may not have "Read comments" permission - continue without comments
            logger.debug(
                f"Could not fetch comments for page {page_id}, integration may not have comment access: {e}"
            )

        # Try to fetch block-level comments (best effort - continue even if some blocks fail)
        for block in blocks_data:
            block_id = block.get("id")
            if block_id:
                try:
                    block_comments = notion_client.get_all_comments(block_id)
                    comments_data.extend(block_comments)
                except Exception as e:
                    # Log but continue - we don't want one failing block to stop all comment fetching
                    logger.debug(
                        f"Could not fetch comments for block {block_id} on page {page_id}: {e}"
                    )

        page_title = self._extract_page_title(page_data)
        parent = page_data.get("parent", {})
        db_id = parent.get("database_id") if parent.get("type") == "database_id" else None

        artifact = NotionPageArtifact(
            entity_id=get_notion_page_entity_id(page_id=page_id),
            ingest_job_id=UUID(job_id),
            content=NotionPageArtifactContent(
                page_data=page_data, blocks=blocks_data, comments=comments_data
            ),
            metadata=NotionPageArtifactMetadata(
                page_id=page_id,
                page_title=page_title,
                database_id=db_id,
            ),
            # We always pull Notion pages fresh from the API regardless of backfill vs webhook,
            # so we can set source_updated_at to now() since we can assume we just pulled this from API
            source_updated_at=datetime.now(tz=UTC),
        )

        return artifact

    async def collect_notion_users(
        self, db_pool: asyncpg.Pool, job_id: str, tenant_id: str
    ) -> None:
        """
        Collect all Notion users and store them as artifacts.

        Args:
            db_pool: Database connection pool
            job_id: The ingest job ID
        """
        try:
            notion_client = await self.get_notion_client(tenant_id)
            users = notion_client.get_all_users()

            artifacts: list[BaseIngestArtifact] = []

            for user_data in users:
                user_id = user_data.get("id")

                if not user_id:
                    continue

                artifacts.append(
                    NotionUserArtifact(
                        entity_id=get_notion_user_entity_id(user_id=user_id),
                        ingest_job_id=UUID(job_id),
                        content=NotionUserArtifactContent(**user_data),
                        metadata=NotionUserArtifactMetadata(
                            user_id=user_id, user_name=user_data.get("name", "")
                        ),
                        # We just pulled all this data fresh from the API
                        source_updated_at=datetime.now(tz=UTC),
                    )
                )

            await self.store_artifacts_batch(db_pool, artifacts)

        except Exception as e:
            logger.error(f"Failed to collect notion_users: {e}")
            raise

    def _extract_page_title(self, page_data: dict[str, Any]) -> str:
        properties = page_data.get("properties", {})

        for _, prop_data in properties.items():
            if prop_data.get("type") == "title":
                title_array = prop_data.get("title", [])
                if title_array:
                    title_parts = []
                    for text_obj in title_array:
                        if text_obj.get("type") == "text":
                            title_parts.append(text_obj.get("text", {}).get("content", ""))
                    return "".join(title_parts) if title_parts else "Untitled"

        return page_data.get("object", "Untitled Page")

    async def send_backfill_child_job_message(
        self,
        config: NotionApiBackfillConfig,
        delay_timestamp: datetime | None = None,
        description: str = "job",
    ) -> None:
        """
        Send a Notion backfill job message with optional delay.

        Args:
            config: The backfill job configuration to send
            delay_timestamp: Optional timestamp when the job should start (for rate limiting)
            description: Description for logging (e.g., "child job batch 0", "re-queued job")
        """
        try:
            await self.sqs_client.send_backfill_ingest_message(
                backfill_config=config,
            )

            # Log the message sending
            log_message = f"Sent {description} for tenant {config.tenant_id} with {len(config.page_ids)} pages"
            if delay_timestamp:
                log_message += f". Was scheduled to start at {delay_timestamp.isoformat()}"
            logger.info(log_message)

        except Exception as e:
            logger.error(f"Failed to send {description}: {e}")
            raise
