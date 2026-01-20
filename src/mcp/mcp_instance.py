"""Shared MCP instance module to avoid circular imports."""

from fastmcp import FastMCP
from fastmcp.server.auth.auth import AuthProvider
from fastmcp.server.auth.providers.jwt import JWTVerifier
from fastmcp.server.auth.providers.workos import AuthKitProvider

from src.mcp.auth import APIKeyAuthProvider
from src.mcp.auth.multi_provider import MultiAuthProvider
from src.utils.config import (
    get_authkit_domain,
    get_internal_jwt_audience,
    get_internal_jwt_issuer,
    get_internal_jwt_jwks_uri,
    get_internal_jwt_public_key,
    get_mcp_base_url,
)
from src.utils.logging import get_logger

_mcp_instance: FastMCP | None = None
logger = get_logger(__name__)


def _build_auth_provider():
    # Configure AuthKit (WorkOS) provider for public metadata and human auth
    authkit_domain = get_authkit_domain()
    base_url = get_mcp_base_url()

    providers: list[AuthProvider] = []

    workos_provider = None
    if authkit_domain:
        workos_provider = AuthKitProvider(
            authkit_domain=authkit_domain,
            base_url=base_url,
        )
        providers.append(workos_provider)

    # API key provider for programmatic access
    providers.append(APIKeyAuthProvider())

    # Optional internal JWT verifier for agent/slackbot
    internal_jwks = get_internal_jwt_jwks_uri()
    internal_pub = get_internal_jwt_public_key()
    internal_issuer = get_internal_jwt_issuer()
    internal_audience = get_internal_jwt_audience()

    internal_verifier = None
    if internal_jwks or internal_pub:
        internal_verifier = JWTVerifier(
            jwks_uri=internal_jwks if internal_jwks else None,
            public_key=internal_pub if internal_pub else None,
            issuer=internal_issuer if internal_issuer else None,
            audience=internal_audience if internal_audience else None,
            # Keep resource_server_url/scopes default; WorkOS handles .well-known
        )
        providers.append(internal_verifier)

    # If both are present, combine: expose WorkOS routes, accept either token
    if len(providers) > 1 and workos_provider:
        return MultiAuthProvider(
            primary_routes_provider=workos_provider,
            verifiers=providers,
        )
    elif len(providers) > 1:
        return MultiAuthProvider(
            primary_routes_provider=providers[0],
            verifiers=providers,
        )

    # If only one is configured, return it
    return providers[0] if providers else None


def get_mcp() -> FastMCP:
    global _mcp_instance
    if _mcp_instance is None:
        auth = _build_auth_provider()
        _mcp_instance = FastMCP("corporate-context", stateless_http=True, auth=auth)

    return _mcp_instance
