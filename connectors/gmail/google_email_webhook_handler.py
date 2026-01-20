import json
import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import asyncpg
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from src.clients.google_email import GoogleEmailClient
from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.ingest.gatekeeper.verification import VerificationResult
from src.utils.logging import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _get_gcp_project_id() -> str | None:
    """Get the GCP project ID from the control service account configuration.

    Returns:
        The GCP project ID, or None if not configured.
    """
    control_sa_json = os.environ.get("GOOGLE_DRIVE_CONTROL_SERVICE_ACCOUNT")
    if not control_sa_json:
        return None
    try:
        control_sa = json.loads(control_sa_json)
        return control_sa.get("project_id")
    except (json.JSONDecodeError, KeyError):
        return None


class GoogleEmailWebhookVerifier:
    """Verifier for Google Email (Gmail via Pub/Sub) webhooks.

    Verifies webhooks using OIDC JWT tokens in the Authorization header.
    Google Pub/Sub push subscriptions are configured to include a signed JWT
    that we verify using Google's public keys.

    Security validations:
    - JWT signature is valid (signed by Google)
    - JWT audience matches the expected webhook URL
    - JWT email matches the expected tenant service account
    """

    async def verify(
        self,
        headers: dict[str, str],
        body: bytes,
        tenant_id: str,
        request_url: str | None = None,
    ) -> VerificationResult:
        """Verify a Google Email webhook using OIDC JWT.

        Args:
            headers: Request headers containing Authorization bearer token
            body: Request body (Pub/Sub message)
            tenant_id: Tenant ID to validate service account against
            request_url: Expected audience (webhook URL)
        """
        try:
            verify_google_email_webhook(
                headers, body, expected_audience=request_url, tenant_id=tenant_id
            )
            return VerificationResult(success=True)
        except ValueError as e:
            return VerificationResult(success=False, error=str(e))


