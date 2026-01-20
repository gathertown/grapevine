"""Webhook handler functions for gatekeeper service."""

import json
import urllib.parse
from datetime import UTC, datetime

import aiohttp
from fastapi import HTTPException, Request, Response

from connectors.attio import AttioWebhookVerifier, extract_attio_webhook_metadata
from connectors.base.external_source import ExternalSource
from connectors.confluence import ConfluenceWebhookVerifier, extract_confluence_webhook_metadata
from connectors.confluence.confluence_models import ConfluenceApiBackfillRootConfig
from connectors.figma.figma_webhook_handler import (
    FigmaWebhookVerifier,
    extract_figma_team_id,
    extract_figma_webhook_metadata,
)
from connectors.gather import GatherWebhookVerifier, extract_gather_webhook_metadata
from connectors.github import GitHubWebhookVerifier, extract_github_webhook_metadata
from connectors.gmail import GoogleEmailWebhookVerifier
from connectors.gong import GongWebhookVerifier
from connectors.google_drive import GoogleDriveWebhookVerifier
from connectors.hubspot import (
    HubSpotWebhookVerifier,
    deduplicate_hubspot_events,
    extract_hubspot_webhook_metadata,
)
from connectors.jira import JiraWebhookVerifier, extract_jira_webhook_metadata
from connectors.jira.jira_models import JiraApiBackfillRootConfig
from connectors.linear import (
    LinearWebhookVerifier,
    extract_linear_organization_id,
    extract_linear_webhook_metadata,
)
from connectors.notion import NotionWebhookVerifier, extract_notion_webhook_metadata
from connectors.slack import SlackWebhookVerifier, extract_slack_webhook_metadata
from connectors.trello import TrelloWebhookVerifier, extract_trello_webhook_metadata
from src.clients.github_app import get_github_app_client
from src.clients.redis import get_client as get_redis_client
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.database.connector_installations import (
    ConnectorInstallationsRepository,
    ConnectorStatus,
    ConnectorType,
)
from src.ingest.gatekeeper.models import WebhookResponse
from src.ingest.gatekeeper.services.webhook_processor import WebhookProcessor
from src.ingest.gatekeeper.verification import WebhookVerifier
from src.ingest.services.forge_jwt import verify_forge_request
from src.mcp.utils.api_keys import verify_api_key
from src.utils.config import get_confluence_app_id, get_grapevine_environment, get_jira_app_id
from src.utils.logging import LogContext, get_logger
from src.utils.size_formatting import format_size
from src.utils.tenant_config import set_tenant_config_value

logger = get_logger(__name__)

# Redis key TTL for Notion setup nonces (2 weeks)
NOTION_SETUP_NONCE_TTL_SECONDS = 14 * 24 * 60 * 60


async def _validate_notion_setup_nonce(nonce: str | None, tenant_id: str) -> bool:
    """Validate Notion setup nonce from Redis and mark as used.

    Args:
        nonce: The setup nonce to validate (can be None)
        tenant_id: Expected tenant ID

    Returns:
        True if nonce is valid and matches tenant_id, False otherwise
    """
    if not nonce:
        logger.debug("Notion setup nonce is missing")
        return False

    try:
        redis_client = await get_redis_client()
        redis_key = f"notion:setup:nonce:{nonce}"

        # Get the nonce value from Redis
        nonce_value = await redis_client.get(redis_key)

        if not nonce_value:
            logger.debug(f"Notion setup nonce not found in Redis: {nonce[:8]}...")
            return False

        # Parse the stored value: {tenant_id}:{timestamp}
        try:
            stored_tenant_id, timestamp_str = nonce_value.split(":", 1)
        except ValueError:
            logger.error(f"Invalid nonce value format in Redis: {nonce_value}")
            return False

        # Validate tenant ID matches
        if stored_tenant_id != tenant_id:
            logger.warning(
                f"Notion setup nonce tenant mismatch. Expected: {tenant_id}, Got: {stored_tenant_id}"
            )
            return False

        # Nonce is valid - delete it to ensure one-time use
        await redis_client.delete(redis_key)
        logger.info(f"Notion setup nonce validated and consumed for tenant {tenant_id}")

        return True

    except Exception as e:
        logger.error(f"Error validating Notion setup nonce: {e}")
        return False


def validate_tenant_id(tenant_id: str) -> None:
    """Validate tenant ID format and raise HTTPException if invalid."""
    if not tenant_id.replace("-", "").replace("_", "").isalnum():
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tenant ID format: {tenant_id}. Must contain only alphanumeric characters, hyphens, and underscores",
        )


def _extract_webhook_metadata(
    source_type: ExternalSource, headers: dict[str, str], body_str: str
) -> dict[str, str | int | bool]:
    """Extract metadata from webhook payload for observability.

    Args:
        source_type: The webhook source type
        headers: HTTP headers
        body_str: Request body as string

    Returns:
        Dictionary containing extracted metadata, always includes payload_size
    """
    try:
        if source_type == "github":
            return extract_github_webhook_metadata(headers, body_str)
        elif source_type == "slack":
            return extract_slack_webhook_metadata(headers, body_str)
        elif source_type == "linear":
            return extract_linear_webhook_metadata(headers, body_str)
        elif source_type == "notion":
            return extract_notion_webhook_metadata(headers, body_str)
        elif source_type == "jira":
            return extract_jira_webhook_metadata(headers, body_str)
        elif source_type == "confluence":
            return extract_confluence_webhook_metadata(headers, body_str)
        elif source_type == "gather":
            return extract_gather_webhook_metadata(headers, body_str)
        elif source_type == "trello":
            return extract_trello_webhook_metadata(headers, body_str)
        elif source_type == "attio":
            return extract_attio_webhook_metadata(headers, body_str)
        elif source_type == "figma":
            return extract_figma_webhook_metadata(headers, body_str)
        elif source_type == "google_drive" or source_type == "google_email":
            return {
                "payload_size": len(body_str),
                "payload_size_human": format_size(len(body_str)),
            }
        else:
            # Fallback for unknown source types
            return {
                "payload_size": len(body_str),
                "payload_size_human": format_size(len(body_str)),
                "source_type": source_type,
            }
    except Exception as e:
        # Always return at least basic information
        logger.error(f"Error extracting webhook metadata for {source_type}: {e}")
        return {
            "payload_size": len(body_str),
            "payload_size_human": format_size(len(body_str)),
            "metadata_extraction_error": str(e),
        }


def _is_validation_disabled(request: Request) -> bool:
    """Check if webhook validation is disabled via app state."""
    return getattr(request.app.state, "dangerously_disable_webhook_validation", False)


