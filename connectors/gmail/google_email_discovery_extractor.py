import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, get_google_drive_user_entity_id
from connectors.base.document_source import DocumentSource
from connectors.gmail.gmail_models import (
    GoogleEmailDiscoveryConfig,
    GoogleEmailUserConfig,
)
from connectors.gmail.google_email_webhook_handler import GoogleEmailWebhookManager
from connectors.google_drive.google_drive_artifacts import (
    GoogleDriveUserArtifact,
    GoogleDriveUserContent,
    GoogleDriveUserMetadata,
)
from src.clients.google_email import GoogleEmailClient
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


class GoogleEmailDiscoveryExtractor(BaseExtractor[GoogleEmailDiscoveryConfig]):
    source_name = "google_email_discovery"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: GoogleEmailDiscoveryConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: Callable[[list[str], DocumentSource, str], Awaitable[None]],
    ) -> None:
        try:
            admin_email = await self.ssm_client.get_google_email_admin_email(config.tenant_id)
            if not admin_email:
                raise ValueError(f"No admin email found for tenant {config.tenant_id}")

            topic_name = await self.ssm_client.get_google_email_pub_sub_topic(config.tenant_id)
            if not topic_name:
                raise ValueError(f"No topic name found for tenant {config.tenant_id}")

            email_client = GoogleEmailClient(
                tenant_id=config.tenant_id, admin_email=admin_email, ssm_client=self.ssm_client
            )

            logger.info(f"Starting Google Email discovery for tenant {config.tenant_id}")

            await self._discover_users(
                email_client, topic_name, job_id, config.tenant_id, db_pool, config
            )

            await self._register_webhooks(email_client, config.tenant_id, db_pool)

            logger.info(f"Successfully completed Google Email discovery job {job_id}")

        except Exception as e:
            logger.error(f"Discovery job {job_id} failed: {e}")
            raise

    async def _discover_users(
        self,
        email_client: GoogleEmailClient,
        topic_name: str,
        job_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        config: GoogleEmailDiscoveryConfig,
    ) -> None:
        try:
            users = await email_client.list_users()
            logger.info(f"Found {len(users)} users in Google Workspace")

            for user_data in users:
                if user_data.get("suspended", False):
                    logger.info(f"Skipping suspended user: {user_data.get('primaryEmail')}")
                    continue

                artifact = GoogleDriveUserArtifact(
                    entity_id=get_google_drive_user_entity_id(user_id=user_data["id"]),
                    ingest_job_id=UUID(job_id),
                    source_updated_at=datetime.fromisoformat(
                        user_data.get("lastLoginTime", datetime.now(UTC).isoformat())
                    ),
                    content=GoogleDriveUserContent(
                        user_id=user_data["id"],
                        email=user_data["primaryEmail"],
                        full_name=user_data.get("name", {}).get("fullName", ""),
                        given_name=user_data.get("name", {}).get("givenName"),
                        family_name=user_data.get("name", {}).get("familyName"),
                        is_admin=user_data.get("isAdmin", False),
                        is_suspended=user_data.get("suspended", False),
                        org_unit_path=user_data.get("orgUnitPath"),
                        creation_time=user_data.get("creationTime"),
                        last_login_time=user_data.get("lastLoginTime"),
                    ),
                    metadata=GoogleDriveUserMetadata(
                        primary_email=user_data["primaryEmail"],
                        aliases=user_data.get("aliases", []),
                        photo_url=user_data.get("thumbnailPhotoUrl"),
                    ),
                )

                await self.store_artifact(db_pool, artifact)
                logger.debug(f"Stored user artifact for {user_data['primaryEmail']}")

                user_email_config = GoogleEmailUserConfig(
                    tenant_id=config.tenant_id,
                    user_email=user_data["primaryEmail"],
                    user_id=user_data["id"],
                    backfill_id=config.backfill_id,
                    suppress_notification=config.suppress_notification,
                )
                await self._send_job(user_email_config)
                logger.info(
                    f"Spawned job to process personal emails for {user_data['primaryEmail']}"
                )

        except Exception as e:
            logger.error(f"Failed to discover users: {e}")
            raise

    async def _send_job(
        self,
        config: GoogleEmailUserConfig,
    ) -> None:
        try:
            message_id = await self.sqs_client.send_backfill_ingest_message(
                backfill_config=config,
            )

            if not message_id:
                raise Exception(f"Failed to send backfill job for {config.source}")

        except Exception as e:
            logger.error(f"Failed to send job: {e}")
            raise

    async def _register_webhooks(
        self,
        email_client: GoogleEmailClient,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> None:
        """Register Google Email webhooks for all discovered users."""
        try:
            logger.info(f"Starting webhook registration for tenant {tenant_id}")

            webhook_manager = GoogleEmailWebhookManager()

            async with db_pool.acquire() as conn:
                await webhook_manager.register_and_store_webhooks(tenant_id, email_client, conn)

        except Exception as e:
            logger.error(f"Failed to register webhooks for tenant {tenant_id}: {e}")
