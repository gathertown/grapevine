"""HubSpot webhook service utilities."""

import base64
import hmac
import json
import logging
import time
from typing import Any, TypedDict

from src.ingest.gatekeeper.verification import VerificationResult
from src.utils.config import get_config_value
from src.utils.size_formatting import format_size

logger = logging.getLogger(__name__)


class HubSpotWebhookVerifier:
    """Verifier for HubSpot webhooks using HMAC-SHA256 signatures.

    Note: Does not inherit from BaseSigningSecretVerifier because HubSpot:
    1. Uses a global client secret from env (not per-tenant from SSM)
    2. Requires the full request URL in the signature verification
    """

    async def verify(
        self,
        headers: dict[str, str],
        body: bytes,
        tenant_id: str,
        request_url: str | None = None,
    ) -> VerificationResult:
        """Verify a HubSpot webhook."""
        del tenant_id  # HubSpot uses global secret, not per-tenant
        if not request_url:
            return VerificationResult(
                success=False,
                error="HubSpot verification requires request_url",
            )

        try:
            verify_hubspot_webhook(request_url, headers, body)
            return VerificationResult(success=True)
        except ValueError as e:
            return VerificationResult(success=False, error=str(e))


class AssociationChanges(TypedDict):
    companies: set[str]
    deals: set[str]
    tickets: set[str]
    contacts: set[str]


class PortalEvents(TypedDict):
    companies: set[str]
    deals: set[str]
    tickets: set[str]
    contacts: set[str]
    association_changes: AssociationChanges


def verify_hubspot_webhook(request_url: str, headers: dict[str, str], body: bytes) -> None:
    """Verify HubSpot webhook signature v3.

    Args:
        request_url: Full request URL
        headers: Webhook headers containing signature and timestamp
        body: Raw request body

    Raises:
        ValueError: If signature verification fails or timestamp is too old
    """
    # Get timestamp and signature headers
    timestamp_header = headers.get("x-hubspot-request-timestamp")
    signature_header = headers.get("x-hubspot-signature-v3")

    if not timestamp_header:
        raise ValueError("Missing X-HubSpot-Request-Timestamp header")

    if not signature_header:
        raise ValueError("Missing X-HubSpot-Signature-v3 header")

    # Validate timestamp (must be within 5 minutes) #TEMP ASEEL COMMENT BACK IN
    try:
        request_timestamp = int(timestamp_header)
        current_time_ms = int(time.time() * 1000)

        if current_time_ms - request_timestamp > 300000:  # 5 minutes in milliseconds
            raise ValueError("Request timestamp too old (more than 5 minutes)")
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid timestamp header: {e}")

    # Get client secret from environment
    secret = get_config_value("HUBSPOT_CLIENT_SECRET")
    if not secret:
        raise ValueError("HUBSPOT_CLIENT_SECRET not configured")

    # Decode URL-encoded characters as per HubSpot requirements
    # Note: We don't decode the ? that denotes the query string
    url_replacements = {
        "%3A": ":",
        "%2F": "/",
        "%3F": "?",
        "%40": "@",
        "%21": "!",
        "%24": "$",
        "%27": "'",
        "%28": "(",
        "%29": ")",
        "%2A": "*",
        "%2C": ",",
        "%3B": ";",
    }

    decoded_url = request_url
    for encoded, decoded in url_replacements.items():
        decoded_url = decoded_url.replace(encoded, decoded)

    # Create the source string: method + uri + body + timestamp
    body_str = body.decode("utf-8")
    source_string = f"POST{decoded_url}{body_str}{timestamp_header}"

    # Create HMAC SHA-256 hash
    hash_obj = hmac.new(secret.encode("utf-8"), source_string.encode("utf-8"), digestmod="sha256")

    # Base64 encode the hash
    computed_signature = base64.b64encode(hash_obj.digest()).decode("utf-8")

    # Use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(computed_signature, signature_header):
        raise ValueError("HubSpot webhook signature verification failed")

    logger.info("HubSpot signature verification successful")