def verify_google_email_webhook(
    headers: dict[str, str],
    body: bytes,
    expected_audience: str | None = None,
    tenant_id: str | None = None,
) -> None:
    """Verify Google Email (Gmail via Pub/Sub push) webhook.

    Verifies the webhook using the OIDC JWT token in the Authorization header.
    Also validates the Pub/Sub message structure.

    Security validations:
    - JWT signature is valid (signed by Google)
    - JWT issuer is Google
    - JWT audience matches expected_audience (webhook URL)
    - JWT email matches expected tenant service account pattern

    Args:
        headers: Webhook headers (must contain Authorization: Bearer <jwt>)
        body: Raw request body containing the Pub/Sub push JSON
        expected_audience: Expected JWT audience (should be the webhook URL)
        tenant_id: Tenant ID to validate service account email against

    Raises:
        ValueError: If verification fails
    """
    # Validate the message structure
    try:
        payload: dict[str, Any] = json.loads(body.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Invalid JSON body: {e}")

    message = payload.get("message", {})

    if not message.get("data"):
        raise ValueError("Missing data attribute in Pub/Sub message for Google Email webhook")

    # Verify the JWT token from Authorization header
    auth_header = headers.get("authorization")
    if not auth_header:
        raise ValueError("Missing Authorization header in Google Email webhook")

    _verify_jwt_token(auth_header, expected_audience=expected_audience, tenant_id=tenant_id)
    logger.debug("Google Email webhook JWT verification successful")


def _verify_jwt_token(
    auth_header: str,
    expected_audience: str | None = None,
    tenant_id: str | None = None,
) -> None:
    """Verify JWT token from Authorization header using Google's public keys.

    Args:
        auth_header: Authorization header value (Bearer <token>)
        expected_audience: Expected JWT audience (webhook URL). If provided, validates aud claim.
        tenant_id: Tenant ID to validate service account email against.

    Raises:
        ValueError: If JWT verification fails
    """
    try:
        # Extract JWT token from Bearer header
        if not auth_header.startswith("Bearer "):
            raise ValueError("Invalid authorization header format - expected 'Bearer <token>'")

        token = auth_header.split("Bearer ")[1]

        # Create Google request adapter for token verification
        request_adapter = google_requests.Request()

        # Verify the JWT token using Google's public keys
        # This verifies:
        # 1. Token signature (signed by Google)
        # 2. Token expiration
        # 3. Token issuer
        # 4. Audience (if provided)
        id_info = id_token.verify_oauth2_token(
            token,
            request_adapter,
            audience=expected_audience,  # Validates aud claim if provided
        )

        # Verify the token issuer is Google
        if id_info["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
            raise ValueError(f"Wrong issuer for Google Email webhook: {id_info['iss']}")

        # Verify the email is a Google service account (ends with .iam.gserviceaccount.com)
        email = id_info.get("email", "")
        if not email.endswith(".iam.gserviceaccount.com"):
            raise ValueError(f"JWT email is not a Google service account: {email}")

        # If tenant_id is provided, verify the email matches the expected tenant service account
        # Format: tenant-{tenant_id}@{project_id}.iam.gserviceaccount.com
        if tenant_id:
            project_id = _get_gcp_project_id()
            if project_id:
                # Validate the exact email address including project ID for security
                expected_email = f"tenant-{tenant_id}@{project_id}.iam.gserviceaccount.com"
                if email != expected_email:
                    raise ValueError(
                        f"JWT email does not match expected tenant service account. "
                        f"Expected: {expected_email}, got: {email}"
                    )
            else:
                # Fallback: validate prefix if project ID not available (less secure)
                expected_prefix = f"tenant-{tenant_id}@"
                if not email.startswith(expected_prefix):
                    raise ValueError(
                        f"JWT email does not match expected tenant service account. "
                        f"Expected prefix: {expected_prefix}, got: {email}"
                    )
                logger.warning(
                    "GCP project ID not configured - using prefix-only email validation (less secure)"
                )
            logger.debug(f"JWT email validated for tenant {tenant_id}: {email}")

    except ValueError:
        # Re-raise ValueError as-is
        raise
    except Exception as e:
        raise ValueError(f"JWT verification failed: {e}")


class GoogleEmailWebhookManager:
    """Service to manage Google Email webhook channels across all tenants."""

    def __init__(self):
        self.ssm_client = SSMClient()

    async def _register_user_webhook(
        self,
        email_client: GoogleEmailClient,
        user_email: str,
        topic_name: str,
    ) -> dict[str, Any]:
        """Register Google Email webhooks for a tenant's user."""
        user_client = await email_client.impersonate_user(user_email)

        await user_client.stop_all_watches()

        watch_result = await user_client.create_watch(
            topic_name=topic_name,
        )

        payload = {
            "expiration": watch_result["expiration"],
            "history_id": watch_result["historyId"],
            "topic_name": topic_name,
            "created_at": datetime.now(UTC).isoformat(),
        }

        return payload

    async def check_tenant_user_webhook_expiration(
        self,
        email_client: GoogleEmailClient,
        tenant_id: str,
        user_email: str,
        topic_name: str,
        conn: asyncpg.Connection,
    ) -> bool:
        """Check if a Google Email webhook is registered for a tenant's user."""
        current_config = await self.get_webhook_user_config(conn, tenant_id, user_email)
        if not current_config:
            return False
        current_config = json.loads(current_config)

        expiration = datetime.fromtimestamp(int(current_config["expiration"]) / 1000, tz=UTC)
        now = datetime.now(UTC)
        time_diff = expiration - now

        if time_diff <= timedelta(days=3):
            webhook_config = await self._register_user_webhook(email_client, user_email, topic_name)
            await self.update_webhook_user_config(
                conn,
                tenant_id,
                user_email,
                {
                    "expiration": webhook_config["expiration"],
                    "history_id": webhook_config["history_id"],
                },
            )
            logger.info(f"Updated webhook config for tenant {tenant_id} and user {user_email}")
            return True
        else:
            return False

    async def register_tenant_webhooks(
        self,
        tenant_id: str,
        email_client: GoogleEmailClient,
        conn: asyncpg.Connection,
        topic_name: str,
    ) -> dict[str, dict[str, dict[str, str]]]:
        """Register Google Email webhooks for a tenant's users.

        This is the centralized method for webhook registration that should be used
        by discovery, refresh, and test scripts.

        Args:
            tenant_id: The tenant ID
            email_client: Authenticated Google Email client
            conn: Database connection for the tenant
            topic_name: Pub/Sub topic name

        Returns:
            Webhook configuration dict with users
        """
        webhook_config: dict[str, dict[str, dict[str, str]]] = {"users": {}}

        # Get current user artifacts (only active users)
        # Currently all google_driver_user's are just google workspace users
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
                webhook_config["users"][user_email] = await self._register_user_webhook(
                    email_client, user_email, topic_name
                )
                logger.debug(f"Registered webhook for user {user_email}")

            except Exception as e:
                logger.error(f"Failed to register webhook for user {user_email}: {e}")

        user_count = len(webhook_config["users"])
        logger.info(f"Registered webhooks for tenant {tenant_id}: {user_count} users")

        return webhook_config

    async def register_and_store_webhooks(
        self,
        tenant_id: str,
        email_client: GoogleEmailClient,
        conn: asyncpg.Connection,
    ) -> dict[str, dict[str, dict[str, str]]]:
        """Register webhooks and store the configuration in the database.

        This is the complete method that handles both webhook registration
        and database storage, used by discovery and other processes.

        Args:
            tenant_id: The tenant ID
            email_client: Authenticated Google Email client
            conn: Database connection for the tenant
            webhook_url: Optional custom webhook URL (defaults to production URL)

        Returns:
            Webhook configuration dict with users
        """

        topic_name = await self.ssm_client.get_google_email_pub_sub_topic(tenant_id)
        if not topic_name:
            raise ValueError(f"No topic name found for tenant {tenant_id}")

        webhook_config = await self.register_tenant_webhooks(
            tenant_id, email_client, conn, topic_name
        )

        await self._update_webhook_config(
            conn, webhook_config, tenant_id, "Successfully registered and stored"
        )

        return webhook_config

    async def get_all_tenant_with_google_email_integration(self) -> list[str]:
        """Get all tenants with Google Email integration."""
        control_pool = await tenant_db_manager.get_control_db()
        tenant_ids = []
        async with control_pool.acquire() as conn:
            tenants = await conn.fetch(
                """
                SELECT id FROM tenants
                WHERE state = 'provisioned'
                """
            )
            for tenant in tenants:
                tenant_id = tenant["id"]
                topic_name = await self.ssm_client.get_google_email_pub_sub_topic(tenant_id)
                if topic_name:
                    async with tenant_db_manager.acquire_connection(tenant_id) as tenant_conn:
                        config_row = await tenant_conn.fetchrow(
                            "SELECT value FROM config WHERE key = 'GOOGLE_EMAIL_WEBHOOKS'"
                        )
                        if config_row:
                            tenant_ids.append(tenant_id)

        return tenant_ids

    async def refresh_all_tenant_webhooks(self) -> None:
        """Refresh webhooks for all tenants with Google Email integration."""
        try:
            logger.info("Starting daily Google Email webhook refresh for all tenants")

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
                    await self._refresh_tenant_webhooks(tenant_id)
                except Exception as e:
                    logger.error(f"Failed to refresh webhooks for tenant {tenant_id}: {e}")

            logger.info("Completed daily Google Email webhook refresh")

        except Exception as e:
            logger.error(f"Failed to refresh webhooks across tenants: {e}")
            raise

    async def _refresh_tenant_webhooks(self, tenant_id: str) -> None:
        """Refresh webhooks for a specific tenant."""
        try:
            logger.info(f"Refreshing webhooks for tenant {tenant_id}")

            async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                existing_config, email_client = await self.get_tenant_webhook_setup(tenant_id, conn)
                if not existing_config or not email_client:
                    return

                await self._stop_existing_channels(email_client, existing_config)

                topic_name = await self.ssm_client.get_google_email_pub_sub_topic(tenant_id)
                if not topic_name:
                    logger.error(f"No topic name found for tenant {tenant_id}")
                    return

                new_config = await self.register_tenant_webhooks(
                    tenant_id, email_client, conn, topic_name
                )

                await self._update_webhook_config(conn, new_config, tenant_id, "Refreshed")

        except Exception as e:
            logger.error(f"Failed to refresh webhooks for tenant {tenant_id}: {e}")
            raise

    async def stop_all_tenant_webhooks(self) -> None:
        """Stop all Google Email webhooks for all tenants (cleanup/emergency shutdown)."""
        try:
            logger.info("Starting emergency shutdown of all Google Email webhooks")

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
                existing_config, email_client = await self.get_tenant_webhook_setup(tenant_id, conn)
                if not existing_config or not email_client:
                    return 0

                await self._stop_existing_channels(email_client, existing_config)
                stopped_count = len(existing_config.get("users", {}))

                await self._clear_webhook_config(conn)

                logger.info(
                    f"Stopped {stopped_count} webhook channels for tenant {tenant_id} and cleared config"
                )
                return stopped_count

        except Exception as e:
            logger.error(f"Failed to stop webhooks for tenant {tenant_id}: {e}")
            return 0

    async def _stop_existing_channels(
        self, email_client: GoogleEmailClient, existing_config: dict
    ) -> None:
        """Stop all existing webhook channels."""
        stopped_count = await self._stop_channels_by_type(
            email_client, existing_config.get("users", {}), "user"
        )
        logger.info(f"Stopped {stopped_count} existing webhook channels")

    async def _stop_channels_by_type(
        self, email_client: GoogleEmailClient, channels: dict, channel_type: str
    ) -> int:
        """Stop all channels of a specific type (user)."""
        stopped_count = 0

        for identifier, _ in channels.items():
            try:
                user_email = identifier  # identifier is the user email for user channels
                user_client = await email_client.impersonate_user(user_email)
                await user_client.stop_all_watches()
                logger.debug(
                    f"Stopped {channel_type} webhook channel for {identifier} (impersonating user)"
                )
                stopped_count += 1
            except Exception as e:
                logger.warning(f"Failed to stop {channel_type} channel for {identifier}: {e}")

        return stopped_count

    async def get_tenant_webhook_setup(
        self, tenant_id: str, conn: asyncpg.Connection
    ) -> tuple[dict | None, GoogleEmailClient | None]:
        """Get tenant's webhook config and email client, or None if not available."""
        config_row = await conn.fetchrow(
            "SELECT value FROM config WHERE key = 'GOOGLE_EMAIL_WEBHOOKS'"
        )

        if not config_row:
            logger.debug(f"Tenant {tenant_id} has no Google Email webhook config")
            return None, None

        existing_config = json.loads(config_row["value"])

        admin_email = await self.ssm_client.get_google_email_admin_email(tenant_id)
        if not admin_email:
            logger.warning(f"No admin email found for tenant {tenant_id}")
            return existing_config, None

        email_client = GoogleEmailClient(
            tenant_id=tenant_id, admin_email=admin_email, ssm_client=self.ssm_client
        )

        return existing_config, email_client

    async def _update_webhook_config(
        self,
        conn: asyncpg.Connection,
        webhook_config: dict,
        tenant_id: str,
        action: str = "Updated",
    ) -> None:
        """Update or clear webhook config in database based on results."""
        if webhook_config["users"]:
            await conn.execute(
                """
                INSERT INTO config (key, value)
                VALUES ($1, $2)
                ON CONFLICT (key)
                    DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
                """,
                "GOOGLE_EMAIL_WEBHOOKS",
                json.dumps(webhook_config),
            )

            await self.insert_many_webhook_user_configs(conn, tenant_id, webhook_config["users"])

            user_count = len(webhook_config["users"])
            logger.info(f"{action} webhooks for tenant {tenant_id}: {user_count} users")
        else:
            # No current artifacts, clear the config
            await self._clear_webhook_config(conn)
            logger.info(f"Cleared webhook config for tenant {tenant_id} (no active artifacts)")

    async def _clear_webhook_config(self, conn: asyncpg.Connection) -> None:
        """Clear webhook configuration from database."""
        await conn.execute("DELETE FROM config WHERE key = 'GOOGLE_EMAIL_WEBHOOKS'")
        await conn.execute("DELETE FROM config WHERE key LIKE 'GOOGLE_EMAIL_WEBHOOKS_%'")

    def get_webhook_tenant_user_key(self, tenant_id: str, user_email: str) -> str:
        """Get webhook tenant user key."""
        return f"GOOGLE_EMAIL_WEBHOOKS_{tenant_id}_{user_email}"

    async def get_webhook_user_config(
        self, conn: asyncpg.Connection, tenant_id: str, user_email: str
    ) -> str:
        """Get webhook expiration for a tenant."""
        config_row = await conn.fetchrow(
            "SELECT value FROM config WHERE key = $1",
            self.get_webhook_tenant_user_key(tenant_id, user_email),
        )
        return config_row["value"]

    async def update_webhook_user_config(
        self, conn: asyncpg.Connection, tenant_id: str, user_email: str, config: dict
    ) -> None:
        """Set webhook expiration for a tenant."""
        await conn.execute(
            """
            INSERT INTO config (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key)
            DO UPDATE SET
                value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """,
            self.get_webhook_tenant_user_key(tenant_id, user_email),
            json.dumps(config),
        )

    async def delete_webhook_user_config(
        self, conn: asyncpg.Connection, tenant_id: str, user_email: str
    ) -> None:
        """Delete webhook user config from database."""
        await conn.execute(
            "DELETE FROM config WHERE key = $1",
            self.get_webhook_tenant_user_key(tenant_id, user_email),
        )

    async def insert_many_webhook_user_configs(
        self, conn: asyncpg.Connection, tenant_id: str, configs: dict
    ) -> None:
        """Insert many webhook user configs into database."""
        insert_values = []
        for user_email, config in configs.items():
            webbook_value = {
                "expiration": config["expiration"],
                "history_id": config["history_id"],
            }
            key = self.get_webhook_tenant_user_key(tenant_id, user_email)
            insert_values.append((key, json.dumps(webbook_value)))

        await conn.executemany(
            """
            INSERT INTO config (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key)
            DO UPDATE SET
                value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """,
            insert_values,
        )


# Singleton instance for use in cron jobs
webhook_manager = GoogleEmailWebhookManager()
