import json

from src.ingest.gatekeeper.verification import BaseSigningSecretVerifier
from src.utils.logging import get_logger
from src.utils.size_formatting import format_size

logger = get_logger(__name__)


class JiraWebhookVerifier(BaseSigningSecretVerifier):
    """Verifier for Jira webhooks using signing secret comparison."""

    source_type = "jira"
    verify_func = staticmethod(lambda h, b, s: verify_jira_webhook(h, b, s))


def verify_jira_webhook(headers: dict[str, str], body: bytes, secret: str) -> None:
    """Verify Jira webhook signature.

    Args:
        headers: HTTP headers from the webhook request
        body: Raw request body as bytes
        secret: Signing secret from SSM for verification
    """
    if not secret:
        return

    signing_secret_header = headers.get("x-jira-signing-secret")
    if signing_secret_header:
        if signing_secret_header != secret:
            raise ValueError("Invalid Jira signing secret - does not match stored SSM parameter")
        logger.debug("Successfully verified Forge app signing secret matches SSM stored value")
        return


def extract_jira_webhook_metadata(
    headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from Jira webhook for observability.

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

        if issue := payload.get("issue"):
            metadata["issue_key"] = issue.get("key", "")
            metadata["issue_id"] = issue.get("id", "")

            if project := issue.get("fields", {}).get("project"):
                metadata["project_key"] = project.get("key", "")
                metadata["project_id"] = project.get("id", "")

        if user := payload.get("user"):
            metadata["user_id"] = user.get("accountId", "")
            metadata["user_display_name"] = user.get("displayName", "")

        if comment := payload.get("comment"):
            metadata["comment_id"] = comment.get("id", "")
            if author := comment.get("author"):
                metadata["comment_author_id"] = author.get("accountId", "")

        if changelog := payload.get("changelog"):
            items = changelog.get("items", [])
            metadata["changelog_items_count"] = len(items)
            if items:
                changed_fields = [item.get("field", "") for item in items]
                metadata["changed_fields"] = ",".join(filter(None, changed_fields))

    except Exception as e:
        logger.error(f"Error extracting Jira webhook metadata: {e}")
        metadata["extraction_error"] = str(e)

    return metadata