def deduplicate_hubspot_events(
    events: list[dict[str, Any]],
) -> dict[str, PortalEvents]:
    """Deduplicate HubSpot webhook events by portal and object.

    HubSpot sends multiple events for the same object (e.g., 9 events for 1 deal creation).
    This function groups events by portal and extracts unique object IDs.

    Args:
        events: List of HubSpot webhook events

    Returns:
        Dictionary mapping portal_id to sets of unique company and deal IDs
        Format: {portal_id: {"companies": set(), "deals": set(), "association_changes": {"companies": set(), "deals": set()}}}
    """
    events_by_portal: dict[str, PortalEvents] = {}

    for event in events:
        # Extract portal_id (required for tenant resolution)
        portal_id = event.get("portalId")
        if not portal_id:
            logger.warning(f"Event missing portalId: {event}")
            continue

        # Portal ID will be used by caller to resolve tenant
        portal_key = str(portal_id)

        # Initialize portal's object sets
        if portal_key not in events_by_portal:
            events_by_portal[portal_key] = {
                "companies": set(),
                "deals": set(),
                "tickets": set(),
                "contacts": set(),
                "association_changes": {
                    "companies": set(),
                    "deals": set(),
                    "contacts": set(),
                    "tickets": set(),
                },
            }

        subscription_type = event.get("subscriptionType")

        # Handle property changes, creation, deletion events
        if subscription_type in ["object.creation", "object.deletion"]:
            object_id = event.get("objectId")
            object_type_id = event.get("objectTypeId")

            if object_id and object_type_id:
                if object_type_id == "0-2":  # Company
                    events_by_portal[portal_key]["companies"].add(str(object_id))
                elif object_type_id == "0-3":  # Deal
                    events_by_portal[portal_key]["deals"].add(str(object_id))
                elif object_type_id == "0-5":  # Ticket
                    events_by_portal[portal_key]["tickets"].add(str(object_id))
                elif object_type_id == "0-1":  # Contact
                    events_by_portal[portal_key]["contacts"].add(str(object_id))

        # Handle association changes - only process DEAL_TO_COMPANY to avoid duplication
        elif subscription_type == "object.associationChange":
            association_type = event.get("associationType")

            if association_type == "DEAL_TO_COMPANY":
                # For DEAL_TO_COMPANY, fromObjectId is the deal
                deal_id = event.get("fromObjectId")
                if deal_id:
                    events_by_portal[portal_key]["deals"].add(str(deal_id))
                    # Also track that this deal had an association change
                    events_by_portal[portal_key]["association_changes"]["deals"].add(str(deal_id))
            # Skip COMPANY_TO_DEAL to avoid processing the same association twice

    return events_by_portal


def extract_hubspot_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int]:
    """Extract metadata from HubSpot webhook for observability.

    Reports raw event counts without deduplication.
    Actual deduplication happens in deduplicate_hubspot_events.

    Args:
        headers: Webhook headers
        body_str: Webhook body as string

    Returns:
        Dictionary containing extracted metadata
    """
    metadata: dict[str, str | int] = {
        "payload_size": len(body_str),
        "payload_size_human": format_size(len(body_str)),
    }

    # Extract HubSpot-specific headers
    metadata["signature_version"] = "v3" if headers.get("x-hubspot-signature-v3") else ""
    metadata["request_timestamp"] = headers.get("x-hubspot-request-timestamp", "")
    metadata["user_agent"] = headers.get("user-agent", "")

    # Parse the JSON payload (trust HubSpot to send valid JSON)
    events = json.loads(body_str)

    # Count raw events by type
    event_counts: dict[str, int] = {}
    portal_ids = set()

    for event in events:
        # Track portal IDs
        if portal_id := event.get("portalId"):
            portal_ids.add(str(portal_id))

        # Count subscription types
        if subscription_type := event.get("subscriptionType"):
            event_counts[subscription_type] = event_counts.get(subscription_type, 0) + 1

    metadata["event_count"] = len(events)
    metadata["event_types"] = ", ".join(f"{k}:{v}" for k, v in event_counts.items())
    metadata["portal_ids"] = ", ".join(portal_ids)

    return metadata
