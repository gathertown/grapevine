"""HTTP client authentication utilities for httpx."""

import httpx


class BearerAuth(httpx.Auth):
    """Bearer token authentication for httpx client requests.

    Example:
        >>> auth = BearerAuth("my-token-123")
        >>> async with httpx.AsyncClient(auth=auth) as client:
    """

    def __init__(self, token: str):
        self.token = token

    def auth_flow(self, request: httpx.Request):
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request
