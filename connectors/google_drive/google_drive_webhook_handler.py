import json
import secrets
from datetime import UTC, datetime, timedelta

import asyncpg

from src.clients.google_drive import GoogleDriveClient
from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.config import get_base_domain
from src.utils.logging import get_logger

logger = get_logger(__name__)


class GoogleDriveWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for Google Drive webhooks using channel token verification."""

    source_type = "google_drive"
    verify_func = staticmethod(lambda h, b, s: verify_google_drive_webhook(h, b, s))


def verify_google_drive_webhook(headers: dict[str, str], body: bytes, secret: str) -> None:
    """Verify Google Drive webhook using channel token.

    Google Drive push notifications use a token-based verification system.
    The token is sent in the X-Goog-Channel-Token header and should match
    the token that was provided when creating the watch channel.

    Args:
        headers: Webhook headers
        body: Webhook body (unused for Google Drive, notifications are empty)
        secret: Expected channel token

    Raises:
        ValueError: If verification fails
    """
    # Google Drive sends the channel token in X-Goog-Channel-Token header
    channel_token = headers.get("x-goog-channel-token", "")
    if not channel_token:
        raise ValueError("Missing X-Goog-Channel-Token header")

    if channel_token != secret:
        raise ValueError("Google Drive webhook token verification failed: token mismatch")

    logger.debug("Google Drive webhook token verification successful")


class GoogleDriveWebhookManager:
    """Service to manage Google Drive webhook channels across all tenants."""

    def __init__(self):
        self.ssm_client = SSMClient()

    async def ensure_signing_secret(self, tenant_id: str) -> str:
        """Ensure a Google Drive signing secret exists for the tenant, creating one if needed.

        Args:
            tenant_id: The tenant ID

        Returns:
            The signing secret to use for webhook token verification
        """
        # Try to get existing signing secret
        signing_secret = await self.ssm_client.get_signing_secret(tenant_id, "google_drive")

        if not signing_secret:
            # Generate a new secure token for this tenant
            signing_secret = f"gdrive_webhook_{tenant_id}_{secrets.token_urlsafe(32)}"

            # Store it in SSM
            await self.ssm_client.store_signing_secret(tenant_id, "google_drive", signing_secret)

            logger.info(
                f"Generated and stored new Google Drive signing secret for tenant {tenant_id}"
            )
        else:
            logger.debug(f"Using existing Google Drive signing secret for tenant {tenant_id}")

        return signing_secret

    async def register_tenant_webhooks(
        self,
        tenant_id: str,
        drive_client: GoogleDriveClient,
        conn: asyncpg.Connection,
        webhook_url: str | None = None,
    ) -> dict[str, dict[str, dict[str, str]]]:
        """Register Google Drive webhooks for a tenant's users and shared drives.

        This is the centralized method for webhook registration that should be used
        by discovery, refresh, and test scripts.

        Args:
            tenant_id: The tenant ID
            drive_client: Authenticated Google Drive client
            conn: Database connection for the tenant
            webhook_url: Optional custom webhook URL (defaults to production URL)

        Returns:
            Webhook configuration dict with users and shared_drives
        """
        signing_secret = await self.ensure_signing_secret(tenant_id)

        base_domain = get_base_domain()
        base_url = f"https://{tenant_id}.ingest.{base_domain}"

        if webhook_url is None:
            webhook_url = f"{base_url}/webhooks/google-drive"

        logger.info(
            f"Registering Google Drive webhooks for tenant {tenant_id} using URL: {webhook_url}"
        )

        webhook_config: dict[str, dict[str, dict[str, str]]] = {"users": {}, "shared_drives": {}}

        # Get current user artifacts (only active users)
        user_artifacts = await conn.fetch(
            """
            SELECT content FROM ingest_artifact
            WHERE entity = 'google_drive_user' AND (content ->> 'is_suspended')::boolean = false
            """
        )

        for row in user_artifacts:
            content = row["content"]
            user_email = content["email"]

            try:
                user_client = await drive_client.impersonate_user(user_email)

                page_token = await user_client.get_start_page_token()

                channel = await user_client.watch_changes(
                    page_token=page_token,
                    webhook_url=webhook_url,
                    restrict_to_my_drive=True,
                    token=signing_secret,
                )

                webhook_config["users"][user_email] = {
                    "channel_id": channel["id"],
                    "resource_id": channel["resourceId"],
                    "page_token": page_token,
                    "webhook_url": webhook_url,
                    "created_at": datetime.now(UTC).isoformat(),
                }

                logger.debug(f"Registered webhook for user {user_email}")

            except Exception as e:
                logger.error(f"Failed to register webhook for user {user_email}: {e}")

        shared_drive_artifacts = await conn.fetch(
            """
            SELECT content FROM ingest_artifact
            WHERE entity = 'google_drive_shared_drive'
            """
        )

        for row in shared_drive_artifacts:
            content = row["content"]
            drive_id = content["drive_id"]
            drive_name = content.get("name", "Unknown")

            try:
                page_token = await drive_client.get_start_page_token(drive_id=drive_id)

                channel = await drive_client.watch_changes(
                    page_token=page_token,
                    webhook_url=webhook_url,
                    drive_id=drive_id,
                    token=signing_secret,
                )

                webhook_config["shared_drives"][drive_id] = {
                    "channel_id": channel["id"],
                    "resource_id": channel["resourceId"],
                    "page_token": page_token,
                    "webhook_url": webhook_url,
                    "drive_name": drive_name,
                    "created_at": datetime.now(UTC).isoformat(),
                }

                logger.debug(f"Registered webhook for shared drive {drive_name}")

            except Exception as e:
                logger.error(f"Failed to register webhook for shared drive {drive_name}: {e}")

        user_count = len(webhook_config["users"])
        drive_count = len(webhook_config["shared_drives"])
        logger.info(
            f"Registered webhooks for tenant {tenant_id}: {user_count} users, {drive_count} shared drives"
        )

        return webhook_config

    async def register_and_store_webhooks(
        self,
        tenant_id: str,
        drive_client: GoogleDriveClient,
        conn: asyncpg.Connection,
        webhook_url: str | None = None,
    ) -> dict[str, dict[str, dict[str, str]]]:
        """Register webhooks and store the configuration in the database.

        This is the complete method that handles both webhook registration
        and database storage, used by discovery and other processes.

        Args:
            tenant_id: The tenant ID
            drive_client: Authenticated Google Drive client
            conn: Database connection for the tenant
            webhook_url: Optional custom webhook URL (defaults to production URL)

        Returns:
            Webhook configuration dict with users and shared_drives
        """
        webhook_config = await self.register_tenant_webhooks(
            tenant_id, drive_client, conn, webhook_url
        )

        await self._update_webhook_config(
            conn, webhook_config, tenant_id, "Successfully registered and stored"
        )

        return webhook_config

    async def refresh_all_expiring_tenant_webhooks(self) -> None:
        """Refresh all expiring webhooks for all tenants."""
        try:
            logger.info("Starting daily Google Drive webhook refresh for all tenants")

            control_pool = await tenant_db_manager.get_control_db()
            async with control_pool.acquire() as conn:
                tenants = await conn.fetch(
                    """
                    SELECT id FROM tenants
                    WHERE state = 'provisioned'
                    """
                )

            logger.info(f"Found {len(tenants)} provisioned tenants")

            for tenant_row in tenants:
                tenant_id = tenant_row["id"]
                try:
                    await self.refresh_expiring_tenant_webhooks(tenant_id)
                except Exception as e:
                    logger.error(f"Failed to refresh webhooks for tenant {tenant_id}: {e}")

            logger.info("Completed daily Google Drive webhook refresh")
        except Exception as e:
            logger.error(f"Failed to refresh webhooks across tenants: {e}")
            raise

    async def refresh_all_tenant_webhooks(self) -> None:
        """Refresh webhooks for all tenants with Google Drive integration."""
        try:
            logger.info("Starting daily Google Drive webhook refresh for all tenants")

            control_pool = await tenant_db_manager.get_control_db()
            async with control_pool.acquire() as conn:
                tenants = await conn.fetch(
                    """
                    SELECT id FROM tenants
                    WHERE state = 'provisioned'
                    """
                )

            logger.info(f"Found {len(tenants)} provisioned tenants")

            for tenant_row in tenants:
                tenant_id = tenant_row["id"]
                try:
                    await self.refresh_expiring_tenant_webhooks(tenant_id)
                except Exception as e:
                    logger.error(f"Failed to refresh webhooks for tenant {tenant_id}: {e}")

            logger.info("Completed daily Google Drive webhook refresh")

        except Exception as e:
            logger.error(f"Failed to refresh webhooks across tenants: {e}")
            raise

    async def get_all_tenants_with_google_drive_webhook_config(self) -> list[str]:
        """Get all tenants with Google Drive webhook config."""
        try:
            control_pool = await tenant_db_manager.get_control_db()
            async with control_pool.acquire() as conn:
                tenants = await conn.fetch(
                    """
                    SELECT id FROM tenants
                    WHERE state = 'provisioned'
                    """
                )
                tenant_ids = [tenant["id"] for tenant in tenants]
                results = []
                for tenant_id in tenant_ids:
                    async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                        existing_config, drive_client = await self._get_tenant_webhook_setup(
                            tenant_id, conn
                        )
                        if existing_config and drive_client:
                            results.append(tenant_id)
                return results
        except Exception as e:
            logger.error(f"Failed to get all tenants with Google Drive webhook config: {e}")
            raise

    async def refresh_expiring_tenant_webhooks(self, tenant_id: str) -> None:
        """Refresh expiring webhooks for a specific tenant."""
        try:
            logger.info(f"Refreshing expiring webhooks for tenant {tenant_id}")
            async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                existing_config, drive_client = await self._get_tenant_webhook_setup(
                    tenant_id, conn
                )
                if not existing_config or not drive_client:
                    return
                users = existing_config.get("users", {})
                if users:
                    oldest_user = min(users.values(), key=lambda x: x["created_at"])
                    # add 7 days to the oldest user created at
                    oldest_user_created_at = datetime.fromisoformat(
                        oldest_user["created_at"]
                    ) + timedelta(days=7)
                    time_diff = oldest_user_created_at - datetime.now(UTC)
                    # if the time difference is less than 3 days, refresh the webhooks
                    if time_diff <= timedelta(days=3):
                        # refresh the webhooks for the tenant
                        await self._refresh_tenant_webhooks(tenant_id)

        except Exception as e:
            logger.error(f"Failed to refresh expiring webhooks for tenant {tenant_id}: {e}")
            raise

    async def _refresh_tenant_webhooks(self, tenant_id: str) -> None:
        """Refresh webhooks for a specific tenant."""
        try:
            logger.info(f"Refreshing webhooks for tenant {tenant_id}")

            async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                existing_config, drive_client = await self._get_tenant_webhook_setup(
                    tenant_id, conn
                )
                if not existing_config or not drive_client:
                    return

                await self._stop_existing_channels(drive_client, existing_config)

                new_config = await self.register_tenant_webhooks(tenant_id, drive_client, conn)

                await self._update_webhook_config(conn, new_config, tenant_id, "Refreshed")

        except Exception as e:
            logger.error(f"Failed to refresh webhooks for tenant {tenant_id}: {e}")
            raise

    async def stop_all_tenant_webhooks(self) -> None:
        """Stop all Google Drive webhooks for all tenants (cleanup/emergency shutdown)."""
        try:
            logger.info("Starting emergency shutdown of all Google Drive webhooks")

            control_pool = await tenant_db_manager.get_control_db()
            async with control_pool.acquire() as conn:
                tenants = await conn.fetch(
                    """
                    SELECT id FROM tenants
                    WHERE state = 'provisioned'
                    """
                )

            logger.info(f"Found {len(tenants)} provisioned tenants")

            total_stopped = 0
            for tenant_row in tenants:
                tenant_id = tenant_row["id"]
                try:
                    stopped_count = await self._stop_all_webhooks_for_tenant(tenant_id)
                    total_stopped += stopped_count
                except Exception as e:
                    logger.error(f"Failed to stop webhooks for tenant {tenant_id}: {e}")

            logger.info(f"Emergency shutdown completed: stopped {total_stopped} webhook channels")

        except Exception as e:
            logger.error(f"Failed to stop all webhooks: {e}")
            raise

    async def _stop_all_webhooks_for_tenant(self, tenant_id: str) -> int:
        """Stop all webhooks for a specific tenant and clear config."""
        try:
            logger.info(f"Stopping all webhooks for tenant {tenant_id}")

            async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                existing_config, drive_client = await self._get_tenant_webhook_setup(
                    tenant_id, conn
                )
                if not existing_config or not drive_client:
                    return 0

                await self._stop_existing_channels(drive_client, existing_config)
                stopped_count = len(existing_config.get("users", {})) + len(
                    existing_config.get("shared_drives", {})
                )

                await self._clear_webhook_config(conn)

                logger.info(
                    f"Stopped {stopped_count} webhook channels for tenant {tenant_id} and cleared config"
                )
                return stopped_count

        except Exception as e:
            logger.error(f"Failed to stop webhooks for tenant {tenant_id}: {e}")
            return 0

    async def _stop_existing_channels(
        self, drive_client: GoogleDriveClient, existing_config: dict
    ) -> None:
        """Stop all existing webhook channels."""
        stopped_count = 0
        stopped_count += await self._stop_channels_by_type(
            drive_client, existing_config.get("users", {}), "user"
        )
        stopped_count += await self._stop_channels_by_type(
            drive_client, existing_config.get("shared_drives", {}), "shared drive"
        )
        logger.info(f"Stopped {stopped_count} existing webhook channels")

    async def _stop_channels_by_type(
        self, drive_client: GoogleDriveClient, channels: dict, channel_type: str
    ) -> int:
        """Stop all channels of a specific type (user or shared drive)."""
        stopped_count = 0

        for identifier, channel_info in channels.items():
            try:
                if channel_type == "user":
                    user_email = identifier  # identifier is the user email for user channels
                    user_client = await drive_client.impersonate_user(user_email)
                    await user_client.stop_watch_channel(
                        channel_info["channel_id"], channel_info["resource_id"]
                    )
                    logger.debug(
                        f"Stopped {channel_type} webhook channel for {identifier} (impersonating user)"
                    )
                else:
                    await drive_client.stop_watch_channel(
                        channel_info["channel_id"], channel_info["resource_id"]
                    )
                    logger.debug(f"Stopped {channel_type} webhook channel for {identifier}")

                stopped_count += 1
            except Exception as e:
                logger.warning(f"Failed to stop {channel_type} channel for {identifier}: {e}")

        return stopped_count

    async def _get_tenant_webhook_setup(
        self, tenant_id: str, conn: asyncpg.Connection
    ) -> tuple[dict | None, GoogleDriveClient | None]:
        """Get tenant's webhook config and drive client, or None if not available."""
        config_row = await conn.fetchrow(
            "SELECT value FROM config WHERE key = 'GOOGLE_DRIVE_WEBHOOKS'"
        )

        if not config_row:
            logger.debug(f"Tenant {tenant_id} has no Google Drive webhook config")
            return None, None

        existing_config = json.loads(config_row["value"])

        admin_email = await self.ssm_client.get_google_drive_admin_email(tenant_id)
        if not admin_email:
            logger.warning(f"No admin email found for tenant {tenant_id}")
            return existing_config, None

        drive_client = GoogleDriveClient(
            tenant_id=tenant_id, admin_email=admin_email, ssm_client=self.ssm_client
        )

        return existing_config, drive_client

    async def _update_webhook_config(
        self,
        conn: asyncpg.Connection,
        webhook_config: dict,
        tenant_id: str,
        action: str = "Updated",
    ) -> None:
        """Update or clear webhook config in database based on results."""
        if webhook_config["users"] or webhook_config["shared_drives"]:
            await conn.execute(
                """
                INSERT INTO config (key, value)
                VALUES ($1, $2)
                ON CONFLICT (key)
                DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                """,
                "GOOGLE_DRIVE_WEBHOOKS",
                json.dumps(webhook_config),
            )

            user_count = len(webhook_config["users"])
            drive_count = len(webhook_config["shared_drives"])
            logger.info(
                f"{action} webhooks for tenant {tenant_id}: {user_count} users, {drive_count} shared drives"
            )
        else:
            # No current artifacts, clear the config
            await self._clear_webhook_config(conn)
            logger.info(f"Cleared webhook config for tenant {tenant_id} (no active artifacts)")

    async def _clear_webhook_config(self, conn: asyncpg.Connection) -> None:
        """Clear webhook configuration from database."""
        await conn.execute("DELETE FROM config WHERE key = 'GOOGLE_DRIVE_WEBHOOKS'")


# Singleton instance for use in cron jobs
webhook_manager = GoogleDriveWebhookManager()
