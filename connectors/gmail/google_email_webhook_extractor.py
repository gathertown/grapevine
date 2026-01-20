import base64
import json
import logging
from typing import Any

import asyncpg
from pydantic import BaseModel

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.gmail.google_email_user_extractor import create_email_artifact
from connectors.gmail.google_email_webhook_handler import webhook_manager
from src.clients.google_email import GoogleEmailClient
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE

logger = logging.getLogger(__name__)


class GoogleEmailWebhookConfig(BaseModel):
    body: dict[str, Any]
    headers: dict[str, str]
    tenant_id: str


class GoogleEmailWebhookExtractor(BaseExtractor[GoogleEmailWebhookConfig]):
    source_name = "google_email_webhook"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: GoogleEmailWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a Google Email webhook ingest job.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to Google Email webhooks
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing for entity IDs

        Raises:
            Exception: If processing fails
        """
        try:
            tenant_id = config.tenant_id

            admin_email = await self.ssm_client.get_google_email_admin_email(config.tenant_id)
            if not admin_email:
                raise ValueError(f"No admin email found for tenant {config.tenant_id}")

            admin_email_client = GoogleEmailClient(
                tenant_id=config.tenant_id,
                admin_email=admin_email,
                ssm_client=self.ssm_client,
            )

            logger.info(f"Processing Google Email webhook job {job_id} for tenant {tenant_id}")
            body_data = json.loads(base64.b64decode(config.body["message"]["data"]).decode("utf-8"))
            user_email = body_data["emailAddress"]
            new_history_id = body_data["historyId"]

            webhook_config = await webhook_manager.get_webhook_user_config(
                db_pool, tenant_id, user_email
            )
            if not webhook_config:
                logger.warning(
                    f"No webhook config found for tenant {tenant_id} and user {user_email}"
                )
                return

            webhook_config = json.loads(webhook_config)
            start_history_id = webhook_config["history_id"]

            if new_history_id == start_history_id:
                logger.info(f"No new emails found for {user_email}")
                return

            # Update the webhook config with the new history id
            await webhook_manager.update_webhook_user_config(
                db_pool,
                tenant_id,
                user_email,
                {"history_id": new_history_id, "expiration": webhook_config["expiration"]},
            )

            email_client = GoogleEmailClient(
                tenant_id=config.tenant_id,
                admin_email=user_email,
                ssm_client=self.ssm_client,
            )

            new_message_ids = await email_client.get_new_emails(
                user_id="me", start_history_id=start_history_id
            )

            if new_message_ids:
                user_info = await admin_email_client.get_user_info_by_email(user_email)
                if not user_info:
                    logger.warning(f"No user info found for {user_email}")
                    return
                user_id = user_info["id"]
                await self._process_new_emails(
                    email_client,
                    user_id,
                    new_message_ids,
                    job_id,
                    user_email,
                    db_pool,
                    trigger_indexing,
                    tenant_id,
                )
            else:
                logger.info(f"No new emails found for {user_email}")

            topic_name = await self.ssm_client.get_google_email_pub_sub_topic(tenant_id)
            if not topic_name:
                raise ValueError(f"No topic name found for tenant {tenant_id}")

            await webhook_manager.check_tenant_user_webhook_expiration(
                email_client, tenant_id, user_email, topic_name, db_pool
            )

            logger.info(f"Processing Google Email webhook job {job_id} for tenant {tenant_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to process Google Email webhook job {job_id}: {e}")
            raise

    async def _process_new_emails(
        self,
        email_client: GoogleEmailClient,
        user_id: str,
        message_ids: list[str],
        job_id: str,
        user_email: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
        tenant_id: str,
    ) -> None:
        total_processed = 0
        message_ids_batch = []

        parallel_batch_size = 10

        for i in range(0, len(message_ids), parallel_batch_size):
            batch = message_ids[i : i + parallel_batch_size]
            batch_results = await email_client.get_emails_batch(
                user_id="me", message_ids=batch, format="full"
            )

            for msg_id, message_data_or_error in zip(batch, batch_results, strict=False):
                if isinstance(message_data_or_error, Exception):
                    logger.error(f"Failed to fetch message {msg_id}: {message_data_or_error}")
                    continue

                artifact = await create_email_artifact(
                    email_client, user_id, msg_id, job_id, user_email, message_data_or_error
                )

                if artifact:
                    await self.store_artifact(db_pool, artifact)
                    message_ids_batch.append(msg_id)
                    total_processed += 1
                    if len(message_ids_batch) >= DEFAULT_INDEX_BATCH_SIZE:
                        await trigger_indexing(
                            message_ids_batch, DocumentSource.GOOGLE_EMAIL, tenant_id
                        )
                        message_ids_batch = []
                        logger.info(
                            f"Indexed batch of {DEFAULT_INDEX_BATCH_SIZE} emails for {user_email}"
                        )
        if message_ids_batch:
            await trigger_indexing(message_ids_batch, DocumentSource.GOOGLE_EMAIL, tenant_id)
            logger.info(f"Indexed final batch of {len(message_ids_batch)} emails for {user_email}")

        logger.info(
            f"Finished processing emails for {user_email}. "
            f"Total domain-accessible emails: {total_processed}"
        )
