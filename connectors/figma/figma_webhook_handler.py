"""
Figma webhook verification utilities.

Handles verification of Figma webhook signatures using HMAC-SHA256.
"""

import hashlib
import hmac
import json
import logging

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.size_formatting import format_size

logger = logging.getLogger(__name__)


def verify_figma_webhook(headers: dict[str, str], body: bytes, secret: str | None) -> None:
    """Verify Figma webhook signature using HMAC-SHA256.

    Figma signs webhooks using HMAC-SHA256 with the passcode provided when
    creating the webhook. The signature is provided in the X-Figma-Signature header.

    Args:
        headers: HTTP headers from the webhook request
        body: Raw request body as bytes
        secret: Webhook passcode from webhook creation

    Raises:
        ValueError: If secret is missing, signature is missing, or signature is invalid
    """
    if not secret:
        raise ValueError("Missing Figma webhook signing secret - cannot verify webhook")

    # Get signature from header (case-insensitive header lookup)
    signature = headers.get("x-figma-signature") or headers.get("figma-signature", "")

    if not signature:
        raise ValueError("Missing Figma webhook signature header")

    # Calculate expected signature using HMAC-SHA256
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature.lower(), expected.lower()):
        raise ValueError("Invalid Figma webhook signature")


class FigmaWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for Figma webhooks using HMAC-SHA256 signatures."""

    source_type = "figma"
    verify_func = staticmethod(lambda h, b, s: verify_figma_webhook(h, b, s))


def extract_figma_team_id(body_str: str) -> str | None:
    """Extract Figma team ID from webhook payload.

    Figma webhooks include team_id in the payload for team-level webhooks.

    Args:
        body_str: Webhook body as string

    Returns:
        Team ID if found and valid, None otherwise
    """
    try:
        payload = json.loads(body_str)
        team_id = payload.get("team_id")
        if team_id and isinstance(team_id, str) and team_id.strip():
            return team_id.strip()
        return None
    except (json.JSONDecodeError, ValueError, KeyError):
        logger.warning("Failed to extract Figma team ID from webhook payload")
        return None


def extract_figma_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from Figma webhook for observability.

    Figma webhook payload structure:
    {
        "event_type": "FILE_UPDATE" | "FILE_DELETE" | "FILE_COMMENT" | "LIBRARY_PUBLISH",
        "passcode": "...",
        "timestamp": "...",
        "webhook_id": "...",
        "file_key": "...",
        "file_name": "...",
        "team_id": "...",
        "project_id": "...",
        ...event-specific fields
    }

    Args:
        headers: Webhook headers
        body_str: Webhook body as string

    Returns:
        Dictionary containing extracted metadata with at least payload_size
    """
    metadata: dict[str, str | int | bool] = {
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

        # Extract event type (FILE_UPDATE, FILE_DELETE, FILE_COMMENT, LIBRARY_PUBLISH)
        if event_type := payload.get("event_type"):
            metadata["event_type"] = event_type

        # Extract webhook_id
        if webhook_id := payload.get("webhook_id"):
            metadata["webhook_id"] = webhook_id

        # Extract timestamp
        if timestamp := payload.get("timestamp"):
            metadata["timestamp"] = timestamp

        # Extract file information
        if file_key := payload.get("file_key"):
            metadata["file_key"] = file_key

        if file_name := payload.get("file_name"):
            metadata["file_name"] = file_name

        # Extract team and project context
        if team_id := payload.get("team_id"):
            metadata["team_id"] = team_id

        if project_id := payload.get("project_id"):
            metadata["project_id"] = project_id

        # For FILE_COMMENT events, extract comment-specific info
        if payload.get("event_type") == "FILE_COMMENT":
            if comment_id := payload.get("comment_id"):
                metadata["comment_id"] = comment_id
            # comments array contains the comment data
            comments = payload.get("comments", [])
            if comments:
                metadata["comment_count"] = len(comments)

        # For LIBRARY_PUBLISH events
        if payload.get("event_type") == "LIBRARY_PUBLISH":
            if created_components := payload.get("created_components"):
                metadata["created_components_count"] = len(created_components)
            if modified_components := payload.get("modified_components"):
                metadata["modified_components_count"] = len(modified_components)
            if deleted_components := payload.get("deleted_components"):
                metadata["deleted_components_count"] = len(deleted_components)

    except Exception as e:
        logger.error(f"Error extracting Figma webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata
