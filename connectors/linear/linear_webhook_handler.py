"""
Linear webhook verification utilities.

Handles verification of Linear webhook signatures and security checks.
"""

import hashlib
import hmac
import json
import logging
import time

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.size_formatting import format_size

logger = logging.getLogger(__name__)


class LinearWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for Linear webhooks using HMAC-SHA256 signatures."""

    source_type = "linear"
    verify_func = staticmethod(lambda h, b, s: verify_linear_webhook(h, b, s))


# Linear's webhook server IP addresses as documented in their security guide
# https://linear.app/developers/webhooks#securing-webhooks
LINEAR_WEBHOOK_IPS = {"35.231.147.226", "35.243.134.228", "34.140.253.14", "34.38.87.206"}


def verify_linear_webhook(
    headers: dict[str, str], body: bytes, secret: str, client_ip: str | None = None
) -> None:
    """Verify webhook signature and timestamp."""
    if not secret:
        return

    signature = headers.get("linear-signature", "")
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid Linear webhook signature")

    try:
        payload = json.loads(body.decode("utf-8"))
        webhook_timestamp = payload.get("webhookTimestamp")
        if webhook_timestamp:
            if webhook_timestamp > 1e12:
                webhook_timestamp = webhook_timestamp / 1000

            time_diff = abs(time.time() - webhook_timestamp)
            if time_diff > 60:
                raise ValueError("Webhook timestamp too old - potential replay attack")
    except json.JSONDecodeError:
        pass


def extract_linear_organization_id(body_str: str) -> str | None:
    """Extract Linear organization ID from webhook payload.

    Args:
        body_str: Webhook body as string

    Returns:
        Organization ID if found and valid (non-empty string), None otherwise
    """
    try:
        payload = json.loads(body_str)
        org_id = payload.get("organizationId")

        # Validate that org_id is a non-empty string
        if org_id and isinstance(org_id, str) and org_id.strip():
            return org_id.strip()

        return None
    except (json.JSONDecodeError, ValueError, KeyError):
        logger.warning("Failed to extract Linear organization ID from webhook payload")
        return None


def extract_linear_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from Linear webhook for observability.

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

    try:
        # Extract common delivery headers documented by Linear (before parsing body)
        metadata["delivery_id"] = headers.get("linear-delivery", "")
        metadata["event_type"] = headers.get("linear-event", "unknown")

        # Try to parse the JSON payload
        try:
            payload = json.loads(body_str)
        except (json.JSONDecodeError, ValueError):
            metadata["parse_error"] = "Failed to parse JSON"
            return metadata

        # Extract documented common fields present on all Linear webhook events
        metadata["action"] = payload.get("action", "")
        metadata["type"] = payload.get("type", "")
        metadata["created_at"] = payload.get("createdAt", "")
        metadata["url"] = payload.get("url", "")
        metadata["webhook_timestamp"] = payload.get("webhookTimestamp", "")
        metadata["webhook_id"] = payload.get("webhookId", "")

        # Extract organization ID for OAuth webhook routing
        if org_id := payload.get("organizationId"):
            metadata["organization_id"] = org_id

        # Extract actor information (who triggered the action)
        if actor := payload.get("actor"):
            metadata["actor_id"] = actor.get("id", "")
            metadata["actor_type"] = actor.get("type", "")  # User, OauthClient, or Integration

        # For update actions, track if there were previous values
        if updated_from := payload.get("updatedFrom"):
            metadata["has_updates"] = True
            metadata["updated_fields_count"] = (
                len(updated_from) if isinstance(updated_from, dict) else 0
            )

        # Extract basic entity information from the data object
        if data := payload.get("data"):
            # Entity type is from the type field
            metadata["entity_type"] = payload.get("type", "unknown").lower()

            # Entity ID from data.id when data is a dict
            if isinstance(data, dict):
                metadata["entity_id"] = data.get("id", "")

    except Exception as e:
        # Log but don't fail
        logger.error(f"Error extracting Linear webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata
