"""Route definitions for gatekeeper service."""

import re

from fastapi import APIRouter, HTTPException, Request, Response

from src.ingest.gatekeeper.custom_data_handlers import (
    CustomDataDeleteResponse,
    CustomDataDocumentResponse,
    CustomDataIngestResponse,
    handle_custom_data_delete,
    handle_custom_data_get,
    handle_custom_data_ingest,
    handle_custom_data_update,
)
from src.ingest.gatekeeper.models import WebhookResponse
from src.ingest.gatekeeper.utils import (
    check_slack_url_verification,
    extract_tenant_from_confluence_signing_secret,
    extract_tenant_from_jira_signing_secret,
    extract_tenant_from_request,
    extract_tenant_from_slack_request,
)
from src.ingest.gatekeeper.webhook_handlers import (
    handle_attio_webhook,
    handle_confluence_webhook,
    handle_custom_collection_webhook,
    handle_figma_webhook,
    handle_figma_webhook_with_tenant,
    handle_gather_webhook,
    handle_github_app_webhook,
    handle_github_webhook,
    handle_gong_webhook,
    handle_google_drive_webhook,
    handle_google_email_webhook,
    handle_hubspot_webhook,
    handle_jira_webhook,
    handle_linear_oauth_webhook,
    handle_linear_webhook,
    handle_notion_webhook,
    handle_slack_webhook,
    handle_trello_webhook,
)
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)

router = APIRouter()


def validate_collection_name(name: str) -> None:
    """Validate collection name is URL-safe.

    Rules:
    - Alphanumeric, dashes, underscores only
    - 1-64 characters

    Raises:
        HTTPException: If name is invalid
    """
    if not re.match(r"^[a-zA-Z0-9_-]{1,64}$", name):
        raise HTTPException(
            status_code=400,
            detail="Collection name must be alphanumeric, dashes, or underscores (max 64 chars)",
        )


# GitHub App webhook endpoint (no tenant extraction needed)
@router.post("/webhooks/github_app", response_model=WebhookResponse)
async def github_app_webhook(request: Request):
    """Process GitHub App webhook including installation events."""
    result = await handle_github_app_webhook(request)
    # Add log context if tenant was resolved
    if result.tenant_id:
        with LogContext(tenant_id=result.tenant_id):
            logger.info("GitHub App webhook processed successfully")
    return result


# HubSpot webhook endpoint (uses portal ID for tenant resolution)
@router.post("/webhooks/hubspot", response_model=WebhookResponse)
async def hubspot_webhook(request: Request):
    """Process HubSpot webhook using portal ID for tenant resolution."""
    result = await handle_hubspot_webhook(request)
    # Add log context if tenant was resolved
    if result.tenant_id:
        with LogContext(tenant_id=result.tenant_id):
            logger.info("HubSpot webhook processed successfully")
    return result


# Linear OAuth webhook endpoint (uses organization ID from payload for tenant resolution)
@router.post("/webhooks/linear/oauth", response_model=WebhookResponse)
async def linear_oauth_webhook(request: Request):
    """Process Linear OAuth webhook using organization ID for tenant resolution.

    This endpoint is for Linear OAuth applications that have application-level webhooks.
    The tenant is identified by extracting the organization ID from the webhook payload.
    """
    result = await handle_linear_oauth_webhook(request)
    # Add log context if tenant was resolved
    if result.tenant_id:
        with LogContext(tenant_id=result.tenant_id):
            logger.info("Linear OAuth webhook processed successfully")
    return result


# Gong webhook endpoint (uses JWT payload for tenant resolution)
@router.post("/webhooks/gong", response_model=WebhookResponse)
async def gong_webhook(request: Request):
    """Process Gong webhook signed JWT payloads."""
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id):
        result = await handle_gong_webhook(request, tenant_result.tenant_id)
        logger.info("Gong webhook processed successfully")
        return result


# Original endpoints using Host header for tenant extraction
@router.post("/webhooks/github", response_model=WebhookResponse)
async def github_webhook(request: Request):
    """Process GitHub webhook."""
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id):
        return await handle_github_webhook(request, tenant_result.tenant_id)


@router.post("/webhooks/slack", response_model=WebhookResponse)
async def slack_webhook(request: Request):
    """Process Slack webhook with centralized OAuth support.

    For centralized OAuth apps, extracts team_id from payload to resolve tenant.
    Falls back to Host header for legacy per-tenant apps.
    """
    body = await request.body()
    body_str = body.decode("utf-8")

    # Check for URL verification challenge first
    challenge = check_slack_url_verification(body_str)
    if challenge:
        return Response(content=challenge, media_type="text/plain")

    headers = dict(request.headers)
    tenant_result = await extract_tenant_from_slack_request(body_str, headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id):
        return await handle_slack_webhook(request, tenant_result.tenant_id)


@router.post("/webhooks/linear", response_model=WebhookResponse)
async def linear_webhook(request: Request):
    """Process Linear webhook."""
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id):
        return await handle_linear_webhook(request, tenant_result.tenant_id)


