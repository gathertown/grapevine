"""Middleware to extract tenant_id from JWT claims and attach it to the request context.

This middleware expects a JWT-authenticated request with a tenant_id claim.

It looks for `tenant_id` in token claims and stores it under `context.state["org_id"]`
(kept as org_id for backward compatibility with existing tools).
Tools can read it if they accept the context parameter.
"""

from __future__ import annotations

import contextlib
import json
from base64 import urlsafe_b64decode
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.clients.tenant_opensearch import TenantScopedOpenSearchClient

import asyncpg
import httpx
from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext

from src.clients.tenant_db import _tenant_db_manager
from src.clients.tenant_opensearch import _tenant_opensearch_manager
from src.mcp.utils.auth_helpers import (
    extract_tenant_id_from_api_key,
    is_api_key_authentication,
    is_api_key_non_billable,
)
from src.utils.config import get_config_value
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def _resolve_workos_org_to_tenant_id(
    control_pool: asyncpg.Pool, workos_org_id: str
) -> str | None:
    """Resolve a WorkOS organization ID to an internal tenant ID.

    Args:
        control_pool: Database connection pool
        workos_org_id: WorkOS organization ID to resolve

    Returns:
        Internal tenant ID if found, None otherwise
    """
    async with control_pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id FROM public.tenants
            WHERE workos_org_id = $1
              AND state = 'provisioned'
            """,
            workos_org_id,
        )
        if row:
            return row["id"]
        return None


async def _get_user_organization_from_workos(user_id: str) -> str | None:
    """Get user's organization ID from WorkOS API.

    Args:
        user_id: WorkOS user ID (from JWT sub claim)

    Returns:
        Organization ID or None if not found
    """
    try:
        workos_api_key = get_config_value("WORKOS_API_KEY")
        if not workos_api_key:
            logger.warning("OrgContextMiddleware - WORKOS_API_KEY not configured")
            return None

        async with httpx.AsyncClient() as client:
            # Get user's organization memberships
            response = await client.get(
                "https://api.workos.com/user_management/organization_memberships",
                headers={"Authorization": f"Bearer {workos_api_key}", "Accept": "application/json"},
                params={"user_id": user_id},
            )

            if response.status_code == 200:
                data = response.json()
                memberships = data.get("data", [])
                if memberships:
                    # Take the first organization membership
                    first_membership = memberships[0]
                    org_id = first_membership.get("organization_id")
                    logger.debug(f"OrgContextMiddleware - Found org_id from WorkOS API: {org_id}")
                    return org_id
                else:
                    logger.debug("OrgContextMiddleware - User has no organization memberships")
                    return None
            else:
                logger.warning(
                    f"OrgContextMiddleware - WorkOS API error: {response.status_code} {response.text}"
                )
                return None

    except Exception as e:
        logger.warning(f"OrgContextMiddleware - Error calling WorkOS API: {e}")
        return None


def _decode_jwt_payload(jwt_token: str) -> dict | None:
    """Decode JWT payload without verification (for extracting claims).

    Args:
        jwt_token: JWT token string

    Returns:
        Decoded payload dict or None if invalid
    """
    try:
        # Split JWT into header.payload.signature
        parts = jwt_token.split(".")
        if len(parts) != 3:
            return None

        # Decode payload (second part)
        payload_b64 = parts[1]
        # Add padding if needed for base64 decoding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
        return payload
    except Exception as e:
        logger.warning(f"Failed to decode JWT payload: {e}")
        return None


def _extract_tenant_id_from_context(context: Context) -> str | None:
    """Extract tenant_id from the context state."""
    return context.get_state("tenant_id")


def _extract_permission_principal_token_from_context(context: Context) -> str | None:
    """Extract permission_principal_token from the context state."""
    return context.get_state("permission_principal_token")


def _extract_non_billable_from_context(context: Context) -> bool:
    """Extract nonBillable flag from the context state.

    Returns True if the request should NOT be counted as billable.
    Defaults to False (billable) if not set.
    """
    return context.get_state("non_billable") or False


@contextlib.asynccontextmanager
async def _acquire_pool_from_context(
    context: Context, readonly: bool = False
) -> AsyncIterator[asyncpg.Pool]:
    """Private context manager to acquire a database pool from context.

    Usage:
        async with _acquire_pool_from_context(context, readonly=True) as pool:
            # Use pool
    """
    tenant_id = _extract_tenant_id_from_context(context)
    if not tenant_id:
        raise RuntimeError(
            "tenant_id not found in tool context; ensure OrgContextMiddleware is enabled and token includes tenant_id or org_id claim"
        )
    async with _tenant_db_manager.acquire_pool(tenant_id, readonly=readonly) as pool:
        yield pool


@contextlib.asynccontextmanager
async def acquire_connection_from_context(
    context: Context, readonly: bool = False
) -> AsyncIterator[asyncpg.Connection]:
    """Context manager to acquire a database connection from context.

    Usage:
        async with acquire_connection_from_context(context, readonly=True) as conn:
            # Use connection for read-only operations

        async with acquire_connection_from_context(context) as conn:
            # Use connection for read-write operations
    """
    async with (
        _acquire_pool_from_context(context, readonly=readonly) as pool,
        pool.acquire() as conn,
    ):
        yield conn


@contextlib.asynccontextmanager
async def acquire_opensearch_from_context(
    context: Context,
) -> AsyncIterator[tuple[TenantScopedOpenSearchClient, str]]:
    """Context manager to lazily acquire tenant-scoped OpenSearch client from context.

    The returned client enforces tenant isolation - it will only allow operations
    on the tenant's index and will raise ValueError if code attempts to access
    a different index.

    Usage:
        async with acquire_opensearch_from_context(context) as (client, index):
            results = await client.keyword_search(index_name=index, query="...", ...)
            # Attempting to use a different index will raise ValueError

    Args:
        context: FastMCP context containing tenant_id

    Returns:
        Tuple of (TenantScopedOpenSearchClient, index_name)

    Raises:
        RuntimeError: If tenant_id is not found in context
    """
    tenant_id = _extract_tenant_id_from_context(context)
    if not tenant_id:
        raise RuntimeError(
            "tenant_id not found in tool context; ensure OrgContextMiddleware is enabled and token includes tenant_id claim"
        )

    async with _tenant_opensearch_manager.acquire_client(tenant_id) as (client, index_name):
        yield client, index_name


class OrgContextMiddleware(Middleware):
    def __init__(self):
        super().__init__()

    async def on_call_tool(
        self,
        middleware_context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        logger.info("OrgContextMiddleware - Starting tenant resolution")
        context = middleware_context.fastmcp_context
        if context is None:
            logger.info("OrgContextMiddleware - No FastMCP context, skipping")
            return await call_next(middleware_context)

        request = get_http_request()
        tenant_id = None
        non_billable = False

        # Check if this is API key authentication
        if is_api_key_authentication(request):
            tenant_id = extract_tenant_id_from_api_key(request)
            non_billable = is_api_key_non_billable(request)
        else:
            # Handle JWT-based authentication (existing logic)
            tenant_id, non_billable = await self._extract_tenant_id_and_flags_from_jwt()

        # Set tenant_id in context if found
        if tenant_id:
            context.set_state("tenant_id", tenant_id)
            logger.info(f"OrgContextMiddleware - Tenant resolution complete: {tenant_id}")
        else:
            logger.warning(
                "OrgContextMiddleware - No tenant_id found, continuing without tenant context"
            )

        # Set non_billable flag if present
        if non_billable:
            context.set_state("non_billable", True)
            logger.debug("OrgContextMiddleware - request marked as non-billable")

        logger.info("OrgContextMiddleware - Calling next middleware")
        return await call_next(middleware_context)

    async def _extract_tenant_id_and_flags_from_jwt(self) -> tuple[str | None, bool]:
        """Extract tenant_id and flags from JWT-based authentication (existing logic)."""
        claims = None
        non_billable = False

        try:
            logger.info("OrgContextMiddleware - Extracting JWT claims")
            user = get_http_request().user
            access_token_obj = user.access_token
            jwt_token = access_token_obj.token
            claims = _decode_jwt_payload(jwt_token)
            logger.info("OrgContextMiddleware - Successfully decoded JWT")
        except Exception as e:
            logger.warning(f"OrgContextMiddleware - Error getting claims: {e}")
            claims = None

        # Extract tenant_id and nonBillable from claims
        tenant_id = None
        try:
            # Get tenant_id directly from claims (from Slack bot or other internal services)
            tenant_id = claims.get("tenant_id") if isinstance(claims, dict) else None

            if tenant_id:
                logger.debug(f"OrgContextMiddleware - using tenant_id from claims: {tenant_id}")

            # Extract nonBillable flag from claims (defaults to False/billable if not present)
            non_billable = claims.get("nonBillable", False) if isinstance(claims, dict) else False
            if non_billable:
                logger.debug("OrgContextMiddleware - request marked as non-billable")
        except Exception as e:
            logger.warning(f"OrgContextMiddleware - Error extracting tenant: {e}")

        # If no tenant_id found, try to get org_id from WorkOS API and resolve to tenant_id
        if not tenant_id:
            try:
                logger.info(
                    "OrgContextMiddleware - No tenant_id in claims, trying WorkOS resolution"
                )
                # Get user's organization ID from WorkOS API and resolve to tenant_id
                user_id = claims.get("sub") if claims else None
                if user_id:
                    logger.info(f"OrgContextMiddleware - Calling WorkOS API for user {user_id}")
                    org_id = await _get_user_organization_from_workos(user_id)
                    logger.info(f"OrgContextMiddleware - WorkOS API returned org_id: {org_id}")
                    if org_id:
                        logger.info("OrgContextMiddleware - Acquiring control DB pool")
                        control_pool = await _tenant_db_manager.get_control_db()
                        logger.info("OrgContextMiddleware - Resolving org_id to tenant_id in DB")
                        resolved_tenant_id = await _resolve_workos_org_to_tenant_id(
                            control_pool, org_id
                        )
                        logger.info(
                            f"OrgContextMiddleware - DB lookup returned tenant_id: {resolved_tenant_id}"
                        )
                    else:
                        resolved_tenant_id = None
                else:
                    logger.info("OrgContextMiddleware - No user_id in claims")
                    resolved_tenant_id = None
                if resolved_tenant_id:
                    tenant_id = resolved_tenant_id
                    logger.debug(
                        f"OrgContextMiddleware - resolved user {user_id} to tenant_id: {tenant_id}"
                    )
            except Exception as e:
                logger.warning(f"OrgContextMiddleware - Error resolving user to tenant_id: {e}")

        return tenant_id, non_billable
