import logging

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.gmail.gmail_models import GoogleEmailWebhookRefreshConfig
from connectors.gmail.google_email_webhook_handler import webhook_manager

logger = logging.getLogger(__name__)


class GoogleEmailWebhookRefreshExtractor(BaseExtractor[GoogleEmailWebhookRefreshConfig]):
    source_name = "google_email_webhook_refresh"

    def __init__(self):
        super().__init__()

    async def process_job(
        self,
        job_id: str,
        config: GoogleEmailWebhookRefreshConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a Google Email webhook refresh job.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to Google Email webhooks to refresh
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing for entity IDs

        Raises:
            Exception: If processing fails
        """
        try:
            existing_config, email_client = await webhook_manager.get_tenant_webhook_setup(
                config.tenant_id, db_pool
            )
            if not existing_config or not email_client:
                logger.error(f"No config or email client found for tenant {config.tenant_id}")
                return

            for identifier in existing_config["users"]:
                if "topic_name" not in existing_config["users"][identifier]:
                    logger.error(f"No topic name found for user {identifier}")
                    continue
                user_email_client = await email_client.impersonate_user(identifier)
                try:
                    update_result = await webhook_manager.check_tenant_user_webhook_expiration(
                        user_email_client,
                        config.tenant_id,
                        identifier,
                        existing_config["users"][identifier]["topic_name"],
                        db_pool,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to check tenant user webhook expiration for user {identifier}: {e}"
                    )
                    continue
                if update_result:
                    logger.info(f"Updated google email webhook for user {identifier}")

        except Exception as e:
            logger.error(f"Failed to process Google Email webhook refresh job {job_id}: {e}")
            raise
