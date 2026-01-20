"""Shared authentication helper utilities for MCP middleware."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request


def is_api_key_authentication(request: Request) -> bool:
    """Check if the request is authenticated via API key.

    Checks both client_id prefix (current) and scopes (future-proofing for
    granular permissions like api-key:read, api-key:write, etc.).

    Args:
        request: The HTTP request to check

    Returns:
        True if authenticated via API key, False otherwise
    """
    try:
        user = getattr(request, "user", None)
        if user and hasattr(user, "access_token"):
            access_token = user.access_token
            # Check client_id format (primary check)
            if hasattr(access_token, "client_id") and access_token.client_id.startswith("api-key:"):
                return True
            # Check scopes (future: could have api-key:read, api-key:write, etc.)
            if hasattr(access_token, "scopes") and "api-key" in access_token.scopes:
                return True
    except Exception:
        pass
    return False


def extract_tenant_id_from_api_key(request: Request) -> str | None:
    """Extract tenant_id from API key authentication.

    Args:
        request: The HTTP request containing API key authentication

    Returns:
        The tenant_id if found, None otherwise
    """
    try:
        user = getattr(request, "user", None)
        if user and hasattr(user, "access_token"):
            access_token = user.access_token
            if hasattr(access_token, "client_id") and access_token.client_id.startswith("api-key:"):
                # Extract tenant_id from client_id format: "api-key:{tenant_id}"
                return access_token.client_id.split(":", 1)[1]
    except Exception:
        pass
    return None


def has_api_key_scope(request: Request, scope: str) -> bool:
    """Check if API key has a specific scope (for future use).

    Args:
        request: The HTTP request containing API key authentication
        scope: The scope to check for

    Returns:
        True if the API key has the specified scope, False otherwise
    """
    try:
        user = getattr(request, "user", None)
        if user and hasattr(user, "access_token"):
            access_token = user.access_token
            if hasattr(access_token, "scopes"):
                return scope in access_token.scopes
    except Exception:
        pass
    return False


def is_api_key_non_billable(request: Request) -> bool:
    """Check if the API key is marked as non-billable.

    Args:
        request: The HTTP request containing API key authentication

    Returns:
        True if the API key has the "non-billable" scope, False otherwise
    """
    return has_api_key_scope(request, "non-billable")
