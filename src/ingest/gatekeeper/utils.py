"""Utility functions for gatekeeper service."""

import json
import logging
import time
import urllib.parse

from src.clients.ssm import SSMClient
from src.database.connector_installations import (
    ConnectorInstallationsRepository,
    ConnectorType,
)
from src.ingest.gatekeeper.models import TenantFromHostResult
from src.utils.config import get_config_value

logger = logging.getLogger(__name__)


def get_base_domain() -> str:
    """Get base domain from environment."""
    domain = get_config_value("BASE_DOMAIN")
    if not domain:
        raise ValueError("BASE_DOMAIN environment variable is required")
    return domain


def extract_tenant_from_host(headers: dict[str, str]) -> TenantFromHostResult:
    """Extract tenant ID from Host header using pattern {tenant}.ingest.{base_domain}.

    Args:
        headers: Webhook headers

    Returns:
        TenantFromHostResult with tenant_id and optional error
    """
    try:
        # Get Host header (case-insensitive lookup)
        host = None
        for key, value in headers.items():
            if key.lower() == "host":
                host = value
                break

        if not host:
            return TenantFromHostResult(
                tenant_id=None,
                error="No Host header found in request",
            )

        # Get base domain and construct expected suffix
        try:
            base_domain = get_base_domain()
            expected_suffix = f".ingest.{base_domain}"
        except ValueError as e:
            return TenantFromHostResult(
                tenant_id=None,
                error=f"Configuration error: {e}",
            )

        # Parse tenant from host pattern: {tenant}.ingest.{base_domain}
        if not host.endswith(expected_suffix):
            return TenantFromHostResult(
                tenant_id=None,
                error=f"Invalid host format: {host}. Expected pattern: {{tenant}}{expected_suffix}",
            )

        # Extract tenant part
        tenant_part = host.replace(expected_suffix, "")

        if not tenant_part:
            return TenantFromHostResult(
                tenant_id=None,
                error="Empty tenant in host header",
            )

        # Validate tenant ID format (basic validation)
        if not tenant_part.replace("-", "").replace("_", "").isalnum():
            return TenantFromHostResult(
                tenant_id=None,
                error=f"Invalid tenant ID format: {tenant_part}. Must contain only alphanumeric characters, hyphens, and underscores",
            )

        logger.debug(f"Extracted tenant '{tenant_part}' from host '{host}'")
        return TenantFromHostResult(tenant_id=tenant_part)

    except Exception as e:
        logger.error(f"Error extracting tenant from host header: {e}")
        return TenantFromHostResult(tenant_id=None, error=f"Unexpected error: {e}")


def extract_tenant_from_request(
    headers: dict[str, str], path_tenant_id: str | None = None
) -> TenantFromHostResult:
    """Extract tenant ID from URL path parameter or Host header.

    This function first tries to extract the tenant ID from the URL path parameter.
    If that's not available, it falls back to extracting from the Host header.

    Args:
        headers: Webhook headers
        path_tenant_id: Optional tenant ID extracted from URL path parameter

    Returns:
        TenantFromHostResult with tenant_id and optional error
    """
    # First try path parameter extraction
    if path_tenant_id:
        logger.debug(f"Using tenant '{path_tenant_id}' from URL path parameter")

        # Validate tenant ID format (same validation as host-based extraction)
        if not path_tenant_id.replace("-", "").replace("_", "").isalnum():
            return TenantFromHostResult(
                tenant_id=None,
                error=f"Invalid tenant ID format: {path_tenant_id}. Must contain only alphanumeric characters, hyphens, and underscores",
            )

        return TenantFromHostResult(tenant_id=path_tenant_id)

    # Fallback to host-based extraction
    logger.debug("No path tenant ID provided, falling back to Host header extraction")
    return extract_tenant_from_host(headers)


def create_session_name(tenant_id: str, source_type: str) -> str:
    """Create a unique session name for STS assume role.

    Args:
        tenant_id: Tenant identifier
        source_type: Source type

    Returns:
        Unique session name
    """
    timestamp = int(time.time())
    return f"gatekeeper-{tenant_id}-{source_type}-{timestamp}"


async def extract_tenant_from_jira_signing_secret(signing_secret: str | None) -> str | None:
    """Extract tenant ID from signing secret and verify it exists in SSM.

    The signing secret format is {tenant_id}-{suffix}, so we can extract
    the tenant ID directly and then verify it exists in SSM under
    /{tenant_id}/signing-secret/jira.

    Args:
        signing_secret: Jira signing secret to look up (format: tenant_id-suffix)

    Returns:
        Tenant ID if found and verified, None otherwise
    """
    try:
        if not signing_secret:
            logger.error("Missing x-jira-signing-secret header")
            return None

        if "-" not in signing_secret:
            logger.error(
                f"Invalid signing secret format: {signing_secret}. Expected format: tenant_id-suffix"
            )
            return None

        tenant_id = signing_secret.split("-", 1)[0]
        logger.debug(f"Extracted tenant ID '{tenant_id}' from signing secret")

        ssm_client = SSMClient()
        stored_signing_secret = await ssm_client.get_signing_secret(tenant_id, "jira")

        if stored_signing_secret is None:
            logger.error(f"No signing secret found for tenant {tenant_id}")
            return None

        if stored_signing_secret == signing_secret:
            logger.debug(f"Verified signing secret for tenant {tenant_id}")
            return tenant_id
        else:
            logger.error(
                f"Signing secret mismatch for tenant {tenant_id}. "
                f"Expected: {stored_signing_secret}, Got: {signing_secret}"
            )
            return None

    except Exception as e:
        logger.error(
            f"Unexpected error extracting tenant from signing secret {signing_secret}: {e}"
        )
        return None


