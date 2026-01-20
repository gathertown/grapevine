"""API Key authentication provider for FastMCP."""

from __future__ import annotations

from fastmcp.server.auth.auth import AccessToken, AuthProvider

from src.mcp.utils.api_keys import API_KEY_NON_BILLABLE_TENANT_IDS, verify_api_key


class APIKeyAuthProvider(AuthProvider):
    """Auth provider that validates API keys."""

    def __init__(self) -> None:
        super().__init__()

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify an API key token and return an AccessToken if valid.

        Args:
            token: The API key token to verify

        Returns:
            AccessToken if the API key is valid, None otherwise
        """
        try:
            tenant_id = await verify_api_key(token)
            if tenant_id:
                # Check if tenant is whitelisted for non-billable API key usage
                scopes = ["api-key"]
                if tenant_id in API_KEY_NON_BILLABLE_TENANT_IDS:
                    scopes.append("non-billable")

                return AccessToken(
                    token=token,
                    client_id=f"api-key:{tenant_id}",
                    scopes=scopes,
                    expires_at=None,  # API keys don't expire
                )
        except Exception:
            # Log and return None for any verification errors
            pass
        return None