async def _verify_and_raise(
    verifier: WebhookVerifier,
    headers: dict[str, str],
    body: bytes,
    tenant_id: str,
    source_type: str,
    request: Request,
    request_url: str | None = None,
) -> None:
    """Verify webhook and raise HTTPException on failure.

    This is a helper that handlers call after doing any source-specific
    pre-processing. It delegates to the verifier and converts failures
    to appropriate HTTP error codes.

    Args:
        verifier: The webhook verifier instance
        headers: HTTP headers
        body: Raw request body as bytes
        tenant_id: Tenant ID
        source_type: Source type for logging
        request: FastAPI request (to check if validation is disabled)
        request_url: Optional request URL (required for some verifiers like HubSpot)

    Raises:
        HTTPException: If verification fails
    """
    # Check if webhook validation is disabled
    if _is_validation_disabled(request):
        logger.warning(
            f"⚠️ Skipping {source_type} webhook verification (DANGEROUSLY_DISABLE_WEBHOOK_VALIDATION=true)",
        )
        return

    result = await verifier.verify(headers, body, tenant_id, request_url)

    if not result.success:
        logger.warning(f"Failed to verify {source_type} webhook: {result.error}")

        # Determine appropriate error status code based on error message
        error_msg = result.error or "Verification failed"
        error_lower = error_msg.lower()

        # 400 Bad Request: Configuration/setup issues
        if "not configured" in error_lower or "no signing secret" in error_lower:
            status_code = 400
        # 401 Unauthorized: Signature verification failures
        elif "signature" in error_lower:
            status_code = 401
        # Default: 400 for other verification failures
        else:
            status_code = 400

        raise HTTPException(status_code=status_code, detail=error_msg)


async def _process_verified_webhook(
    request: Request,
    source_type: ExternalSource,
    tenant_id: str,
    body_str: str,
    headers: dict[str, str],
    extracted_body: str | None = None,
) -> WebhookResponse:
    """Process an already-verified webhook.

    This function handles the common post-verification logic:
    - Extract metadata for observability
    - Publish to SQS queues
    - Return success response

    Handlers are responsible for:
    1. Reading the request body
    2. Calling their verifier (or skipping if validation disabled)
    3. Calling this function to publish

    Args:
        request: FastAPI request object
        source_type: Source type (github, slack, linear, notion, etc.)
        tenant_id: Tenant ID
        body_str: Request body as string (for signature verification reference)
        headers: Request headers
        extracted_body: Optional extracted JSON body (for processing/SQS, defaults to body_str)

    Returns:
        WebhookResponse indicating success or failure
    """
    webhook_metadata: dict[str, str | int | bool] = {"payload_size": 0, "payload_size_human": "0 B"}

    try:
        # Use extracted_body for processing if provided, otherwise use body_str
        processing_body = extracted_body if extracted_body is not None else body_str

        webhook_metadata = _extract_webhook_metadata(source_type, headers, processing_body)
        tracking_context = {f"webhook_meta_{key}": value for key, value in webhook_metadata.items()}

        with LogContext(tenant_id=tenant_id, **tracking_context):
            logger.info(f"Webhook verification successful for {source_type}")

            sqs_client: SQSClient = request.app.state.sqs_client
            message_ids = await _publish_to_queues(
                sqs_client, processing_body, headers, tenant_id, source_type
            )

            if not message_ids:
                logger.error(f"Failed to publish {source_type} webhook to any queues")
                raise HTTPException(
                    status_code=500, detail="Failed to publish webhook to processing queues"
                )

            logger.info(
                f"Successfully processed {source_type} webhook for tenant {tenant_id}",
                message_count=len(message_ids),
            )
            return WebhookResponse(
                success=True,
                message=f"Webhook processed successfully, published to {len(message_ids)} queue(s)",
                tenant_id=tenant_id,
                message_id=message_ids[0] if message_ids else None,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing {source_type} webhook: {e}", **webhook_metadata)
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


async def _publish_to_queues(
    sqs_client: SQSClient,
    body: str,
    headers: dict[str, str],
    tenant_id: str,
    source_type: ExternalSource,
) -> list[str]:
    """Publish webhook to appropriate queues based on source type.

    Args:
        sqs_client: SQS client instance
        body: Webhook body as JSON string (caller extracts from form-encoding if needed)
        headers: Webhook headers
        tenant_id: Tenant identifier
        source_type: Source type (github, slack, linear, notion)

    Returns:
        List of message IDs from successful queue publications
    """
    message_ids = []

    # All endpoints write to ingest-jobs queue
    message_id = await sqs_client.send_ingest_webhook_message(
        webhook_body=body,
        webhook_headers=headers,
        tenant_id=tenant_id,
        source_type=source_type,
    )
    if message_id:
        message_ids.append(message_id)
        logger.info(f"Published to ingest-jobs queue: {message_id}", source_type=source_type)
    else:
        logger.error("Failed to publish to ingest-jobs queue")

    # Slack endpoint additionally writes to slackbot queue
    if source_type == "slack":
        # Extract event_id from Slack webhook for deduplication
        dedup_id = None
        try:
            payload = json.loads(body)
            dedup_id = payload.get("event_id")
            if dedup_id:
                logger.debug(f"Using Slack event_id for deduplication: {dedup_id}")
        except Exception as e:
            logger.warning(f"Failed to extract event_id from Slack webhook: {e}")

        # Always send to slackbot queue - let slackbot decide based on user
        # Slackbot will check if mentions are from external users and block accordingly
        message_id = await sqs_client.send_slackbot_webhook_message(
            webhook_body=body,
            webhook_headers=headers,
            tenant_id=tenant_id,
            message_deduplication_id=dedup_id,
        )
        if message_id:
            message_ids.append(message_id)
            logger.info(f"Published to slackbot queue: {message_id}", source_type=source_type)
        else:
            logger.error("Failed to publish to slackbot queue")

    return message_ids


async def handle_github_webhook(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle GitHub webhook processing with tenant ID."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received github webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Verify using GitHub verifier
    await _verify_and_raise(GitHubWebhookVerifier(), headers, body, tenant_id, "github", request)

    return await _process_verified_webhook(request, "github", tenant_id, body_str, headers)


async def handle_slack_webhook(request: Request, tenant_id: str) -> WebhookResponse | Response:
    """Handle Slack webhook processing with tenant ID."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    # Extract JSON payload, handling both JSON and form-encoded formats
    extracted_body = body_str  # Default: use as-is
    content_type = headers.get("content-type", "")

    # Log Content-Type for diagnostics
    logger.info(
        "Processing Slack webhook",
        content_type=content_type,
        tenant_id=tenant_id,
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Check for form-encoded data by content-type OR by body content
    # Slack button interactions may not always have the correct content-type header
    has_form_content_type = "application/x-www-form-urlencoded" in content_type
    has_form_body_prefix = body_str.startswith("payload=")
    is_form_encoded = has_form_content_type or has_form_body_prefix

    if is_form_encoded:
        # Form-encoded payload (block_actions/interactivity)
        try:
            form_data = urllib.parse.parse_qs(body_str)
            if "payload" not in form_data:
                logger.error("Missing payload parameter in form-encoded Slack webhook")
                raise HTTPException(status_code=400, detail="Missing payload parameter")

            # Extract JSON from form data
            extracted_body = form_data["payload"][0]
            payload = json.loads(extracted_body)

            logger.info(
                "Received form-encoded Slack webhook",
                payload_type=payload.get("type"),
                tenant_id=tenant_id,
            )
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.error(f"Failed to parse form-encoded Slack webhook: {e}")
            raise HTTPException(status_code=400, detail="Invalid form-encoded payload")
    else:
        # JSON payload (event_callback, url_verification)
        try:
            payload = json.loads(body_str)

            # Handle URL verification challenge (no signature verification needed)
            if payload.get("type") == "url_verification":
                logger.info("Slack URL verification challenge received")
                challenge = payload.get("challenge", "")
                return Response(content=challenge, media_type="text/plain")
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON body from slack webhook: {body_str}")
            raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Verify using Slack verifier (use original body for signature verification)
    await _verify_and_raise(SlackWebhookVerifier(), headers, body, tenant_id, "slack", request)

    # Pass extracted_body for processing (may differ from body_str for form-encoded)
    return await _process_verified_webhook(
        request, "slack", tenant_id, body_str, headers, extracted_body
    )


async def handle_linear_webhook(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle Linear webhook processing with tenant ID (legacy per-tenant webhooks)."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received linear webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Verify using Linear verifier
    await _verify_and_raise(LinearWebhookVerifier(), headers, body, tenant_id, "linear", request)

    return await _process_verified_webhook(request, "linear", tenant_id, body_str, headers)


async def handle_linear_oauth_webhook(request: Request) -> WebhookResponse:
    """Handle Linear OAuth webhook (application-level webhook).

    For OAuth, Linear sends webhooks to a single application-level endpoint.
    The organization ID is extracted from the webhook payload to identify the tenant.
    """
    try:
        # Read body to extract organization ID
        body = await request.body()
        body_str = body.decode("utf-8")
        headers = dict(request.headers)

        # Log webhook receipt for debugging
        logger.info(
            "Received Linear OAuth webhook",
            payload_size=len(body_str),
            payload_size_human=format_size(len(body_str)),
        )

        # Extract Linear organization ID from payload
        organization_id = extract_linear_organization_id(body_str)
        if not organization_id:
            logger.warning("No organization ID found in Linear OAuth webhook payload")
            raise HTTPException(
                status_code=400,
                detail="Missing organization ID in Linear webhook payload",
            )

        # Resolve tenant ID from organization ID
        tenant_id = await _resolve_tenant_by_linear_org_id(organization_id)
        if not tenant_id:
            logger.warning(
                f"No tenant found for Linear organization ID {organization_id}",
            )
            raise HTTPException(
                status_code=404,
                detail=f"No tenant found for Linear organization ID {organization_id}",
            )

        with LogContext(tenant_id=tenant_id, linear_org_id=organization_id):
            logger.info(
                f"Processing Linear OAuth webhook for organization {organization_id}",
            )
            validate_tenant_id(tenant_id)

            # Verify using Linear verifier
            await _verify_and_raise(
                LinearWebhookVerifier(), headers, body, tenant_id, "linear", request
            )

            return await _process_verified_webhook(request, "linear", tenant_id, body_str, headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Linear OAuth webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


async def handle_notion_webhook(request: Request, tenant_id: str) -> WebhookResponse | Response:
    """Handle Notion webhook processing with tenant ID."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received notion webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Handle Notion webhook verification request
    try:
        payload = json.loads(body_str)
        if "verification_token" in payload and len(payload) == 1:
            logger.info("Notion verification token received")

            # Check if webhook validation is disabled in the app state
            if _is_validation_disabled(request):
                logger.warning(
                    f"⚠️  Webhook validation disabled - skipping Notion verification token storage: {payload}"
                )
                return Response(status_code=200)

            verification_token = payload["verification_token"]
            logger.info(f"Notion verification token received: {verification_token}")

            # Validate setup nonce from query parameters
            setup_nonce = request.query_params.get("setup_nonce")

            # Validate nonce with Redis (will fail if nonce is None or invalid)
            is_valid = await _validate_notion_setup_nonce(setup_nonce, tenant_id)

            if not is_valid:
                nonce_preview = setup_nonce[:8] + "..." if setup_nonce else "None"
                logger.warning(
                    f"⚠️ SECURITY: Invalid or missing Notion setup nonce for tenant {tenant_id}. "
                    f"Nonce: {nonce_preview}. Rejecting to prevent AIVP-672 vulnerability.",
                )
                # Return 403 to indicate authentication/authorization failure
                return Response(status_code=403)

            # Valid nonce - store the verification token
            webhook_processor: WebhookProcessor = request.app.state.webhook_processor
            ssm_client: SSMClient = webhook_processor.ssm_client

            await ssm_client.store_signing_secret(
                tenant_id=tenant_id,
                source_type="notion",
                secret=verification_token,
            )

            logger.info(f"Notion verification token stored successfully for tenant {tenant_id}")
            return Response(status_code=200)

    except json.JSONDecodeError:
        pass

    # Verify using Notion verifier
    await _verify_and_raise(NotionWebhookVerifier(), headers, body, tenant_id, "notion", request)

    return await _process_verified_webhook(request, "notion", tenant_id, body_str, headers)


async def handle_google_drive_webhook(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle Google Drive webhook processing with tenant ID."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received google_drive webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Verify using Google Drive verifier
    await _verify_and_raise(
        GoogleDriveWebhookVerifier(), headers, body, tenant_id, "google_drive", request
    )

    return await _process_verified_webhook(request, "google_drive", tenant_id, body_str, headers)


async def handle_google_email_webhook(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle Google Email webhook processing with tenant ID."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received google_email webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Verify using Google Email verifier (JWT-based)
    # Pass the request URL as the expected audience for JWT validation
    request_url = str(request.url)
    await _verify_and_raise(
        GoogleEmailWebhookVerifier(), headers, body, tenant_id, "google_email", request, request_url
    )

    return await _process_verified_webhook(request, "google_email", tenant_id, body_str, headers)


async def handle_gather_webhook(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle Gather webhook processing with tenant ID."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received gather webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Verify using Gather verifier
    await _verify_and_raise(GatherWebhookVerifier(), headers, body, tenant_id, "gather", request)

    return await _process_verified_webhook(request, "gather", tenant_id, body_str, headers)


async def handle_github_app_webhook(request: Request) -> WebhookResponse:
    """Handle GitHub App webhooks - including installation events."""
    # Initialize webhook_metadata early to prevent NameError in exception handler
    webhook_metadata: dict[str, str | int | bool] = {"payload_size": 0, "payload_size_human": "0 B"}

    try:
        headers = dict(request.headers)
        body = await request.body()
        body_str = body.decode("utf-8")

        # Log basic receipt (before verification)
        payload_size = len(body_str)
        logger.info(
            "Received GitHub App webhook",
            payload_size=payload_size,
            payload_size_human=format_size(payload_size),
        )

        # Verify webhook signature using GitHub App secret
        signature = headers.get("x-hub-signature-256")
        if not signature:
            logger.error("Missing GitHub App webhook signature")
            raise HTTPException(status_code=401, detail="Missing webhook signature")

        # Get GitHub App client for signature verification
        app_client = get_github_app_client()
        if not app_client.verify_webhook_signature(body, signature):
            logger.error("Invalid GitHub App webhook signature")
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        # Parse the webhook payload
        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON body from GitHub App webhook: {body_str}")
            raise HTTPException(status_code=400, detail="Invalid JSON body")

        event_type = headers.get("x-github-event", "unknown")
        action = payload.get("action", "")

        logger.info(f"GitHub App webhook event: {event_type}.{action}")

        # Handle installation events specially
        if event_type == "installation":
            return await _handle_installation_event(payload, action)

        # For other events, route to existing GitHub webhook processing
        # First, we need to determine the tenant from the installation
        installation_id = payload.get("installation", {}).get("id")
        if not installation_id:
            logger.error("No installation ID found in GitHub App webhook")
            raise HTTPException(status_code=400, detail="Missing installation ID")

        # Look up tenant by installation ID
        tenant_id = await _resolve_tenant_by_installation_id(installation_id)
        if not tenant_id:
            logger.error(f"No tenant found for installation ID {installation_id}")
            raise HTTPException(status_code=404, detail="Tenant not found for installation")

        webhook_metadata = _extract_webhook_metadata("github", headers, body_str)

        # Add all webhook metadata to logging context with prefix
        tracking_context = {f"webhook_meta_{key}": value for key, value in webhook_metadata.items()}

        # Continue processing with verified data in LogContext
        with LogContext(tenant_id=tenant_id, **tracking_context):
            logger.info(f"GitHub App webhook verification successful: {event_type}.{action}")

            # Publish to queues
            sqs_client: SQSClient = request.app.state.sqs_client
            message_ids = await _publish_to_queues(
                sqs_client, body_str, headers, tenant_id, "github"
            )

            if not message_ids:
                logger.error("Failed to publish github webhook to any queues")
                raise HTTPException(
                    status_code=500, detail="Failed to publish webhook to processing queues"
                )

            logger.info(
                f"Successfully processed github webhook for tenant {tenant_id}",
                message_count=len(message_ids),
            )
            return WebhookResponse(
                success=True,
                message=f"Webhook processed successfully, published to {len(message_ids)} queue(s)",
                tenant_id=tenant_id,
                message_id=message_ids[0] if message_ids else None,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing GitHub App webhook: {e}", **webhook_metadata)
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


async def _handle_installation_event(payload: dict, action: str) -> WebhookResponse:
    """Handle GitHub App installation events.

    Args:
        payload: Webhook payload
        action: Installation action (created, deleted, etc.)
    """
    installation = payload.get("installation", {})
    installation_id = installation.get("id")

    if not installation_id:
        logger.error("Missing installation ID in GitHub App installation event")
        raise HTTPException(status_code=400, detail="Missing installation ID")

    account = installation.get("account", {})
    organization = account.get("login", "")
    account_type = account.get("type", "")

    if not organization:
        logger.error("Missing organization login in GitHub App installation event")
        raise HTTPException(status_code=400, detail="Missing organization information")

    logger.info(
        f"GitHub App installation {action}: {installation_id} for {organization} ({account_type})"
    )

    if action == "created":
        # Note: The actual connector record is created by the admin-backend when the
        # installation is saved via POST /api/github/installation
        return WebhookResponse(
            success=True,
            message=f"GitHub App installed for org {organization}",
        )

    elif action == "deleted":
        repo = ConnectorInstallationsRepository()
        connector_installation = await repo.get_by_type_and_external_id(
            ConnectorType.GITHUB, str(installation_id), exclude_disconnected=False
        )

        if connector_installation:
            await repo.mark_disconnected(connector_installation.id)
            logger.info(f"Marked GitHub App installation {installation_id} as disconnected")
        else:
            logger.warning(
                f"GitHub App installation {installation_id} not found in database during deletion"
            )

        return WebhookResponse(
            success=True,
            message=f"GitHub App installation {installation_id} deleted",
        )

    # For other installation actions, just acknowledge
    return WebhookResponse(
        success=True, message=f"GitHub App installation {action} processed", tenant_id=None
    )


async def _resolve_tenant_by_installation_id(installation_id: int) -> str | None:
    """Resolve tenant ID by GitHub App installation ID.

    Returns:
        Tenant ID if found, None otherwise
    """
    repo = ConnectorInstallationsRepository()
    connector_installation = await repo.get_by_type_and_external_id(
        ConnectorType.GITHUB, str(installation_id)
    )

    if connector_installation:
        logger.info(
            f"Found tenant {connector_installation.tenant_id} for installation ID {installation_id}"
        )
        return connector_installation.tenant_id

    logger.warning(f"No tenant found for installation ID {installation_id}")
    return None


async def _resolve_tenant_by_portal_id(portal_id: int) -> str | None:
    """Resolve tenant ID by HubSpot portal ID.

    Returns:
        Tenant ID if found, None otherwise
    """
    repo = ConnectorInstallationsRepository()
    connector_installation = await repo.get_by_type_and_external_id(
        ConnectorType.HUBSPOT, str(portal_id)
    )

    if connector_installation:
        logger.info(
            f"Found tenant {connector_installation.tenant_id} for HubSpot portal ID {portal_id}"
        )
        return connector_installation.tenant_id

    logger.warning(f"No tenant found for HubSpot portal ID {portal_id}")
    return None


async def _resolve_tenant_by_linear_org_id(organization_id: str) -> str | None:
    """Resolve tenant ID by Linear organization ID.

    Queries the connector_installations table in the control database to find the tenant
    associated with the given Linear organization ID.

    Args:
        organization_id: Linear organization ID from webhook payload

    Returns:
        Tenant ID if found, None otherwise
    """
    try:
        repo = ConnectorInstallationsRepository()
        connector_installation = await repo.get_by_type_and_external_id(
            ConnectorType.LINEAR, organization_id
        )

        if connector_installation:
            logger.info(
                f"Found tenant {connector_installation.tenant_id} for Linear organization ID {organization_id}"
            )
            return connector_installation.tenant_id

        logger.warning(f"No tenant found for Linear organization ID {organization_id}")
        return None

    except Exception as e:
        logger.error(f"Error resolving tenant by Linear organization ID: {e}")
        return None


async def handle_hubspot_webhook(request: Request) -> WebhookResponse:
    """Handle HubSpot webhooks.

    HubSpot sends webhook events for deals, companies, and other CRM objects.
    HubSpot doesn't support custom webhook URLs per installation,
    so we need to resolve the tenant using the portal_id from the webhook payload.
    """
    # Initialize webhook_metadata for logging
    webhook_metadata: dict[str, str | int] = {"payload_size": 0}

    try:
        headers = dict(request.headers)
        body = await request.body()
        body_str = body.decode("utf-8")

        # Extract metadata for observability
        webhook_metadata = extract_hubspot_webhook_metadata(headers, body_str)
        logger.info("Received HubSpot webhook", **webhook_metadata)

        # Verify using HubSpot verifier (uses global secret, tenant_id empty)
        await _verify_and_raise(
            HubSpotWebhookVerifier(),
            headers,
            body,
            tenant_id="",  # HubSpot uses global secret, not per-tenant
            source_type="hubspot",
            request=request,
            request_url=str(request.url),
        )

        # Parse the JSON payload (HubSpot sends an array of events)
        events = json.loads(body_str)

        # Deduplicate events to get unique objects per portal
        events_by_portal = deduplicate_hubspot_events(events)

        # Resolve tenants and send messages
        events_by_tenant = {}
        failed_count = 0

        for portal_id_str, objects in events_by_portal.items():
            # Resolve tenant_id using portal_id
            portal_id = int(portal_id_str)
            tenant_id = await _resolve_tenant_by_portal_id(portal_id)

            if not tenant_id:
                logger.warning(f"No tenant found for HubSpot portal_id {portal_id}")
                failed_count += 1
                continue

            events_by_tenant[tenant_id] = objects

        # Send one message per tenant with deduplicated objects
        message_count = 0
        for tenant_id, objects in events_by_tenant.items():
            # Create message body with unique objects
            message_body = {
                "companies": list(objects["companies"]),
                "deals": list(objects["deals"]),
                "tickets": list(objects["tickets"]),
                "contacts": list(objects["contacts"]),
                "association_changes": {
                    "companies": list(objects.get("association_changes", {}).get("companies", [])),
                    "deals": list(objects.get("association_changes", {}).get("deals", [])),
                },
            }

            if (
                message_body["companies"]
                or message_body["deals"]
                or message_body["tickets"]
                or message_body["contacts"]
            ):
                logger.info(
                    f"Processing tenant: {tenant_id}: companies {len(message_body['companies'])}, deals {len(message_body['deals'])}, tickets {len(message_body['tickets'])}, contacts {len(message_body['contacts'])}"
                )
                sqs_client: SQSClient = request.app.state.sqs_client
                await _publish_to_queues(
                    sqs_client=sqs_client,
                    body=json.dumps(message_body),
                    headers=headers,
                    tenant_id=tenant_id,
                    source_type="hubspot",
                )
                message_count += 1
            else:
                logger.info(f"No objects in webhook for tenant {tenant_id}")
                continue

        # Return success response
        return WebhookResponse(
            success=True,
            message=f"Processed {len(events)} HubSpot events for {message_count} tenants",
            tenant_id=next(iter(events_by_tenant.keys())) if events_by_tenant else None,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Unexpected error processing HubSpot webhook: {e}",
            **webhook_metadata,
        )
        raise HTTPException(status_code=500, detail=f"Internal server error: {e}")


def _extract_jira_event_payload_from_body(body_str: str) -> dict:
    """Extract Jira event payload from either direct or webtrigger format.

    Args:
        body_str: Request body as string

    Returns:
        The actual event payload dictionary
    """
    payload = json.loads(body_str)

    # If webtrigger format, extract the actual event from body
    if "method" in payload and "body" in payload and "context" in payload:
        return json.loads(payload["body"])

    # Otherwise return direct payload
    return payload


async def handle_jira_webhook(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle Jira webhook processing with tenant ID."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received jira webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    await _store_jira_oauth_token(request, tenant_id)

    try:
        event_payload = _extract_jira_event_payload_from_body(body_str)
        logger.debug(f"Jira webhook received with eventType: {event_payload.get('eventType')}")

        # Handle custom Grapevine events that require Forge JWT authentication
        if event_payload.get("eventType") == "avi:grapevine:configured:signing-secret":
            return await _handle_jira_configuration_event(request, event_payload, tenant_id)
        elif event_payload.get("eventType") == "avi:grapevine:backfill":
            return await _handle_jira_backfill_event(request, tenant_id)

    except json.JSONDecodeError:
        logger.info("Failed to parse JSON, processing as regular webhook")

    # Verify using Jira verifier
    await _verify_and_raise(JiraWebhookVerifier(), headers, body, tenant_id, "jira", request)

    return await _process_verified_webhook(request, "jira", tenant_id, body_str, headers)


async def _verify_forge_jwt_for_source(request: Request, source: str, tenant_id: str) -> None:
    """Verify Forge JWT for a source. Raises HTTPException on failure.

    Args:
        request: FastAPI request object
        source: Source name ("jira" or "confluence")
        tenant_id: Tenant ID for logging

    Raises:
        HTTPException: If app ID not configured or JWT verification fails
    """
    # Get app ID based on source
    if source == "jira":
        app_id = get_jira_app_id()
        source_display = "Jira"
    elif source == "confluence":
        app_id = get_confluence_app_id()
        source_display = "Confluence"
    else:
        raise ValueError(f"Unknown source: {source}")

    if not app_id:
        logger.error(f"{source.upper()}_APP_ID not configured, cannot verify Forge JWT")
        raise HTTPException(
            status_code=500, detail=f"{source_display} Forge app ID not configured on server"
        )

    headers = dict(request.headers)
    try:
        verify_forge_request(headers, app_id)
        logger.info(f"Successfully verified Forge JWT for {source_display}, tenant {tenant_id}")
    except ValueError as e:
        logger.warning(f"Forge JWT verification failed for {source_display}: {e}")
        raise HTTPException(status_code=401, detail=f"Forge authentication failed: {e}")
    except Exception as e:
        logger.error(f"Error verifying Forge JWT for {source_display}: {e}")
        raise HTTPException(status_code=401, detail=f"Forge authentication error: {e}")


async def _store_jira_oauth_token(request: Request, tenant_id: str) -> None:
    headers = dict(request.headers)
    oauth_token = headers.get("x-forge-oauth-system")
    if oauth_token:
        try:
            webhook_processor: WebhookProcessor = request.app.state.webhook_processor
            ssm_client: SSMClient = webhook_processor.ssm_client
            await ssm_client.store_api_key(tenant_id, "JIRA_SYSTEM_OAUTH_TOKEN", oauth_token)
        except Exception as e:
            logger.error(f"Failed to store OAuth token in SSM for tenant {tenant_id}: {e}")


async def _handle_jira_backfill_event(request: Request, tenant_id: str) -> WebhookResponse:
    try:
        await _verify_forge_jwt_for_source(request, "jira", tenant_id)

        logger.info(f"Triggering Jira root backfill for tenant {tenant_id}")

        sqs_client: SQSClient = request.app.state.sqs_client
        backfill_message = JiraApiBackfillRootConfig(
            tenant_id=tenant_id,
        )

        message_id = await sqs_client.send_backfill_ingest_message(backfill_message)

        if message_id:
            logger.info(
                f"Successfully queued Jira root backfill job for tenant {tenant_id}, message ID: {message_id}"
            )
            return WebhookResponse(
                success=True,
                message=f"Jira backfill job queued successfully: {message_id}",
                tenant_id=tenant_id,
            )
        else:
            logger.error(f"Failed to queue Jira root backfill job for tenant {tenant_id}")
            return WebhookResponse(
                success=False,
                message="Failed to queue backfill job",
                tenant_id=tenant_id,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling Jira backfill event: {e}")
        return WebhookResponse(
            success=False,
            message=f"Error handling backfill event: {e}",
            tenant_id=tenant_id,
        )


async def _handle_jira_configuration_event(
    request: Request, payload: dict, tenant_id: str
) -> WebhookResponse:
    try:
        await _verify_forge_jwt_for_source(request, "jira", tenant_id)

        webtrigger_url = payload.get("webtriggerUrl")
        cloud_id = payload.get("cloudId")

        if not webtrigger_url:
            raise ValueError("Missing webtriggerUrl in configuration event")

        if not cloud_id:
            raise ValueError("Missing cloudId in configuration event")

        await set_tenant_config_value("JIRA_WEBTRIGGER_BACKFILL_URL", webtrigger_url, tenant_id)
        await set_tenant_config_value("JIRA_CLOUD_ID", cloud_id, tenant_id)

        # Create or update connector record (using cloud_id as external_id)
        try:
            repo = ConnectorInstallationsRepository()
            existing_connector_installation = await repo.get_by_tenant_type_and_external_id(
                tenant_id, ConnectorType.JIRA, cloud_id
            )

            if existing_connector_installation:
                await repo.update_status(existing_connector_installation.id, ConnectorStatus.ACTIVE)
                logger.info(
                    f"Updated existing Jira connector to active for tenant {tenant_id}",
                    extra={"connector_id": str(existing_connector_installation.id)},
                )
            else:
                connector_installation = await repo.create(
                    tenant_id=tenant_id,
                    connector_type=ConnectorType.JIRA,
                    external_id=cloud_id,
                    external_metadata={},
                    status=ConnectorStatus.ACTIVE,
                )
                logger.info(
                    f"Created new Jira connector for tenant {tenant_id}",
                    extra={"connector_id": str(connector_installation.id)},
                )
        except Exception as connector_error:
            logger.error(
                f"Failed to create/update Jira connector record for tenant {tenant_id}: {connector_error}"
            )
            # Don't fail the configuration, just log the error

        async with aiohttp.ClientSession() as session:
            trigger_payload = {"eventType": "avi:grapevine:backfill", "tenant_id": tenant_id}

            async with session.post(
                webtrigger_url, json=trigger_payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    logger.info(f"Successfully triggered Jira backfill for tenant {tenant_id}")
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Failed to trigger Jira backfill: HTTP {response.status} - {error_text}"
                    )

        return WebhookResponse(
            success=True,
            message=f"Jira configuration completed for tenant {tenant_id}",
            tenant_id=tenant_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle Jira configuration event: {e}")
        return WebhookResponse(
            success=False,
            message=f"Configuration processing failed: {e}",
            tenant_id=tenant_id,
        )


async def handle_confluence_webhook(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle Confluence webhook processing with tenant ID."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received confluence webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    await _store_confluence_oauth_token(request, tenant_id)

    try:
        event_payload = _extract_confluence_event_payload_from_body(body_str)
        logger.debug(
            f"Confluence webhook received with eventType: {event_payload.get('eventType')}"
        )

        # Handle custom Grapevine events that require Forge JWT authentication
        if event_payload.get("eventType") == "avi:grapevine:configured:signing-secret":
            return await _handle_confluence_configuration_event(request, event_payload, tenant_id)
        elif event_payload.get("eventType") == "avi:grapevine:backfill":
            return await _handle_confluence_backfill_event(request, tenant_id)

    except json.JSONDecodeError:
        logger.info("Failed to parse JSON, processing as regular webhook")

    # Verify using Confluence verifier
    await _verify_and_raise(
        ConfluenceWebhookVerifier(), headers, body, tenant_id, "confluence", request
    )

    return await _process_verified_webhook(request, "confluence", tenant_id, body_str, headers)


async def _store_confluence_oauth_token(request: Request, tenant_id: str) -> None:
    headers = dict(request.headers)
    oauth_token = headers.get("x-forge-oauth-system")
    if oauth_token:
        try:
            webhook_processor: WebhookProcessor = request.app.state.webhook_processor
            ssm_client: SSMClient = webhook_processor.ssm_client
            await ssm_client.store_api_key(tenant_id, "CONFLUENCE_SYSTEM_OAUTH_TOKEN", oauth_token)
        except Exception as e:
            logger.error(f"Failed to store OAuth token in SSM for tenant {tenant_id}: {e}")


def _extract_confluence_event_payload_from_body(body_str: str) -> dict:
    """Extract event payload from Confluence webhook request body.

    Args:
        body_str: Request body as string

    Returns:
        The actual event payload dictionary
    """
    payload = json.loads(body_str)

    # If webtrigger format, extract the actual event from body
    if "method" in payload and "body" in payload and "context" in payload:
        return json.loads(payload["body"])

    # Otherwise return direct payload
    return payload


async def _handle_confluence_backfill_event(request: Request, tenant_id: str) -> WebhookResponse:
    try:
        await _verify_forge_jwt_for_source(request, "confluence", tenant_id)

        logger.info(f"Triggering Confluence root backfill for tenant {tenant_id}")

        sqs_client: SQSClient = request.app.state.sqs_client
        backfill_message = ConfluenceApiBackfillRootConfig(
            tenant_id=tenant_id,
        )

        await sqs_client.send_backfill_ingest_message(backfill_message)
        logger.info(f"Successfully sent Confluence backfill message for tenant {tenant_id}")

        return WebhookResponse(
            success=True,
            message=f"Confluence backfill triggered for tenant {tenant_id}",
            tenant_id=tenant_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle Confluence backfill event: {e}")
        return WebhookResponse(
            success=False,
            message=f"Backfill trigger failed: {e}",
            tenant_id=tenant_id,
        )


async def _handle_confluence_configuration_event(
    request: Request, payload: dict, tenant_id: str
) -> WebhookResponse:
    try:
        await _verify_forge_jwt_for_source(request, "confluence", tenant_id)

        webtrigger_url = payload.get("webtriggerUrl")
        cloud_id = payload.get("cloudId")
        site_url = payload.get("siteUrl")

        logger.info(f"Confluence configuration event for tenant {tenant_id}")

        if webtrigger_url:
            await set_tenant_config_value(
                "CONFLUENCE_WEBTRIGGER_BACKFILL_URL", webtrigger_url, tenant_id
            )

        if cloud_id:
            await set_tenant_config_value("CONFLUENCE_CLOUD_ID", cloud_id, tenant_id)

        if site_url:
            await set_tenant_config_value("CONFLUENCE_SITE_URL", site_url, tenant_id)

        # Create or update connector record (using cloud_id as external_id)
        if cloud_id:
            try:
                repo = ConnectorInstallationsRepository()
                existing_connector_installation = await repo.get_by_tenant_type_and_external_id(
                    tenant_id, ConnectorType.CONFLUENCE, cloud_id
                )

                if existing_connector_installation:
                    await repo.update_status(
                        existing_connector_installation.id, ConnectorStatus.ACTIVE
                    )
                    logger.info(
                        f"Updated existing Confluence connector to active for tenant {tenant_id}",
                        extra={"connector_id": str(existing_connector_installation.id)},
                    )
                else:
                    connector_installation = await repo.create(
                        tenant_id=tenant_id,
                        connector_type=ConnectorType.CONFLUENCE,
                        external_id=cloud_id,
                        external_metadata={},
                        status=ConnectorStatus.ACTIVE,
                    )
                    logger.info(
                        f"Created new Confluence connector for tenant {tenant_id}",
                        extra={"connector_id": str(connector_installation.id)},
                    )
            except Exception as connector_error:
                logger.error(
                    f"Failed to create/update Confluence connector record for tenant {tenant_id}: {connector_error}"
                )
                # Don't fail the configuration, just log the error

        # Trigger backfill via webtrigger URL if available
        if webtrigger_url:
            async with aiohttp.ClientSession() as session:
                trigger_payload = {"eventType": "avi:grapevine:backfill", "tenant_id": tenant_id}

                response = await session.post(webtrigger_url, json=trigger_payload)
                if response.status == 200:
                    logger.info(
                        f"Successfully triggered Confluence backfill for tenant {tenant_id}"
                    )
                else:
                    error_text = await response.text()
                    logger.error(
                        f"Failed to trigger Confluence backfill: HTTP {response.status} - {error_text}"
                    )

        return WebhookResponse(
            success=True,
            message=f"Confluence configuration completed for tenant {tenant_id}",
            tenant_id=tenant_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to handle Confluence configuration event: {e}")
        return WebhookResponse(
            success=False,
            message=f"Configuration processing failed: {e}",
            tenant_id=tenant_id,
        )


async def handle_gong_webhook(request: Request, tenant_id: str) -> WebhookResponse | Response:
    """Handle Gong webhook signed with tenant-provided public key.

    Gong sends test webhooks with isTest=true when users verify the webhook setup.
    For test webhooks, we verify the signature and return 200.
    For real webhooks, we verify and queue them for processing.
    """
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received gong webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Verify using Gong verifier (RS256 JWT)
    await _verify_and_raise(GongWebhookVerifier(), headers, body, tenant_id, "gong", request)

    # Check if this is a test webhook from Gong UI
    try:
        payload = json.loads(body_str)
        if payload.get("isTest", False):
            logger.info(
                "Gong test webhook verified successfully",
                tenant_id=tenant_id,
            )

            # Store verification success flag for frontend polling
            # This allows the UI to show "verified" status
            await set_tenant_config_value("GONG_WEBHOOK_VERIFIED", "true", tenant_id)

            return Response(status_code=200)
    except json.JSONDecodeError:
        logger.warning("Failed to parse Gong webhook payload as JSON")

    # Process real webhook
    return await _process_verified_webhook(request, "gong", tenant_id, body_str, headers)


async def handle_custom_collection_webhook(
    request: Request,
    tenant_id: str,
    collection_name: str,
) -> WebhookResponse:
    """Handle custom collection webhook with API key authentication.

    Only available in local and staging environments for testing.

    Args:
        request: FastAPI request
        tenant_id: Tenant ID from URL path
        collection_name: Collection name from URL path

    Returns:
        WebhookResponse indicating success/failure

    Raises:
        HTTPException: On validation or auth failures
    """
    # Restrict to non-production environments only
    environment = get_grapevine_environment()
    if environment not in ["local", "staging"]:
        logger.warning(
            f"Custom collections webhook rejected in {environment} environment",
            tenant_id=tenant_id,
            collection_name=collection_name,
        )
        raise HTTPException(
            status_code=403,
            detail="Custom collections are only available in local and staging environments",
        )

    validate_tenant_id(tenant_id)

    # Parse body
    body = await request.body()
    body_str = body.decode("utf-8")

    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in custom collection webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Validate required fields
    if "id" not in payload:
        raise HTTPException(status_code=400, detail="Missing required field: id")
    if "content" not in payload:
        raise HTTPException(status_code=400, detail="Missing required field: content")
    if "metadata" not in payload:
        raise HTTPException(status_code=400, detail="Missing required field: metadata")

    # Validate types
    if not isinstance(payload["id"], str):
        raise HTTPException(status_code=400, detail="Field 'id' must be a string")
    if not isinstance(payload["content"], str):
        raise HTTPException(status_code=400, detail="Field 'content' must be a string")
    if not isinstance(payload["metadata"], dict):
        raise HTTPException(status_code=400, detail="Field 'metadata' must be an object")

    # Authenticate using API key
    api_key = request.headers.get("authorization", "").replace("Bearer ", "").strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Verify API key
    verified_tenant_id = await verify_api_key(api_key)
    if not verified_tenant_id or verified_tenant_id != tenant_id:
        logger.warning(f"Invalid API key for tenant {tenant_id}")
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Inject collection_name into payload for downstream processing
    payload["collection_name"] = collection_name

    # Add timestamp if not provided
    if "source_created_at" not in payload:
        payload["source_created_at"] = datetime.now(UTC).isoformat()

    # Log acceptance
    logger.info(
        "Accepted custom collection document",
        collection_name=collection_name,
        item_id=payload["id"],
        content_length=len(payload["content"]),
    )

    # Publish to SQS for processing
    sqs_client: SQSClient = request.app.state.sqs_client
    message_id = await sqs_client.send_ingest_webhook_message(
        webhook_body=json.dumps(payload),
        webhook_headers=dict(request.headers),
        tenant_id=tenant_id,
        source_type="custom",
    )

    if not message_id:
        logger.error("Failed to publish custom collection webhook to SQS")
        raise HTTPException(
            status_code=500,
            detail="Failed to publish webhook to processing queue",
        )

    return WebhookResponse(
        success=True,
        message=f"Document '{payload['id']}' accepted for collection '{collection_name}'",
        tenant_id=tenant_id,
        message_id=message_id,
    )


async def handle_trello_webhook(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle Trello webhook processing with tenant ID."""
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received trello webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Verify using Trello verifier
    await _verify_and_raise(TrelloWebhookVerifier(), headers, body, tenant_id, "trello", request)

    return await _process_verified_webhook(request, "trello", tenant_id, body_str, headers)


async def handle_attio_webhook(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle Attio webhook processing with tenant ID.

    Attio sends webhooks for record, note, and task events.
    Signature verification uses SHA256 HMAC with the webhook secret.
    """
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received attio webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Verify using Attio verifier
    await _verify_and_raise(AttioWebhookVerifier(), headers, body, tenant_id, "attio", request)

    return await _process_verified_webhook(request, "attio", tenant_id, body_str, headers)


async def _resolve_tenant_by_figma_team_id(team_id: str) -> str | None:
    """Resolve tenant ID by Figma team ID.

    Queries the connector_installations table in the control database to find the tenant
    associated with the given Figma team ID. The team_id is stored in external_metadata
    (synced_team_ids or selected_team_ids arrays).

    Args:
        team_id: Figma team ID from webhook payload

    Returns:
        Tenant ID if found, None otherwise
    """
    try:
        repo = ConnectorInstallationsRepository()
        # Search for Figma connector with this team_id in external_metadata
        connector = await repo.get_figma_connector_by_team_id(team_id)

        if connector:
            logger.info(f"Found tenant {connector.tenant_id} for Figma team ID {team_id}")
            return connector.tenant_id

        logger.warning(f"No tenant found for Figma team ID {team_id}")
        return None

    except Exception as e:
        logger.error(f"Error resolving tenant by Figma team ID: {e}")
        return None


async def handle_figma_webhook(request: Request) -> WebhookResponse:
    """Handle Figma webhook (centralized OAuth - resolves tenant from team_id).

    Figma sends webhooks for file updates, deletions, comments, and library publishes.
    The team_id in the payload is used to resolve the tenant.
    Signature verification uses HMAC-SHA256 with the webhook passcode.
    """
    webhook_metadata: dict[str, str | int | bool] = {"payload_size": 0, "payload_size_human": "0 B"}

    try:
        headers = dict(request.headers)
        body = await request.body()
        body_str = body.decode("utf-8")

        logger.info(
            "Received Figma webhook",
            payload_size=len(body_str),
            payload_size_human=format_size(len(body_str)),
        )

        # Extract team_id from payload for tenant resolution
        team_id = extract_figma_team_id(body_str)
        if not team_id:
            logger.warning("No team_id found in Figma webhook payload")
            raise HTTPException(
                status_code=400,
                detail="Missing team_id in Figma webhook payload",
            )

        # Resolve tenant ID from team_id
        tenant_id = await _resolve_tenant_by_figma_team_id(team_id)
        if not tenant_id:
            logger.warning(f"No tenant found for Figma team ID {team_id}")
            raise HTTPException(
                status_code=404,
                detail=f"No tenant found for Figma team ID {team_id}",
            )

        with LogContext(tenant_id=tenant_id, figma_team_id=team_id):
            logger.info(f"Processing Figma webhook for team {team_id}")
            validate_tenant_id(tenant_id)

            # Verify using Figma verifier
            await _verify_and_raise(
                FigmaWebhookVerifier(), headers, body, tenant_id, "figma", request
            )

            return await _process_verified_webhook(request, "figma", tenant_id, body_str, headers)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Figma webhook: {e}", **webhook_metadata)
        raise HTTPException(status_code=500, detail="Internal server error")


async def handle_figma_webhook_with_tenant(request: Request, tenant_id: str) -> WebhookResponse:
    """Handle Figma webhook with tenant ID from URL path.

    For webhooks registered with tenant-specific URLs (/{tenant_id}/webhooks/figma).
    Signature verification uses HMAC-SHA256 with the webhook passcode.
    """
    validate_tenant_id(tenant_id)

    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    logger.info(
        "Received figma webhook",
        payload_size=len(body_str),
        payload_size_human=format_size(len(body_str)),
    )

    # Verify using Figma verifier
    await _verify_and_raise(FigmaWebhookVerifier(), headers, body, tenant_id, "figma", request)

    return await _process_verified_webhook(request, "figma", tenant_id, body_str, headers)