@router.post("/webhooks/notion", response_model=WebhookResponse)
async def notion_webhook(request: Request):
    """Process Notion webhook."""
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id):
        return await handle_notion_webhook(request, tenant_result.tenant_id)


@router.post("/webhooks/google-drive", response_model=WebhookResponse)
async def google_drive_webhook(request: Request):
    """Process Google Drive webhook."""
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id):
        return await handle_google_drive_webhook(request, tenant_result.tenant_id)


@router.post("/webhooks/google-email", response_model=WebhookResponse)
async def google_email_webhook(request: Request):
    """Process Google Email webhook."""
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id):
        return await handle_google_email_webhook(request, tenant_result.tenant_id)


@router.post("/webhooks/jira", response_model=WebhookResponse)
async def jira_webhook(request: Request):
    """Process Jira webhook."""
    headers = dict(request.headers)
    signing_secret = headers.get("x-jira-signing-secret")

    tenant_id = await extract_tenant_from_jira_signing_secret(signing_secret)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Failed to extract tenant ID")

    with LogContext(tenant_id=tenant_id):
        return await handle_jira_webhook(request, tenant_id)


@router.post("/webhooks/confluence", response_model=WebhookResponse)
async def confluence_webhook(request: Request):
    """Process Confluence webhook."""
    headers = dict(request.headers)
    signing_secret = headers.get("x-confluence-signing-secret")

    tenant_id = await extract_tenant_from_confluence_signing_secret(signing_secret)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="Failed to extract tenant ID")

    with LogContext(tenant_id=tenant_id):
        return await handle_confluence_webhook(request, tenant_id)


@router.post("/webhooks/gather", response_model=WebhookResponse)
async def gather_webhook(request: Request):
    """Process Gather webhook."""
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id):
        return await handle_gather_webhook(request, tenant_result.tenant_id)


