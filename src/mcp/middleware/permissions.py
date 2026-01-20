"""Middleware to extract principal email and generate permission tokens for document access control."""

from __future__ import annotations

import contextlib
from typing import Any

import httpx
import jwt
from fastmcp.server.context import Context
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.middleware import CallNext

from src.mcp.utils.auth_helpers import is_api_key_authentication
from src.permissions.utils import make_email_permission_token
from src.utils.config import get_config_value
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PermissionsMiddleware(Middleware):
    def __init__(self):
        super().__init__()

    async def on_call_tool(
        self,
        middleware_context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        logger.info("PermissionsMiddleware - Starting permissions setup")
        context = middleware_context.fastmcp_context
        if context is None:
            logger.info("PermissionsMiddleware - No FastMCP context, skipping")
            return await call_next(middleware_context)

        # Try to get HTTP request - may not be available in all contexts
        request = None
        # No HTTP request available (e.g., in unit tests)
        with contextlib.suppress(RuntimeError):
            request = get_http_request()

        # Check if this is API key authentication
        if request and is_api_key_authentication(request):
            logger.info(
                "PermissionsMiddleware - API key authentication detected, skipping user-specific permissions"
            )
            # For API keys, set tenant-scoped permissions (audience = "tenant")
            context.set_state("permission_audience", "tenant")
            context.set_state("permission_principal_token", None)  # No user-specific token
        else:
            # Handle JWT-based authentication (existing logic)
            logger.info("PermissionsMiddleware - Getting principal email")
            principal_email = await self._get_principal_email(context)
            logger.info(f"PermissionsMiddleware - Principal email: {principal_email}")

            if principal_email:
                try:
                    permission_principal_token = make_email_permission_token(principal_email)
                    context.set_state("permission_principal_token", permission_principal_token)
                    logger.debug(
                        f"PermissionsMiddleware - created principal permission token for: {principal_email}"
                    )
                except Exception as e:
                    logger.warning(f"PermissionsMiddleware - Error creating permission token: {e}")
            else:
                logger.debug("PermissionsMiddleware - No principal email found")

            logger.info("PermissionsMiddleware - Extracting JWT audience")
            permission_audience = self._extract_jwt_audience()
            context.set_state("permission_audience", permission_audience)
            logger.info(f"PermissionsMiddleware - Permission audience: {permission_audience}")

        logger.info("PermissionsMiddleware - Calling next middleware")
        return await call_next(middleware_context)

    async def _get_principal_email(self, context: Context) -> str | None:
        email = await self._extract_jwt_email()
        if email:
            return email

        logger.debug("PermissionsMiddleware - No email found from any authentication source")
        return None

    async def _extract_jwt_email(self) -> str | None:
        claims = self._extract_jwt_claims()
        if not claims:
            return None

        email = self._extract_slackbot_email(claims)
        if email:
            return email

        return await self._fetch_workos_email(claims)

    def _extract_jwt_audience(self) -> str | None:
        """Extract audience from JWT claims."""
        claims = self._extract_jwt_claims()
        if not claims:
            return None
        return claims.get("permission_audience")

    def _extract_jwt_claims(self) -> dict | None:
        try:
            user = get_http_request().user
            access_token_obj = user.access_token
            jwt_token = access_token_obj.token
            return jwt.decode(jwt_token, options={"verify_signature": False})
        except Exception as e:
            logger.warning(f"PermissionsMiddleware - Error getting JWT claims: {e}")
            return None

    def _extract_slackbot_email(self, claims: dict) -> str | None:
        email_from_jwt = claims.get("email")
        if email_from_jwt:
            return email_from_jwt
        return None

    async def _fetch_workos_email(self, claims: dict) -> str | None:
        user_id = claims.get("sub")
        if not user_id:
            return None

        try:
            workos_api_key = get_config_value("WORKOS_API_KEY")
            if not workos_api_key:
                logger.warning(
                    "PermissionsMiddleware - WORKOS_API_KEY not configured for email lookup"
                )
                return None

            logger.info(f"PermissionsMiddleware - Calling WorkOS API for user email {user_id}")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.workos.com/user_management/users/{user_id}",
                    headers={
                        "Authorization": f"Bearer {workos_api_key}",
                        "Accept": "application/json",
                    },
                )
                logger.info(
                    f"PermissionsMiddleware - WorkOS user API response: {response.status_code}"
                )

                if response.status_code == 200:
                    data = response.json()
                    email = data.get("email")
                    if email:
                        return email
                    else:
                        logger.debug("PermissionsMiddleware - User has no email in WorkOS")
                        return None
                else:
                    logger.warning(
                        f"PermissionsMiddleware - WorkOS user API error: {response.status_code} {response.text}"
                    )
                    return None

        except Exception as e:
            logger.warning(f"PermissionsMiddleware - Error calling WorkOS user API: {e}")
            return None
