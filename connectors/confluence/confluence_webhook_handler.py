import json

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.logging import get_logger
from src.utils.size_formatting import format_size

logger = get_logger(__name__)


class ConfluenceWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for Confluence webhooks using signing secret comparison."""

    source_type = "confluence"
    verify_func = staticmethod(lambda h, b, s: verify_confluence_webhook(h, b, s))


def verify_confluence_webhook(headers: dict[str, str], body: bytes, secret: str) -> None:
    """Verify Confluence webhook signature.

    Args:
        headers: HTTP headers from the webhook request
        body: Raw request body as bytes
        secret: Signing secret from SSM for verification
    """
    if not secret:
        return

    signing_secret_header = headers.get("x-confluence-signing-secret")
    if signing_secret_header:
        if signing_secret_header != secret:
            raise ValueError(
                "Invalid Confluence signing secret - does not match stored SSM parameter"
            )
        logger.debug("Successfully verified Forge app signing secret matches SSM stored value")
        return


def extract_confluence_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from Confluence webhook for observability.

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
        metadata["atlassian_token"] = headers.get("x-atlassian-token", "")
        metadata["user_agent"] = headers.get("user-agent", "")

        try:
            payload = json.loads(body_str)
        except (json.JSONDecodeError, ValueError):
            metadata["parse_error"] = "Failed to parse JSON"
            return metadata

        metadata["event_type"] = payload.get("eventType", "unknown")
        metadata["cloud_id"] = payload.get("cloudId", "")
        metadata["installation_id"] = payload.get("installationId", "")

        # Extract page information
        if page := payload.get("page"):
            metadata["page_id"] = page.get("id", "")
            metadata["page_title"] = page.get("title", "")

            if space := page.get("space"):
                metadata["space_key"] = space.get("key", "")
                metadata["space_id"] = space.get("id", "")
                metadata["space_name"] = space.get("name", "")

        # Extract space information (for space events)
        if space := payload.get("space"):
            metadata["space_key"] = space.get("key", "")
            metadata["space_id"] = space.get("id", "")
            metadata["space_name"] = space.get("name", "")

        # Extract user information
        if user := payload.get("user"):
            metadata["user_id"] = user.get("accountId", "")
            metadata["user_display_name"] = user.get("displayName", "")

        # Extract comment information (for comment events)
        if comment := payload.get("comment"):
            metadata["comment_id"] = comment.get("id", "")
            if author := comment.get("author"):
                metadata["comment_author_id"] = author.get("accountId", "")
                metadata["comment_author_name"] = author.get("displayName", "")

        # Extract version information (for page update events)
        if version := payload.get("version"):
            metadata["version_number"] = version.get("number", "")
            if version_by := version.get("by"):
                metadata["version_author_id"] = version_by.get("accountId", "")
                metadata["version_author_name"] = version_by.get("displayName", "")

    except Exception as e:
        logger.error(f"Error extracting Confluence webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata
