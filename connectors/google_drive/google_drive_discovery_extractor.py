import logging
import secrets
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import (
    BaseExtractor,
    TriggerIndexingCallback,
    get_google_drive_shared_drive_entity_id,
    get_google_drive_user_entity_id,
)
from connectors.google_drive.google_drive_artifacts import (
    GoogleDriveSharedDriveArtifact,
    GoogleDriveSharedDriveContent,
    GoogleDriveSharedDriveMetadata,
    GoogleDriveUserArtifact,
    GoogleDriveUserContent,
    GoogleDriveUserMetadata,
)
from connectors.google_drive.google_drive_models import (
    GoogleDriveDiscoveryConfig,
    GoogleDriveSharedDriveConfig,
    GoogleDriveUserDriveConfig,
)
from connectors.google_drive.google_drive_webhook_handler import GoogleDriveWebhookManager
from src.clients.google_drive import GoogleDriveClient
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = logging.getLogger(__name__)


class GoogleDriveDiscoveryExtractor(BaseExtractor[GoogleDriveDiscoveryConfig]):
    source_name = "google_drive_discovery"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: GoogleDriveDiscoveryConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # Generate a unique backfill ID for this root job
        backfill_id = secrets.token_hex(8)
        logger.info(
            f"Processing Google Drive discovery for tenant {config.tenant_id} with backfill_id {backfill_id}"
        )

        try:
            admin_email = await self.ssm_client.get_google_drive_admin_email(config.tenant_id)
            if not admin_email:
                raise ValueError(f"No admin email found for tenant {config.tenant_id}")

            drive_client = GoogleDriveClient(
                tenant_id=config.tenant_id, admin_email=admin_email, ssm_client=self.ssm_client
            )

            logger.info(f"Starting Google Drive discovery for tenant {config.tenant_id}")

            # Collect child job counts
            child_jobs: list[GoogleDriveUserDriveConfig | GoogleDriveSharedDriveConfig] = []
            await self._discover_users(
                drive_client,
                job_id,
                config.tenant_id,
                db_pool,
                backfill_id,
                child_jobs,
                config.suppress_notification,
            )
            await self._discover_shared_drives(
                drive_client,
                job_id,
                config.tenant_id,
                db_pool,
                backfill_id,
                child_jobs,
                config.suppress_notification,
            )

            # Track total number of ingest jobs (child jobs) for this backfill
            if child_jobs:
                await increment_backfill_total_ingest_jobs(
                    backfill_id, config.tenant_id, len(child_jobs)
                )

            await self._register_webhooks(drive_client, config.tenant_id, db_pool)

            logger.info(
                f"Successfully completed Google Drive discovery job {job_id} with {len(child_jobs)} child jobs"
            )

        except Exception as e:
            logger.error(f"Discovery job {job_id} failed: {e}")
            raise

    async def _discover_users(
        self,
        drive_client: GoogleDriveClient,
        job_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        backfill_id: str,
        child_jobs: list[GoogleDriveUserDriveConfig | GoogleDriveSharedDriveConfig],
        suppress_notification: bool,
    ) -> None:
        try:
            users = await drive_client.list_users()
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

                user_drive_config = GoogleDriveUserDriveConfig(
                    tenant_id=tenant_id,
                    user_email=user_data["primaryEmail"],
                    user_id=user_data["id"],
                    backfill_id=backfill_id,
                    suppress_notification=suppress_notification,
                )
                await self._send_job(user_drive_config)
                child_jobs.append(user_drive_config)
                logger.info(
                    f"Spawned job to process personal drive for {user_data['primaryEmail']}"
                )

        except Exception as e:
            logger.error(f"Failed to discover users: {e}")
            raise

    async def _discover_shared_drives(
        self,
        drive_client: GoogleDriveClient,
        job_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        backfill_id: str,
        child_jobs: list[GoogleDriveUserDriveConfig | GoogleDriveSharedDriveConfig],
        suppress_notification: bool,
    ) -> None:
        try:
            drives = await drive_client.list_shared_drives()
            logger.info(f"Found {len(drives)} shared drives")

            processed_drives = set()

            for drive_data in drives:
                drive_id = drive_data["id"]

                if drive_id in processed_drives:
                    continue
                processed_drives.add(drive_id)

                artifact = GoogleDriveSharedDriveArtifact(
                    entity_id=get_google_drive_shared_drive_entity_id(drive_id=drive_id),
                    ingest_job_id=UUID(job_id),
                    source_updated_at=datetime.fromisoformat(
                        drive_data.get("createdTime", datetime.now(UTC).isoformat())
                    ),
                    content=GoogleDriveSharedDriveContent(
                        drive_id=drive_id,
                        name=drive_data.get("name", "Unnamed Drive"),
                        created_time=drive_data.get("createdTime"),
                    ),
                    metadata=GoogleDriveSharedDriveMetadata(
                        color_rgb=drive_data.get("colorRgb"),
                        background_image_link=drive_data.get("backgroundImageLink"),
                        capabilities=drive_data.get("capabilities"),
                    ),
                )

                await self.store_artifact(db_pool, artifact)
                logger.debug(f"Stored shared drive artifact for {drive_data.get('name')}")

                shared_drive_config = GoogleDriveSharedDriveConfig(
                    tenant_id=tenant_id,
                    drive_id=drive_id,
                    drive_name=drive_data.get("name", "Unnamed Drive"),
                    backfill_id=backfill_id,
                    suppress_notification=suppress_notification,
                )
                await self._send_job(shared_drive_config)
                child_jobs.append(shared_drive_config)
                logger.info(f"Spawned job to process shared drive: {drive_data.get('name')}")

        except Exception as e:
            logger.error(f"Failed to discover shared drives: {e}")
            raise

    async def _send_job(
        self,
        config: GoogleDriveUserDriveConfig | GoogleDriveSharedDriveConfig,
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
        drive_client: GoogleDriveClient,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> None:
        """Register Google Drive webhooks for all discovered users and shared drives."""
        try:
            logger.info(f"Starting webhook registration for tenant {tenant_id}")

            webhook_manager = GoogleDriveWebhookManager()

            async with db_pool.acquire() as conn:
                await webhook_manager.register_and_store_webhooks(tenant_id, drive_client, conn)

        except Exception as e:
            logger.error(f"Failed to register webhooks for tenant {tenant_id}: {e}")
