"""
Trello webhook verification and management utilities.

Handles verification of Trello webhook signatures and webhook configuration management.
"""

import base64
import hashlib
import hmac
import json
import logging

import asyncpg

from connectors.trello.trello_artifacts import TrelloWebhooksConfig
from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.ingest.gatekeeper.verification import VerificationResult
from src.utils.size_formatting import format_size

logger = logging.getLogger(__name__)


class TrelloWebhookVerifier:
    """Verifier for Trello webhooks using HMAC-SHA1 signatures.

    Note: Does not inherit from BaseSigningSecretVerifier because Trello's
    verification requires tenant_id to construct the callback URL used in
    signature verification.
    """

    def __init__(self) -> None:
        self.ssm_client = SSMClient()

    async def verify(
        self,
        headers: dict[str, str],
        body: bytes,
        tenant_id: str,
        request_url: str | None = None,
    ) -> VerificationResult:
        """Verify a Trello webhook for a given tenant."""
        del request_url  # unused for Trello
        signing_secret = await self.ssm_client.get_signing_secret(tenant_id, "trello")
        if not signing_secret:
            return VerificationResult(
                success=False,
                error=f"No signing secret configured for tenant {tenant_id}",
            )

        try:
            verify_trello_webhook(headers, body, tenant_id, signing_secret)
            return VerificationResult(success=True)
        except ValueError as e:
            return VerificationResult(success=False, error=str(e))


# Database config key for storing webhook configuration
TRELLO_WEBHOOKS_CONFIG_KEY = "TRELLO_WEBHOOKS"


def get_trello_webhook_callback_url(tenant_id: str) -> str:
    """Construct Trello webhook callback URL for a tenant.

    The callback URL is used both when registering webhooks with Trello
    and when verifying webhook signatures.

    Format: https://{tenant_id}.ingest.{base_domain}/webhooks/trello
    - Production (BASE_DOMAIN=getgrapevine.ai): {tenant}.ingest.getgrapevine.ai
    - Staging (BASE_DOMAIN=stg.getgrapevine.ai): {tenant}.ingest.stg.getgrapevine.ai

    Args:
        tenant_id: The tenant ID

    Returns:
        Fully qualified callback URL for Trello webhooks
    """
    from src.utils.config import get_base_domain

    base_domain = get_base_domain()
    return f"https://{tenant_id}.ingest.{base_domain}/webhooks/trello"


def verify_trello_webhook(
    headers: dict[str, str], body: bytes, tenant_id: str, secret: str
) -> None:
    """Verify Trello webhook signature.

    Trello uses HMAC-SHA1 with the callback URL + request body as the signed data.
    The signature is sent in the X-Trello-Webhook header as a base64-encoded value.

    Trello uses a global Power-Up OAuth secret (TRELLO_POWER_UP_SECRET) for all tenants,
    as described in: https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/

    Args:
        headers: Webhook headers
        body: Raw webhook body
        tenant_id: The tenant ID (used to construct callback URL)
        secret: Trello Power-Up OAuth secret for signature verification

    Raises:
        ValueError: If signature verification fails
    """
    if not secret:
        raise ValueError(
            "Trello Power-Up OAuth secret is required for webhook verification. "
            "Get your Power-Up OAuth secret from https://trello.com/power-ups/admin"
        )

    # Get signature from headers
    signature = headers.get("x-trello-webhook", "")
    if not signature:
        raise ValueError("Missing Trello webhook signature header")

    # Construct callback URL for signature verification
    callback_url = get_trello_webhook_callback_url(tenant_id)

    # Trello signature: base64(HMAC-SHA1(secret, body + callback_url))
    # See: https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/
    body_str = body.decode("utf-8") if isinstance(body, bytes) else body
    content = body_str + callback_url
    expected_bytes = hmac.new(
        secret.encode("utf-8"), content.encode("utf-8"), hashlib.sha1
    ).digest()
    expected_signature = base64.b64encode(expected_bytes).decode()

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Invalid Trello webhook signature")


