"""
Notion webhook handler for live document processing.

Handles Notion webhook events and converts them into structured documents
for storage and embedding generation.
"""

import hashlib
import hmac
import json
import logging

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.size_formatting import format_size

logger = logging.getLogger(__name__)


class NotionWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for Notion webhooks using HMAC-SHA256 signatures."""

    source_type = "notion"
    verify_func = staticmethod(lambda h, b, s: verify_notion_webhook(h, b, s))


def verify_notion_webhook(headers: dict[str, str], body: bytes, secret: str) -> None:
    """Verify Notion webhook signature."""
    if not secret:
        return

    signature = headers.get("x-notion-signature", "")

    if not signature.startswith("sha256="):
        raise ValueError("Invalid Notion signature format")

    # Calculate expected signature using signing secret and body
    expected_signature = (
        "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    )

    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("Notion webhook signature verification failed")


def extract_notion_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from Notion webhook for observability.

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
        # Try to parse the JSON payload
        try:
            payload = json.loads(body_str)
        except (json.JSONDecodeError, ValueError):
            metadata["parse_error"] = "Failed to parse JSON"
            return metadata

        # Handle verification token first (single field payload for webhook setup)
        if "verification_token" in payload and len(payload) == 1:
            metadata["event_type"] = "verification_token"
            metadata["entity_type"] = "verification_token"
            # Don't log the actual token (sensitive)
            return metadata

        # Extract common webhook event properties documented by Notion
        metadata["id"] = payload.get("id", "")
        metadata["time"] = payload.get("timestamp", "")
        metadata["type"] = payload.get("type", "unknown")
        metadata["workspace_id"] = payload.get("workspace_id", "")
        metadata["subscription_id"] = payload.get("subscription_id", "")
        metadata["integration_id"] = payload.get("integration_id", "")
        metadata["attempt_number"] = payload.get("attempt_number", 0)

        # Extract entity information (ID and type of object that triggered the event)
        if entity := payload.get("entity"):
            metadata["entity_type"] = entity.get("type", "unknown")
            metadata["entity_id"] = entity.get("id", "")

        # Extract authors information (who performed the action)
        if authors := payload.get("authors"):
            metadata["author_count"] = len(authors)
            # Extract first author for primary tracking
            if authors and len(authors) > 0:
                first_author = authors[0]
                metadata["primary_author_id"] = first_author.get("id", "")
                metadata["primary_author_type"] = first_author.get("type", "")

    except Exception as e:
        # Log but don't fail
        logger.error(f"Error extracting Notion webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata
