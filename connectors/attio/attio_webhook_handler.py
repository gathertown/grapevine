"""
Attio webhook verification utilities.

Handles verification of Attio webhook signatures.
"""

import hashlib
import hmac
import json
import logging

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.size_formatting import format_size

logger = logging.getLogger(__name__)


def verify_attio_webhook(headers: dict[str, str], body: bytes, secret: str | None) -> None:
    """Verify Attio webhook signature using SHA256 HMAC.

    Attio signs webhooks using SHA256 HMAC with the webhook secret.
    The signature is provided in the Attio-Signature header as a hex string.

    Args:
        headers: HTTP headers from the webhook request
        body: Raw request body as bytes
        secret: Webhook secret from webhook creation response

    Raises:
        ValueError: If secret is missing, signature is missing, or signature is invalid
    """
    if not secret:
        raise ValueError("Missing Attio webhook signing secret - cannot verify webhook")

    # Get signature from header (Attio-Signature or X-Attio-Signature for legacy)
    signature = headers.get("attio-signature") or headers.get("x-attio-signature", "")

    if not signature:
        raise ValueError("Missing Attio webhook signature header")

    # Calculate expected signature using SHA256 HMAC
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise ValueError("Invalid Attio webhook signature")


class AttioWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for Attio webhooks using HMAC-SHA256 signatures."""

    source_type = "attio"
    verify_func = staticmethod(lambda h, b, s: verify_attio_webhook(h, b, s))


def extract_attio_workspace_id(body_str: str) -> str | None:
    """Extract Attio workspace ID from webhook payload.

    Attio webhooks have a wrapper structure:
    {
        "webhook_id": "...",
        "events": [
            {"event_type": "...", "id": {"workspace_id": "...", ...}, ...}
        ]
    }

    Args:
        body_str: Webhook body as string

    Returns:
        Workspace ID if found and valid, None otherwise
    """
    try:
        payload = json.loads(body_str)

        # Workspace ID is in the first event's id.workspace_id field
        events = payload.get("events", [])
        if events and len(events) > 0:
            first_event = events[0]
            id_obj = first_event.get("id", {})
            workspace_id = id_obj.get("workspace_id")

            if workspace_id and isinstance(workspace_id, str) and workspace_id.strip():
                return workspace_id.strip()

        return None
    except (json.JSONDecodeError, ValueError, KeyError):
        logger.warning("Failed to extract Attio workspace ID from webhook payload")
        return None


def extract_attio_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from Attio webhook for observability.

    Attio webhooks have a wrapper structure:
    {
        "webhook_id": "...",
        "events": [
            {"event_type": "...", "id": {...}, "actor": {...}}
        ]
    }

    Safely extracts key information without failing webhook processing.

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

        # Extract webhook_id
        if webhook_id := payload.get("webhook_id"):
            metadata["webhook_id"] = webhook_id

        # Extract events array
        events = payload.get("events", [])
        metadata["event_count"] = len(events)

        # Extract metadata from first event (for observability)
        if events and len(events) > 0:
            first_event = events[0]

            # Extract event type (e.g., record.created, record.updated, note.created)
            event_type = first_event.get("event_type", "")
            if event_type:
                metadata["event_type"] = event_type

            # Extract actor information (who triggered the event)
            actor = first_event.get("actor", {})
            if actor:
                metadata["actor_type"] = actor.get("type", "")
                if actor_id := actor.get("id"):
                    metadata["actor_id"] = actor_id

            # Extract object and record information from id object
            id_obj = first_event.get("id", {})
            if id_obj and isinstance(id_obj, dict):
                if workspace_id := id_obj.get("workspace_id"):
                    metadata["workspace_id"] = workspace_id
                if object_id := id_obj.get("object_id"):
                    metadata["object_type"] = object_id
                if record_id := id_obj.get("record_id"):
                    metadata["record_id"] = record_id

                # For notes, extract note_id
                if note_id := id_obj.get("note_id"):
                    metadata["note_id"] = note_id

                # For tasks, extract task_id
                if task_id := id_obj.get("task_id"):
                    metadata["task_id"] = task_id

                # For record.updated, extract attribute_id
                if attribute_id := id_obj.get("attribute_id"):
                    metadata["attribute_id"] = attribute_id

    except Exception as e:
        logger.error(f"Error extracting Attio webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata
