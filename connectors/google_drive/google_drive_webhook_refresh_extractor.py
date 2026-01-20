import logging

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.google_drive.google_drive_models import GoogleDriveWebhookRefreshConfig
from connectors.google_drive.google_drive_webhook_handler import webhook_manager

logger = logging.getLogger(__name__)


class GoogleDriveWebhookRefreshExtractor(BaseExtractor[GoogleDriveWebhookRefreshConfig]):
    source_name = "google_drive_webhook_refresh"

    def __init__(self):
        super().__init__()

    async def process_job(
        self,
        job_id: str,
        config: GoogleDriveWebhookRefreshConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a Google Drive webhook refresh job.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to Google Drive webhooks to refresh
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing for entity IDs

        Raises:
            Exception: If processing fails
        """
        try:
            tenant_id = config.tenant_id
            await webhook_manager.refresh_expiring_tenant_webhooks(tenant_id)

        except Exception as e:
            logger.error(f"Failed to process Google Drive webhook refresh job {job_id}: {e}")
            raise
