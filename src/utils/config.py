"""Configuration utility for Corporate Context.

This module provides centralized configuration management with:
- Environment variables as primary source
- Per-tenant database configuration
- Type-safe access to configuration values
"""

import os
from typing import Any


def parse_config_value(value: str) -> str | bool | int | None:
    if value.lower() == "true":
        return True
    elif value.lower() == "false":
        return False
    else:
        # Try to parse as a number
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
            except ValueError:
                # Return as string
                return value


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a configuration value from environment variables.

    This function checks for values from environment variables only.

    Args:
        key: Configuration key name (e.g., "OPENSEARCH_URL")
        default: Default value if key not found

    Returns:
        Configuration value or default
    """
    # Check for environment variable
    env_value = os.environ.get(key)
    if env_value is not None:
        return parse_config_value(env_value)

    return default


def get_config_value_str(key: str) -> str | None:
    """
    Get a configuration value from environment variables. But sometimes you just want a string.
    """
    return os.environ.get(key)


def require_config_value(key: str) -> str:
    value = os.environ.get(key)
    if value is None:
        raise ValueError(f"Environment variable {key} is required")
    return value


def get_database_url() -> str:
    """Get database connection URL.

    Returns:
        PostgreSQL connection string from DATABASE_URL config

    Raises:
        ValueError: If DATABASE_URL is not configured
    """
    url = get_config_value("DATABASE_URL")
    if url:
        return url

    raise ValueError("Database URL not found. Please provide DATABASE_URL environment variable")


def get_control_database_url() -> str:
    """Get control database connection URL.

    Returns:
        PostgreSQL connection string from CONTROL_DATABASE_URL config

    Raises:
        ValueError: If CONTROL_DATABASE_URL is not configured
    """
    url = get_config_value("CONTROL_DATABASE_URL")
    if url:
        return url

    raise ValueError(
        "Control database URL not found. Please provide CONTROL_DATABASE_URL environment variable"
    )


def get_openai_api_key() -> str | None:
    """Get OpenAI API key from config or env."""
    return get_config_value("OPENAI_API_KEY")


def get_openai_base_url() -> str | None:
    """Get OpenAI base URL from config or env."""
    return get_config_value("OPENAI_BASE_URL")


def get_opensearch_url() -> str:
    """Get OpenSearch URL for display/logging purposes.

    This constructs a URL from environment variables for backward compatibility.
    For actual client connections, use get_opensearch_admin_username/password.

    Returns:
        OpenSearch URL (e.g., http://localhost:9200)
    """
    host = os.environ.get("OPENSEARCH_DOMAIN_HOST", "localhost")
    port = os.environ.get("OPENSEARCH_PORT", "9200")
    use_ssl = os.environ.get("OPENSEARCH_USE_SSL") is not None
    protocol = "https" if use_ssl else "http"
    return f"{protocol}://{host}:{port}"


def get_opensearch_admin_username() -> str | None:
    """Get OpenSearch admin username from config or env.

    This is used as the shared service credential for all tenant operations.

    Returns:
        OpenSearch admin username or None if not configured
    """
    return get_config_value("OPENSEARCH_ADMIN_USERNAME")


def get_opensearch_admin_password() -> str | None:
    """Get OpenSearch admin password from config or env.

    This is used as the shared service credential for all tenant operations.

    Returns:
        OpenSearch admin password or None if not configured
    """
    return get_config_value("OPENSEARCH_ADMIN_PASSWORD")


def is_source_enabled(source: str) -> bool:
    """Check if a source is enabled."""
    return get_config_value(f"{source.upper()}_ENABLED", False)


def get_mcp_auth_public_key() -> str | None:
    """Get MCP auth public key from config or env."""
    return get_config_value("MCP_AUTH_PUBLIC_KEY")


def get_restore_target_database_url() -> str:
    """Get database URL for restore target, with RESTORE_TARGET_ prefix.

    Used by restore_data_snapshot.py to avoid accidentally restoring to production.

    Returns:
        PostgreSQL connection string for restore target

    Raises:
        ValueError: If RESTORE_TARGET_DATABASE_URL is not set
    """
    # First check for RESTORE_TARGET_DATABASE_URL
    restore_db_url = os.environ.get("RESTORE_TARGET_DATABASE_URL")
    if restore_db_url:
        return restore_db_url

    # Never fall back to regular DATABASE_URL to prevent accidental production restores
    raise ValueError(
        "RESTORE_TARGET_DATABASE_URL environment variable is required for restore operations. "
        "This prevents accidental restoration to production databases."
    )


def get_restore_target_opensearch_url() -> str:
    """Get OpenSearch URL for restore target.

    Used by restore_data_snapshot.py to avoid accidentally restoring to production.
    URL should include embedded credentials if authentication is required.

    Returns:
        OpenSearch URL with embedded credentials
    """
    # First check for RESTORE_TARGET_OPENSEARCH_URL
    restore_url = os.environ.get("RESTORE_TARGET_OPENSEARCH_URL")

    if restore_url:
        return restore_url

    # Check for legacy separate host/port variables and build URL
    restore_host = os.environ.get("RESTORE_TARGET_OPENSEARCH_HOST")
    if restore_host:
        restore_port = os.environ.get("RESTORE_TARGET_OPENSEARCH_PORT")
        restore_username = os.environ.get("RESTORE_TARGET_OPENSEARCH_USERNAME")
        restore_password = os.environ.get("RESTORE_TARGET_OPENSEARCH_PASSWORD")

        # Build URL from components
        port = int(restore_port) if restore_port else 9200
        protocol = "https" if restore_host.startswith("https://") else "http"
        host_clean = restore_host.replace("http://", "").replace("https://", "")

        # Build URL with or without credentials
        if restore_username and restore_password:
            url = f"{protocol}://{restore_username}:{restore_password}@{host_clean}:{port}"
        else:
            url = f"{protocol}://{host_clean}:{port}"

        return url

    # Never fall back to regular OpenSearch config to prevent accidental production restores
    raise ValueError(
        "RESTORE_TARGET_OPENSEARCH_URL or RESTORE_TARGET_OPENSEARCH_HOST environment variable is required for restore operations. "
        "This prevents accidental restoration to production clusters. "
        "Set RESTORE_TARGET_OPENSEARCH_URL (e.g., http://username:password@localhost:9200) or "
        "RESTORE_TARGET_OPENSEARCH_HOST with optional PORT, USERNAME, and PASSWORD variables."
    )


def get_queue_max_retries() -> int:
    """Get queue max retries from config or env."""
    return get_config_value("QUEUE_MAX_RETRIES", 3)


def get_queue_retry_delay() -> int:
    """Get queue retry delay in seconds from config or env."""
    return get_config_value("QUEUE_RETRY_DELAY", 30)


def get_queue_batch_size() -> int:
    """Get queue batch size from config or env."""
    return get_config_value("QUEUE_BATCH_SIZE", 10)


def get_queue_max_job_age() -> int:
    """Get queue max job age in seconds from config or env."""
    return get_config_value("QUEUE_MAX_JOB_AGE", 86400)


def get_source_database_url() -> str | None:
    """Get source database URL from env variable.

    This is used for connecting to external source databases like Statsig.

    Returns:
        Database connection string or None
    """
    return get_config_value("SOURCE_DATABASE_URL")


# Agent configuration functions
def get_context_window(model: str) -> int:
    """Get context window for a given model."""
    if model == "gpt-5":
        return 400_000  # https://platform.openai.com/docs/models/gpt-5
    else:
        raise ValueError(f"Unknown model: {model}")


def get_agent_max_messages() -> int:
    """Get agent max messages from config or env."""
    return get_config_value("AGENT_MAX_MESSAGES", 100)


def get_agent_context_window_buffer() -> float:
    """Get agent context window buffer from config or env."""
    return get_config_value("AGENT_CONTEXT_WINDOW_BUFFER", 0.1)


def get_agent_openai_timeout() -> int:
    """Get agent OpenAI timeout from config or env."""
    return get_config_value("AGENT_OPENAI_TIMEOUT", 180)


def get_agent_tool_timeout() -> int:
    """Get agent tool timeout from config or env."""
    return get_config_value("AGENT_TOOL_TIMEOUT", 60)


def get_agent_debug() -> bool:
    """Get agent debug flag from config or env."""
    return get_config_value("AGENT_DEBUG", False)


def get_agent_citation_excerpt_length() -> int:
    """Get the maximum character length for citation excerpts.

    Returns:
        Maximum number of characters to include in citation excerpts.
        Defaults to 100 if not configured.
    """
    return get_config_value("AGENT_CITATION_EXCERPT_LENGTH", 100)


# Tracing configuration functions
def get_tracing_enabled() -> bool:
    """Get tracing enabled flag from config or env."""
    return get_config_value("TRACING_ENABLED", True)


def get_langfuse_host() -> str:
    """Get Langfuse host from config or env."""
    return get_config_value("LANGFUSE_HOST", "https://us.cloud.langfuse.com")


def get_langfuse_public_key() -> str | None:
    """Get Langfuse public key from config or env."""
    return get_config_value("LANGFUSE_PUBLIC_KEY")


def get_langfuse_secret_key() -> str | None:
    """Get Langfuse secret key from config or env."""
    return get_config_value("LANGFUSE_SECRET_KEY")


def get_grapevine_environment() -> str:
    """Get Grapevine environment from env var."""
    return get_config_value("GRAPEVINE_ENVIRONMENT", "local")


def get_company_name() -> str | None:
    """Get company name from config or env."""
    return get_config_value("COMPANY_NAME")


def get_company_context() -> str | None:
    """Get company context from config or env."""
    return get_config_value("COMPANY_CONTEXT")


# Source Ingest validation functions
# ----------------------


def get_authkit_domain() -> str | None:
    """AuthKit (WorkOS) domain, e.g. https://your-project-12345.authkit.app"""
    return get_config_value("AUTHKIT_DOMAIN")


def get_mcp_base_url() -> str:
    """Base URL where this MCP server is externally reachable."""
    return get_config_value("MCP_BASE_URL", "http://localhost:8000")


def get_remote_mcp_url() -> str:
    """
    Get remote MCP server URL to execute tools on, if any.
    Remote tool execution is only enabled if a REMOTE_MCP_TOKEN is set.
    """
    return get_config_value("REMOTE_MCP_URL", "")


def get_remote_mcp_token() -> str | None:
    """
    The bearer token to auth with the remote MCP server (`REMOTE_MCP_URL`) to execute tools on.
    Remote tool execution is only enabled if this token is set.
    """
    return get_config_value("REMOTE_MCP_TOKEN")


async def extract_tenant_id_from_token(token: str) -> str | None:
    """Extract and verify tenant_id from an MCP token (JWT or API key).

    This function verifies the token signature before extracting the tenant_id.

    Args:
        token: MCP token (JWT or API key)

    Returns:
        The tenant_id if token is valid, None otherwise
    """
    from src.mcp.utils.api_keys import verify_api_key
    from src.mcp.utils.internal_jwt import verify_internal_jwt

    # Try JWT verification first
    claims = verify_internal_jwt(token)
    if claims:
        tenant_id = claims.get("tenant_id")
        if tenant_id:
            return tenant_id

    # Try API key verification
    tenant_id = await verify_api_key(token)
    if tenant_id:
        return tenant_id

    return None


# --- Internal Agent/Slackbot JWT configuration ---


def get_internal_jwt_jwks_uri() -> str | None:
    """JWKS URI for internal JWT issuer used by agent/slackbot (optional)."""
    return get_config_value("INTERNAL_JWT_JWKS_URI")


def get_internal_jwt_issuer() -> str | None:
    """Expected issuer for internal JWTs (optional)."""
    return get_config_value("INTERNAL_JWT_ISSUER")


def get_internal_jwt_audience() -> str | None:
    """Expected audience for internal JWTs (optional)."""
    return get_config_value("INTERNAL_JWT_AUDIENCE")


def get_internal_jwt_public_key() -> str | None:
    """PEM public key for internal JWTs (optional, if not using JWKS)."""
    return get_config_value("INTERNAL_JWT_PUBLIC_KEY")


def get_auth_enabled() -> bool:
    """Get whether authentication is enabled."""
    return get_config_value("AUTH_ENABLED", True)


def get_dev_org_id() -> str | None:
    """Get hardcoded org_id for development when auth is disabled."""
    return get_config_value("DEV_ORG_ID")


# --- Firebase Configuration (for GatherV2 Authentication ---
def get_firebase_admin_private_key_id() -> str | None:
    """Get Firebase Admin SDK private key ID from config or env."""
    return get_config_value("FIREBASE_ADMIN_PRIVATE_KEY_ID")


def get_firebase_admin_private_key() -> str | None:
    """Get Firebase Admin SDK private key from config or env."""
    return get_config_value("FIREBASE_ADMIN_PRIVATE_KEY")


def get_firebase_admin_client_email() -> str | None:
    """Get Firebase Admin SDK client email from config or env."""
    return get_config_value("FIREBASE_ADMIN_CLIENT_EMAIL")


def get_firebase_admin_client_id() -> str | None:
    """Get Firebase Admin SDK client ID from config or env."""
    return get_config_value("FIREBASE_ADMIN_CLIENT_ID")


def get_firebase_admin_client_cert_url() -> str | None:
    """Get Firebase Admin SDK client certificate URL from config or env."""
    return get_config_value("FIREBASE_ADMIN_CLIENT_CERT_URL")


def get_firebase_admin_project_id() -> str | None:
    """Get Firebase Admin SDK project ID from config or env."""
    return get_config_value("FIREBASE_ADMIN_PROJECT_ID")


def get_slack_export_questions_enabled() -> bool:
    """Get whether Slack sample question extraction is enabled."""
    return get_config_value("ENABLE_SLACK_EXPORT_QUESTIONS", False)


# --- SQS Extended Client Configuration ---


def get_sqs_extended_s3_bucket() -> str | None:
    """Get S3 bucket name for storing large ingest webhook payloads."""
    return get_config_value("INGEST_WEBHOOK_DATA_S3_BUCKET_NAME")


def get_sqs_extended_enabled() -> bool:
    """Get whether SQS extended client is enabled.

    Defaults to True if S3 bucket is configured, False otherwise.
    """
    # If bucket is configured, default to enabled
    bucket = get_sqs_extended_s3_bucket()
    default_enabled = bucket is not None
    return get_config_value("SQS_EXTENDED_ENABLED", default_enabled)


def get_base_domain() -> str:
    """Get base domain from config or env.

    Returns:
        Base domain (e.g., 'localhost' or 'your-domain.com')

    Raises:
        ValueError: If BASE_DOMAIN is not configured
    """
    domain = get_config_value("BASE_DOMAIN")
    if not domain:
        raise ValueError("BASE_DOMAIN environment variable is required")
    return domain


def get_frontend_url() -> str:
    """Get frontend URL from config or env.

    Returns:
        Frontend URL (e.g., 'http://localhost:5173' or 'https://app.your-domain.com')
    """
    return get_config_value("FRONTEND_URL", "http://localhost:5173")


def get_development_gong_api_base_url() -> str | None:
    """Get default Gong API base URL for local development."""
    return get_config_value("GONG_API_BASE_URL")


def get_development_gong_access_token() -> str | None:
    """Get default Gong API access token for local development."""
    return get_config_value("GONG_ACCESS_TOKEN")


def get_billing_enabled() -> bool:
    """Get whether billing is enabled for this deployment.

    Billing is enabled when STRIPE_SECRET_KEY is configured.
    No separate toggle needed - if Stripe is configured, billing is on.

    Returns:
        True if STRIPE_SECRET_KEY is set, False otherwise
    """
    return bool(get_config_value("STRIPE_SECRET_KEY"))


def get_amplitude_enabled() -> bool:
    """Get whether Amplitude analytics is enabled.

    Amplitude is enabled when VITE_AMPLITUDE_API_KEY is set.

    Returns:
        True if VITE_AMPLITUDE_API_KEY is configured, False otherwise
    """
    return bool(get_config_value("VITE_AMPLITUDE_API_KEY"))


def get_posthog_enabled() -> bool:
    """Get whether PostHog analytics is enabled.

    PostHog is enabled when VITE_POSTHOG_API_KEY is set.

    Returns:
        True if VITE_POSTHOG_API_KEY is configured, False otherwise
    """
    return bool(get_config_value("VITE_POSTHOG_API_KEY"))


def get_analytics_enabled() -> bool:
    """Get whether any analytics service is enabled.

    Returns True if either Amplitude or PostHog is configured.

    Returns:
        True if any analytics service is configured, False otherwise
    """
    return get_amplitude_enabled() or get_posthog_enabled()


def get_jira_app_id() -> str | None:
    """Get Jira Forge app ID from config or env.

    Returns:
        Jira app ID (UUID format) or None if not configured
    """
    return get_config_value("JIRA_APP_ID")


def get_confluence_app_id() -> str | None:
    """Get Confluence Forge app ID from config or env.

    Returns:
        Confluence app ID (UUID format) or None if not configured
    """
    return get_config_value("CONFLUENCE_APP_ID")


def get_trello_power_up_api_key() -> str | None:
    """Get Trello Power-Up API key from config or env.

    Returns:
        Trello Power-Up API key or None if not configured
    """
    return get_config_value("TRELLO_POWER_UP_API_KEY")


def get_trello_power_up_secret() -> str | None:
    """Get Trello Power-Up OAuth secret from config or env.

    This secret is used for webhook signature verification.
    See: https://developer.atlassian.com/cloud/trello/guides/rest-api/webhooks/

    Returns:
        Trello Power-Up OAuth secret or None if not configured
    """
    return get_config_value("TRELLO_POWER_UP_SECRET")


def get_trello_power_up_id() -> str | None:
    """Get Trello Power-Up plugin ID from config or env.

    This ID identifies your Power-Up in the Trello marketplace and is required
    for GDPR compliance API calls.

    Returns:
        Trello Power-Up plugin ID or None if not configured
    """
    return get_config_value("TRELLO_POWER_UP_ID")