async def extract_tenant_from_confluence_signing_secret(signing_secret: str | None) -> str | None:
    """Extract tenant ID from Confluence signing secret and verify it exists in SSM.

    The signing secret format is {tenant_id}-{suffix}, so we can extract
    the tenant ID directly and then verify it exists in SSM under
    /{tenant_id}/signing-secret/confluence.

    Args:
        signing_secret: Confluence signing secret to look up (format: tenant_id-suffix)

    Returns:
        Tenant ID if found and verified, None otherwise
    """
    try:
        if not signing_secret:
            logger.error("Missing x-confluence-signing-secret header")
            return None

        if "-" not in signing_secret:
            logger.error(
                f"Invalid signing secret format: {signing_secret}. Expected format: tenant_id-suffix"
            )
            return None

        tenant_id = signing_secret.split("-", 1)[0]
        logger.debug(f"Extracted tenant ID '{tenant_id}' from Confluence signing secret")

        ssm_client = SSMClient()
        stored_signing_secret = await ssm_client.get_signing_secret(tenant_id, "confluence")

        if stored_signing_secret is None:
            logger.error(f"No Confluence signing secret found for tenant {tenant_id}")
            return None

        if stored_signing_secret == signing_secret:
            logger.debug(f"Verified Confluence signing secret for tenant {tenant_id}")
            return tenant_id
        else:
            logger.error(
                f"Confluence signing secret mismatch for tenant {tenant_id}. "
                f"Expected: {stored_signing_secret}, Got: {signing_secret}"
            )
            return None

    except Exception as e:
        logger.error(
            f"Unexpected error extracting tenant from Confluence signing secret {signing_secret}: {e}"
        )
        return None


async def resolve_tenant_by_slack_team_id(team_id: str) -> str | None:
    """Resolve tenant ID by Slack team ID.

    Queries the connector_installations table in the control database to find the tenant
    associated with the given Slack team ID (workspace ID).

    Args:
        team_id: Slack team ID from webhook payload

    Returns:
        Tenant ID if found, None otherwise
    """
    try:
        repo = ConnectorInstallationsRepository()
        connector_installation = await repo.get_by_type_and_external_id(
            ConnectorType.SLACK, team_id
        )

        if connector_installation:
            logger.info(
                f"Found tenant {connector_installation.tenant_id} for Slack team ID {team_id}"
            )
            return connector_installation.tenant_id

        logger.warning(f"No tenant found for Slack team ID {team_id}")
        return None

    except Exception as e:
        logger.error(f"Error resolving tenant by Slack team ID: {e}")
        return None


def check_slack_url_verification(body_str: str) -> str | None:
    """Check if Slack webhook is a URL verification challenge.

    Args:
        body_str: Webhook body as string

    Returns:
        Challenge string if this is a URL verification, None otherwise
    """
    try:
        payload = json.loads(body_str)
        if payload.get("type") == "url_verification":
            logger.info("Slack URL verification challenge received (no tenant)")
            return payload.get("challenge", "")
    except (json.JSONDecodeError, KeyError):
        pass

    return None


def parse_slack_payload(body_str: str) -> dict | None:
    """Parse Slack webhook payload from JSON or form-encoded format.

    Args:
        body_str: Webhook body as string (may be JSON or form-encoded)

    Returns:
        Parsed payload dict, or None if parsing fails
    """
    try:
        # Check if form-encoded
        if body_str.startswith("payload="):
            form_data = urllib.parse.parse_qs(body_str)
            if "payload" in form_data:
                return json.loads(form_data["payload"][0])
            return json.loads(body_str)
        return json.loads(body_str)
    except (json.JSONDecodeError, KeyError, AttributeError):
        return None


async def extract_tenant_from_slack_request(
    body_str: str, headers: dict[str, str]
) -> TenantFromHostResult:
    """Extract tenant ID from Slack webhook request.

    First tries legacy per-tenant Host header extraction.
    Falls back to centralized OAuth (team_id resolution) if Host header fails.

    Args:
        body_str: Webhook body as string (may be JSON or form-encoded)
        headers: Webhook headers

    Returns:
        TenantFromHostResult with tenant_id and optional error
    """
    # First try legacy per-tenant app: extract tenant from Host header
    logger.debug("Trying Host header extraction for Slack webhook")
    host_result = extract_tenant_from_host(headers)

    # Check if we got a tenant_id from Host header, but skip "slack" which is used for centralized OAuth
    if host_result.tenant_id and host_result.tenant_id != "slack":
        logger.info(
            "Resolved tenant from Host header (legacy per-tenant app)",
            extra={"tenant_id": host_result.tenant_id},
        )
        return host_result

    # Fallback to centralized OAuth: extract team_id from payload
    logger.debug("Host header extraction failed, trying centralized OAuth (team_id resolution)")

    payload = parse_slack_payload(body_str)
    if not payload:
        return TenantFromHostResult(
            tenant_id=None,
            error="Failed to parse Slack webhook payload",
        )

    team_id = payload.get("team", {}).get("id") or payload.get("team_id")
    if not team_id:
        return TenantFromHostResult(
            tenant_id=None,
            error="Could not extract team_id from Slack webhook payload",
        )

    tenant_id = await resolve_tenant_by_slack_team_id(team_id)
    if not tenant_id:
        logger.warning(f"No tenant found for Slack team_id {team_id}")
        return TenantFromHostResult(
            tenant_id=None,
            error=f"No tenant found for Slack team_id {team_id}",
        )

    logger.info(
        "Resolved tenant from Slack team_id (centralized OAuth)",
        extra={"team_id": team_id, "tenant_id": tenant_id},
    )
    return TenantFromHostResult(tenant_id=tenant_id)