# New endpoints supporting tenant ID in URL path
@router.post("/{tenant_id}/webhooks/github", response_model=WebhookResponse)
async def github_webhook_with_tenant(request: Request, tenant_id: str):
    """Process GitHub webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_github_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/slack", response_model=WebhookResponse)
async def slack_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Slack webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_slack_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/linear", response_model=WebhookResponse)
async def linear_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Linear webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_linear_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/notion", response_model=WebhookResponse)
async def notion_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Notion webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_notion_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/google-drive", response_model=WebhookResponse)
async def google_drive_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Google Drive webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_google_drive_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/google-email", response_model=WebhookResponse)
async def google_email_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Google Email webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_google_email_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/jira", response_model=WebhookResponse)
async def jira_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Jira webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_jira_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/confluence", response_model=WebhookResponse)
async def confluence_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Confluence webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_confluence_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/gong", response_model=WebhookResponse)
async def gong_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Gong webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_gong_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/gather", response_model=WebhookResponse)
async def gather_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Gather webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_gather_webhook(request, tenant_id)


@router.post("/webhooks/attio", response_model=WebhookResponse)
async def attio_webhook(request: Request):
    """Process Attio webhook using Host header for tenant resolution."""
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id):
        return await handle_attio_webhook(request, tenant_result.tenant_id)


@router.post("/{tenant_id}/webhooks/attio", response_model=WebhookResponse)
async def attio_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Attio webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_attio_webhook(request, tenant_id)


# Figma webhook endpoints
@router.post("/webhooks/figma", response_model=WebhookResponse)
async def figma_webhook(request: Request):
    """Process Figma webhook using team_id for tenant resolution.

    Figma sends webhooks for file updates, deletions, comments, and library publishes.
    The tenant is identified by extracting the team_id from the webhook payload.
    """
    result = await handle_figma_webhook(request)
    if result.tenant_id:
        with LogContext(tenant_id=result.tenant_id):
            logger.info("Figma webhook processed successfully")
    return result


@router.post("/{tenant_id}/webhooks/figma", response_model=WebhookResponse)
async def figma_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Figma webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_figma_webhook_with_tenant(request, tenant_id)


@router.head("/{tenant_id}/webhooks/trello")
async def trello_webhook_verify(tenant_id: str):
    """Verify Trello webhook URL (HEAD request for webhook registration)."""
    # Trello sends HEAD request to verify webhook URL is reachable
    # Just return 200 OK to confirm the endpoint exists
    return Response(status_code=200)


@router.post("/{tenant_id}/webhooks/trello", response_model=WebhookResponse)
async def trello_webhook_with_tenant(request: Request, tenant_id: str):
    """Process Trello webhook with tenant ID from URL path."""
    with LogContext(tenant_id=tenant_id):
        return await handle_trello_webhook(request, tenant_id)


@router.post("/{tenant_id}/webhooks/custom/{collection_name}", response_model=WebhookResponse)
async def custom_collection_webhook(request: Request, tenant_id: str, collection_name: str):
    """Process custom collection webhook - auto-creates collection on first POST."""
    validate_collection_name(collection_name)

    with LogContext(tenant_id=tenant_id, collection_name=collection_name):
        return await handle_custom_collection_webhook(request, tenant_id, collection_name)


# Custom Data API endpoints - Host header based (tenant from subdomain)
@router.post("/custom-documents/{slug}", response_model=CustomDataIngestResponse)
async def custom_data_ingest_host(request: Request, slug: str):
    """Ingest custom data documents with tenant ID from Host header.

    Accepts single document or batch of documents. See custom_data_ingest for format details.
    Requires Bearer token authentication with a valid API key for the tenant.
    """
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id, slug=slug):
        return await handle_custom_data_ingest(request, tenant_result.tenant_id, slug)


@router.get("/custom-documents/{slug}/{item_id}", response_model=CustomDataDocumentResponse)
async def custom_data_get_host(request: Request, slug: str, item_id: str):
    """Get a custom data document with tenant ID from Host header.

    Requires Bearer token authentication with a valid API key for the tenant.
    """
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id, slug=slug, item_id=item_id):
        return await handle_custom_data_get(request, tenant_result.tenant_id, slug, item_id)


@router.put("/custom-documents/{slug}/{item_id}", response_model=CustomDataIngestResponse)
async def custom_data_update_host(request: Request, slug: str, item_id: str):
    """Update a custom data document with tenant ID from Host header.

    Requires Bearer token authentication with a valid API key for the tenant.
    """
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id, slug=slug, item_id=item_id):
        return await handle_custom_data_update(request, tenant_result.tenant_id, slug, item_id)


@router.delete("/custom-documents/{slug}/{item_id}", response_model=CustomDataDeleteResponse)
async def custom_data_delete_host(request: Request, slug: str, item_id: str):
    """Delete a custom data document with tenant ID from Host header.

    Requires Bearer token authentication with a valid API key for the tenant.
    """
    headers = dict(request.headers)
    tenant_result = extract_tenant_from_request(headers)

    if tenant_result.error or not tenant_result.tenant_id:
        raise HTTPException(
            status_code=400, detail=f"Failed to extract tenant ID: {tenant_result.error}"
        )

    with LogContext(tenant_id=tenant_result.tenant_id, slug=slug, item_id=item_id):
        return await handle_custom_data_delete(request, tenant_result.tenant_id, slug, item_id)


# Custom Data API endpoints - Path based (tenant from URL)
@router.post("/{tenant_id}/custom-documents/{slug}", response_model=CustomDataIngestResponse)
async def custom_data_ingest(request: Request, tenant_id: str, slug: str):
    """Ingest custom data documents with API key authentication.

    Accepts single document or batch of documents:

    Single document:
    ```json
    {
        "name": "Document Name",
        "content": "Document content...",
        "description": "Optional description",
        "custom_field_1": "value"
    }
    ```

    Batch documents:
    ```json
    {
        "documents": [
            {"name": "Doc 1", "content": "Content 1"},
            {"name": "Doc 2", "content": "Content 2"}
        ]
    }
    ```

    Requires Bearer token authentication with a valid API key for the tenant.
    """
    with LogContext(tenant_id=tenant_id, slug=slug):
        return await handle_custom_data_ingest(request, tenant_id, slug)


@router.get(
    "/{tenant_id}/custom-documents/{slug}/{item_id}",
    response_model=CustomDataDocumentResponse,
)
async def custom_data_get(request: Request, tenant_id: str, slug: str, item_id: str):
    """Get a custom data document by ID.

    Requires Bearer token authentication with a valid API key for the tenant.
    """
    with LogContext(tenant_id=tenant_id, slug=slug, item_id=item_id):
        return await handle_custom_data_get(request, tenant_id, slug, item_id)


@router.put(
    "/{tenant_id}/custom-documents/{slug}/{item_id}", response_model=CustomDataIngestResponse
)
async def custom_data_update(request: Request, tenant_id: str, slug: str, item_id: str):
    """Update a custom data document by ID.

    Updates an existing document with new content. The document must exist.

    ```json
    {
        "name": "Updated Document Name",
        "content": "Updated content...",
        "description": "Updated description",
        "custom_field_1": "updated value"
    }
    ```

    Requires Bearer token authentication with a valid API key for the tenant.
    """
    with LogContext(tenant_id=tenant_id, slug=slug, item_id=item_id):
        return await handle_custom_data_update(request, tenant_id, slug, item_id)


@router.delete(
    "/{tenant_id}/custom-documents/{slug}/{item_id}",
    response_model=CustomDataDeleteResponse,
)
async def custom_data_delete(request: Request, tenant_id: str, slug: str, item_id: str):
    """Delete a custom data document by ID.

    Removes the document from the database and triggers removal from the search index.

    Requires Bearer token authentication with a valid API key for the tenant.
    """
    with LogContext(tenant_id=tenant_id, slug=slug, item_id=item_id):
        return await handle_custom_data_delete(request, tenant_id, slug, item_id)