def extract_trello_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from Trello webhook for observability.

    Safely extracts key information without failing webhook processing.

    Args:
        headers: Webhook headers
        body_str: Webhook body as string

    Returns:
        Dictionary containing extracted metadata with at least payload_size
    """
    metadata: dict[str, str | int] = {
        "payload_size": len(body_str),
        "payload_size_human": format_size(len(body_str)),
    }

    # Extract signature header if present (for debugging)
    if signature := headers.get("x-trello-webhook"):
        # Only log first 8 chars of signature for debugging
        metadata["signature_preview"] = signature[:8] + "..."

    try:
        # Try to parse the JSON payload
        try:
            payload = json.loads(body_str)
        except (json.JSONDecodeError, ValueError):
            metadata["parse_error"] = "Failed to parse JSON"
            return metadata

        # Extract action type
        action = payload.get("action", {})
        action_type = action.get("type", "unknown")
        metadata["action_type"] = action_type

        # Extract model information
        model = payload.get("model", {})
        if "id" in model:
            metadata["model_id"] = model["id"]

        # Extract IDs from action data
        action_data = action.get("data", {})

        # Card ID (for card-related events)
        card = action_data.get("card", {})
        if card and "id" in card:
            metadata["card_id"] = card["id"]
            if "name" in card:
                metadata["card_name"] = card["name"]

        # Board ID (for board-related events)
        board = action_data.get("board", {})
        if board and "id" in board:
            metadata["board_id"] = board["id"]
            if "name" in board:
                metadata["board_name"] = board["name"]

        # List ID (for list-related events)
        list_data = action_data.get("list", {})
        if list_data and "id" in list_data:
            metadata["list_id"] = list_data["id"]

    except Exception as e:
        # Log but don't fail
        logger.error(f"Error extracting Trello webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata


# Webhook configuration management


async def get_webhook_config(tenant_id: str) -> TrelloWebhooksConfig | None:
    """Get Trello webhook configuration for a tenant.

    Args:
        tenant_id: The tenant ID

    Returns:
        TrelloWebhooksConfig if exists, None otherwise
    """
    try:
        async with tenant_db_manager.acquire_connection(tenant_id) as conn:
            config_row = await conn.fetchrow(
                "SELECT value FROM config WHERE key = $1", TRELLO_WEBHOOKS_CONFIG_KEY
            )

            if not config_row:
                logger.debug(f"Tenant {tenant_id} has no Trello webhook config")
                return None

            return TrelloWebhooksConfig.from_json(config_row["value"])

    except Exception as e:
        logger.error(f"Failed to get Trello webhook config for tenant {tenant_id}: {e}")
        return None


async def store_webhook_config(tenant_id: str, webhook_config: TrelloWebhooksConfig) -> None:
    """Store Trello webhook configuration for a tenant.

    Args:
        tenant_id: The tenant ID
        webhook_config: The webhook configuration to store

    Raises:
        Exception: If storing the configuration fails
    """
    try:
        async with tenant_db_manager.acquire_connection(tenant_id) as conn:
            await _update_webhook_config(conn, webhook_config, tenant_id)

    except Exception as e:
        logger.error(f"Failed to store Trello webhook config for tenant {tenant_id}: {e}")
        raise


async def clear_webhook_config(tenant_id: str) -> None:
    """Clear Trello webhook configuration for a tenant.

    Args:
        tenant_id: The tenant ID

    Raises:
        Exception: If clearing the configuration fails
    """
    try:
        async with tenant_db_manager.acquire_connection(tenant_id) as conn:
            await _clear_webhook_config(conn)
            logger.info(f"Cleared Trello webhook config for tenant {tenant_id}")

    except Exception as e:
        logger.error(f"Failed to clear Trello webhook config for tenant {tenant_id}: {e}")
        raise


async def _update_webhook_config(
    conn: asyncpg.Connection,
    webhook_config: TrelloWebhooksConfig,
    tenant_id: str,
) -> None:
    """Update webhook config in database.

    Args:
        conn: Database connection
        webhook_config: The webhook configuration to store
        tenant_id: The tenant ID (for logging)
    """
    if webhook_config.has_webhook:
        await conn.execute(
            """
            INSERT INTO config (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """,
            TRELLO_WEBHOOKS_CONFIG_KEY,
            webhook_config.to_json(),
        )

        logger.info(
            f"Stored member webhook configuration (webhook_id: {webhook_config.webhook_id}) "
            f"for member '{webhook_config.member_username}' ({webhook_config.member_id}) "
            f"for tenant {tenant_id}"
        )
    else:
        await _clear_webhook_config(conn)
        logger.info(f"Cleared webhook config for tenant {tenant_id} (no active webhook)")


async def _clear_webhook_config(conn: asyncpg.Connection) -> None:
    """Clear webhook configuration from database.

    Args:
        conn: Database connection
    """
    await conn.execute("DELETE FROM config WHERE key = $1", TRELLO_WEBHOOKS_CONFIG_KEY)
