import logging

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.notion.notion_base import NotionExtractor
from connectors.notion.notion_models import NotionUserRefreshConfig

logger = logging.getLogger(__name__)


class NotionUserRefreshExtractor(NotionExtractor[NotionUserRefreshConfig]):
    source_name = "notion_user_refresh"

    async def process_job(
        self,
        job_id: str,
        config: NotionUserRefreshConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process a job that only refreshes Notion users (no pages)."""
        try:
            await self.collect_notion_users(db_pool, job_id, config.tenant_id)

            # TODO - we do not trigger any index job here yet, even though theoretically documents could've changed
            # as a result of this user refresh.
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            raise
