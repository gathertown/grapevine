from __future__ import annotations

from collections.abc import Iterable, Sequence

from fastmcp.server.auth.auth import AuthProvider


class MultiAuthProvider(AuthProvider):
    """Composite auth provider that tries multiple underlying providers for token verification.

    - Token verification succeeds if any provider returns a valid AccessToken
    - Public routes (e.g., .well-known) are delegated to the primary provider only
    """

    def __init__(
        self,
        primary_routes_provider: AuthProvider | None,
        verifiers: Sequence[AuthProvider] | Iterable[AuthProvider],
    ):
        # We don't set base_url here; individual providers may have it
        super().__init__()
        self.primary_routes_provider = primary_routes_provider
        # Normalize verifiers to a list
        self.verifiers: list[AuthProvider] = list(verifiers)

    async def verify_token(self, token: str):  # returns AccessToken | None
        # Try each verifier in order; first success wins
        for verifier in self.verifiers:
            try:
                access = await verifier.verify_token(token)
                if access is not None:
                    return access
            except Exception:
                # Ignore and try next provider
                continue
        return None

    def get_routes(self, mcp_path: str | None = None):  # returns list[Route]
        if self.primary_routes_provider is None:
            return []
        return self.primary_routes_provider.get_routes(mcp_path)
