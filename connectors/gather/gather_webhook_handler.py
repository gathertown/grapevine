"""
Gather webhook verification utilities.

Handles verification of Gather webhook signatures and security checks.
"""

import hashlib
import hmac
import json
import logging

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.size_formatting import format_size

logger = logging.getLogger(__name__)


class GatherWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for Gather webhooks using HMAC-SHA256 signatures."""

    source_type = "gather"
    verify_func = staticmethod(lambda h, b, s: verify_gather_webhook(h, b, s))


def verify_gather_webhook(headers: dict[str, str], body: bytes, secret: str) -> None:
    """Verify Gather webhook signature.

    Args:
        headers: Webhook headers
        body: Raw webhook body
        secret: Signing secret from SSM

    Raises:
        ValueError: If signature verification fails
    """
    if not secret:
        raise ValueError("No signing secret configured for Gather webhooks")

    # Get signature from headers (adjust header name based on Gather's documentation)
    signature = headers.get("x-gather-signature", "")
    if not signature:
        raise ValueError("Missing Gather webhook signature header")

    # Compute expected signature using HMAC-SHA256
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    # Constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid Gather webhook signature")


def extract_gather_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from Gather webhook for observability.

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
        # Extract event type from header
        event_type = headers.get("x-gather-event", "unknown")
        metadata["event_type"] = event_type

        # Try to parse the JSON payload
        try:
            payload = json.loads(body_str)
        except (json.JSONDecodeError, ValueError):
            metadata["parse_error"] = "Failed to parse JSON"
            return metadata

        # Extract fields from Gather webhook payload
        # Structure: { "data": { "meetingId": "...", "spaceId": "...", ... } }
        data = payload.get("data", {})

        if "meetingId" in data:
            metadata["meeting_id"] = data["meetingId"]

        if "spaceId" in data:
            metadata["space_id"] = data["spaceId"]

        # For MeetingTranscriptCompleted events, extract memo info
        if event_type == "MeetingTranscriptCompleted" and "meetingMemo" in data:
            memo = data["meetingMemo"]
            if "id" in memo:
                metadata["memo_id"] = memo["id"]

        # For MeetingEnded events, extract meeting details
        if event_type == "MeetingEnded":
            if "type" in data:
                metadata["meeting_type"] = data["type"]
            if "visibility" in data:
                metadata["meeting_visibility"] = data["visibility"]
            if "participants" in data:
                metadata["participant_count"] = len(data["participants"])

    except Exception as e:
        # Log but don't fail
        logger.error(f"Error extracting Gather webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata
