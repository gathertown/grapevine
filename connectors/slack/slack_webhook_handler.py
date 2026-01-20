"""
Slack webhook handler for processing real-time message events.
"""

import hashlib
import hmac
import json
import logging
import time

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.size_formatting import format_size

logger = logging.getLogger(__name__)


class SlackWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for Slack webhooks using HMAC-SHA256 signatures."""

    source_type = "slack"
    verify_func = staticmethod(lambda h, b, s: verify_slack_webhook(h, b, s))


def verify_slack_webhook(headers: dict[str, str], body: bytes, secret: str) -> None:
    """Verify Slack webhook signature and timestamp."""
    if not secret:
        return

    # Extract timestamp and signature from headers
    timestamp = headers.get("x-slack-request-timestamp")
    slack_signature = headers.get("x-slack-signature")

    if not timestamp or not slack_signature:
        raise ValueError("Missing required Slack signature headers")

    # Check timestamp to prevent replay attacks (within 5 minutes)
    try:
        request_time = int(timestamp)
        if abs(time.time() - request_time) > 60 * 5:
            raise ValueError("Slack request timestamp too old - potential replay attack")
    except ValueError:
        raise ValueError("Invalid timestamp format in Slack request")

    # Create signature base string: version:timestamp:body
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"

    # Compute HMAC-SHA256 signature
    expected_signature = (
        "v0="
        + hmac.new(
            secret.encode("utf-8"), sig_basestring.encode("utf-8"), hashlib.sha256
        ).hexdigest()
    )

    # Compare signatures using constant-time comparison
    if not hmac.compare_digest(expected_signature, slack_signature):
        raise ValueError("Slack webhook signature verification failed")


def extract_slack_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from Slack webhook for observability.

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
        # Extract Slack retry headers (if present)
        if retry_num := headers.get("x-slack-retry-num"):
            metadata["retry_num"] = retry_num
        if retry_reason := headers.get("x-slack-retry-reason"):
            metadata["retry_reason"] = retry_reason

        # Try to parse the JSON payload
        try:
            payload = json.loads(body_str)
        except (json.JSONDecodeError, ValueError):
            metadata["parse_error"] = "Failed to parse JSON"
            return metadata

        # Extract common callback fields documented by Slack
        metadata["team_id"] = payload.get("team_id", "")
        metadata["api_app_id"] = payload.get("api_app_id", "")
        metadata["type"] = payload.get("type", "unknown")
        metadata["event_id"] = payload.get("event_id", "")
        metadata["event_time"] = payload.get("event_time", 0)
        metadata["event_context"] = payload.get("event_context", "")

        # Handle URL verification challenge
        if payload.get("type") == "url_verification":
            metadata["entity_type"] = "url_verification"
            # Don't include challenge token (sensitive)
            return metadata

        # Extract common inner event fields documented by Slack
        if event := payload.get("event"):
            # Common fields present in all inner event types
            metadata["entity_type"] = event.get("type", "unknown")
            metadata["event_ts"] = event.get("event_ts", "")
            metadata["ts"] = event.get("ts", "")

            # User field (not included in all events, but common when present)
            if user := event.get("user"):
                metadata["user"] = user

            # Extract basic entity ID - typically channel for most events
            if channel := event.get("channel"):
                metadata["entity_id"] = channel

    except Exception as e:
        # Log but don't fail
        logger.error(f"Error extracting Slack webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata
