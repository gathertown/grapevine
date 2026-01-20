import hashlib
import hmac
import json
import logging

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.size_formatting import format_size

logger = logging.getLogger(__name__)


class GitHubWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for GitHub webhooks using HMAC-SHA256 signatures."""

    source_type = "github"
    verify_func = staticmethod(lambda h, b, s: verify_github_webhook(h, b, s))


def verify_github_webhook(headers: dict[str, str], body: bytes, secret: str) -> None:
    """Verify GitHub webhook signature."""
    if not secret:
        return

    signature = headers.get("x-hub-signature-256", "")
    if not signature:
        raise ValueError("Missing X-Hub-Signature-256 header - ensure webhook secret is configured")

    if not signature.startswith("sha256="):
        raise ValueError("Invalid signature format - expected sha256= prefix")

    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise ValueError("GitHub webhook signature verification failed")


def extract_github_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from GitHub webhook for observability.

    Safely extracts key information without failing webhook processing.
    Excludes names of all kinds to avoid logging PII

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
        # Extract common delivery headers documented by GitHub
        metadata["hook_id"] = headers.get("x-github-hook-id", "")
        metadata["event_type"] = headers.get("x-github-event", "unknown")
        metadata["delivery_id"] = headers.get("x-github-delivery", "")
        metadata["hook_installation_target_type"] = headers.get(
            "x-github-hook-installation-target-type", ""
        )
        metadata["hook_installation_target_id"] = headers.get(
            "x-github-hook-installation-target-id", ""
        )
        metadata["user_agent"] = headers.get("user-agent", "")

        # Try to parse the JSON payload
        try:
            payload = json.loads(body_str)
        except (json.JSONDecodeError, ValueError):
            metadata["parse_error"] = "Failed to parse JSON"
            return metadata

        # Extract common payload fields present in most GitHub webhooks
        metadata["action"] = payload.get("action", "")

        # Repository information (present in most events)
        if repository := payload.get("repository"):
            metadata["repository_id"] = repository.get("id", "")
            metadata["entity_id"] = str(
                repository.get("id", "")
            )  # Use repo ID as fallback entity_id

        # Sender information (present in most events)
        if sender := payload.get("sender"):
            metadata["sender_id"] = sender.get("id", "")
            metadata["sender_type"] = sender.get("type", "")

        # Installation information (for app events)
        if installation := payload.get("installation"):
            metadata["installation_id"] = installation.get("id", "")

    except Exception as e:
        # Log but don't fail
        logger.error(f"Error extracting GitHub webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata
