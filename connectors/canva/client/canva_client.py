"""
Canva Connect API client with rate limiting support.

Canva uses per-endpoint rate limits:
- List designs: 100 req/min/user
- Get design: 100 req/min/user
- List folder items: 100 req/min/user

The client implements exponential backoff and respects the Retry-After header on 429 responses.

Canva OAuth tokens:
- Access tokens expire in ~4 hours (14400 seconds)
- Refresh tokens can only be used once
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field

from src.jobs.exceptions import ExtendVisibilityException
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)

CANVA_API_BASE = "https://api.canva.com/rest/v1"
CANVA_OAUTH_TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"


# Pydantic models for Canva API responses
class CanvaUser(BaseModel):
    """Canva user information from /users/me endpoint."""

    id: str
    display_name: str | None = Field(default=None, alias="display_name")


class CanvaOwner(BaseModel):
    """Design owner information."""

    user_id: str | None = None
    team_id: str | None = None


class CanvaDesignUrls(BaseModel):
    """URLs for accessing a design."""

    edit_url: str | None = None
    view_url: str | None = None


class CanvaThumbnail(BaseModel):
    """Thumbnail image for a design."""

    width: int | None = None
    height: int | None = None
    url: str | None = None


class CanvaDesign(BaseModel):
    """Canva design metadata from list/get endpoints."""

    id: str
    title: str | None = None
    owner: CanvaOwner | None = None
    urls: CanvaDesignUrls | None = None
    created_at: int | None = None  # Unix timestamp
    updated_at: int | None = None  # Unix timestamp
    thumbnail: CanvaThumbnail | None = None
    page_count: int | None = None


class CanvaFolderItem(BaseModel):
    """Item in a folder (can be design, folder, or image)."""

    type: str  # "design", "folder", or "image"
    design: CanvaDesign | None = None
    folder: dict[str, Any] | None = None
    image: dict[str, Any] | None = None


@dataclass
class CanvaRateLimitInfo:
    """Rate limit information from Canva response headers."""

    retry_after: int | None = None


class CanvaAPIError(Exception):
    """Exception raised for Canva API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        rate_limit_info: CanvaRateLimitInfo | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limit_info = rate_limit_info


class CanvaClient:
    """
    Canva Connect API client.

    Handles authentication, rate limiting, and retry logic for Canva API requests.
    Canva access tokens expire after ~4 hours, so we need to refresh on every client creation.
    """

    def __init__(self, access_token: str, timeout: float = 30.0, max_retries: int = 3):
        """
        Initialize the Canva client.

        Args:
            access_token: OAuth access token for Canva API
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts for rate-limited requests
        """
        self.access_token = access_token
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=CANVA_API_BASE,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> CanvaClient:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self, _exc_type: type | None, _exc_val: Exception | None, _exc_tb: object
    ) -> None:
        """Async context manager exit - ensures client is closed."""
        await self.close()

    def _extract_rate_limit_info(self, response: httpx.Response) -> CanvaRateLimitInfo:
        """Extract rate limit information from response headers."""
        retry_after_str = response.headers.get("Retry-After")
        return CanvaRateLimitInfo(
            retry_after=int(retry_after_str) if retry_after_str else None,
        )

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make an HTTP request with retry logic for rate limits.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON body data

        Returns:
            Parsed JSON response

        Raises:
            CanvaAPIError: For API errors
            ExtendVisibilityException: For rate limits that require longer waits
        """
        client = await self._get_client()

        for attempt in range(self.max_retries + 1):
            try:
                response = await client.request(
                    method=method,
                    url=endpoint,
                    params=params,
                    json=json_data,
                )

                if response.status_code == 429:
                    rate_limit_info = self._extract_rate_limit_info(response)
                    retry_after = rate_limit_info.retry_after or 60

                    logger.warning(
                        "Canva rate limit hit",
                        retry_after=retry_after,
                        attempt=attempt,
                    )

                    # If retry_after is long, raise ExtendVisibilityException to extend SQS visibility
                    if retry_after > 60:
                        raise ExtendVisibilityException(
                            visibility_timeout_seconds=retry_after + 30,
                            message=f"Canva rate limited, need to wait {retry_after} seconds",
                        )

                    if attempt < self.max_retries:
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        raise CanvaAPIError(
                            f"Rate limit exceeded after {self.max_retries} retries",
                            status_code=429,
                            rate_limit_info=rate_limit_info,
                        )

                if response.status_code == 401:
                    raise CanvaAPIError(
                        "Unauthorized - access token may be invalid or expired", 401
                    )

                if response.status_code == 403:
                    raise CanvaAPIError("Forbidden - insufficient permissions", 403)

                if response.status_code == 404:
                    raise CanvaAPIError("Not found", 404)

                if response.status_code >= 400:
                    raise CanvaAPIError(
                        f"Canva API error: {response.status_code} - {response.text}",
                        response.status_code,
                    )

                return response.json()

            except httpx.TimeoutException as e:
                logger.error("Canva API timeout", endpoint=endpoint, attempt=attempt, error=str(e))
                if attempt < self.max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise CanvaAPIError(f"Request timeout after {self.max_retries} retries")

            except httpx.RequestError as e:
                logger.error("Canva API request error", endpoint=endpoint, error=str(e))
                raise CanvaAPIError(f"Request failed: {e}")

        raise CanvaAPIError("Max retries exceeded")

    # User endpoints
    async def get_current_user(self) -> CanvaUser:
        """Get the current authenticated user's information."""
        data = await self._request("GET", "/users/me")
        return CanvaUser(**data)

    # Design endpoints
    async def list_designs(
        self,
        query: str | None = None,
        continuation: str | None = None,
        ownership: str | None = None,
        sort_by: str | None = "modified_descending",
        limit: int = 100,
    ) -> tuple[list[CanvaDesign], str | None]:
        """
        List user's designs.

        Args:
            query: Search term (max 255 chars)
            continuation: Pagination token
            ownership: Filter by "owned", "shared", or "any"
            sort_by: Sort order (relevance, modified_descending, etc.)
            limit: Number of results (1-100)

        Returns:
            Tuple of (designs list, continuation token or None)
        """
        params: dict[str, Any] = {"limit": min(limit, 100)}
        if query:
            params["query"] = query[:255]
        if continuation:
            params["continuation"] = continuation
        if ownership:
            params["ownership"] = ownership
        if sort_by:
            params["sort_by"] = sort_by

        data = await self._request("GET", "/designs", params=params)
        designs = [CanvaDesign(**d) for d in data.get("items", [])]
        next_continuation = data.get("continuation")

        return designs, next_continuation

    async def get_design(self, design_id: str) -> CanvaDesign:
        """
        Get a specific design's metadata.

        Args:
            design_id: The design ID

        Returns:
            Design metadata
        """
        data = await self._request("GET", f"/designs/{design_id}")
        # The API returns the design object directly, not nested
        return CanvaDesign(**data.get("design", data))

    # Folder endpoints
    async def list_folder_items(
        self,
        folder_id: str = "root",
        continuation: str | None = None,
        item_types: list[str] | None = None,
        sort_by: str | None = "modified_descending",
    ) -> tuple[list[CanvaFolderItem], str | None]:
        """
        List items in a folder.

        Args:
            folder_id: Folder ID or "root" for root folder
            continuation: Pagination token
            item_types: Filter by type (design, folder, image)
            sort_by: Sort order

        Returns:
            Tuple of (items list, continuation token or None)
        """
        params: dict[str, Any] = {}
        if continuation:
            params["continuation"] = continuation
        if item_types:
            params["item_types"] = ",".join(item_types)
        if sort_by:
            params["sort_by"] = sort_by

        data = await self._request("GET", f"/folders/{folder_id}/items", params=params)
        items = [CanvaFolderItem(**item) for item in data.get("items", [])]
        next_continuation = data.get("continuation")

        return items, next_continuation

    # Iterator helpers
    async def iter_all_designs(
        self,
        ownership: str = "any",
        sort_by: str = "modified_descending",
    ) -> AsyncIterator[CanvaDesign]:
        """
        Iterate through all user's designs with automatic pagination.

        Args:
            ownership: Filter by ownership
            sort_by: Sort order

        Yields:
            CanvaDesign objects
        """
        continuation = None
        while True:
            designs, continuation = await self.list_designs(
                continuation=continuation,
                ownership=ownership,
                sort_by=sort_by,
                limit=100,
            )

            for design in designs:
                yield design

            if not continuation:
                break


@rate_limited()
async def _refresh_canva_token(
    tenant_id: str,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> tuple[str, str]:
    """
    Refresh Canva access token using refresh token.

    Canva access tokens expire in ~4 hours, so we need to refresh on every client creation.
    Refresh tokens can only be used once, so we must update both tokens.

    Args:
        tenant_id: Tenant ID for logging
        refresh_token: Current refresh token
        client_id: Canva app client ID
        client_secret: Canva app client secret

    Returns:
        Tuple of (new_access_token, new_refresh_token)

    Raises:
        ValueError: For auth failures (400, 401, 403)
        RateLimitedError: For transient network errors
    """
    import base64

    # Build Basic auth header
    credentials = f"{client_id}:{client_secret}"
    basic_auth = base64.b64encode(credentials.encode()).decode()

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                CANVA_OAUTH_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {basic_auth}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )

            if response.status_code in (400, 401, 403):
                error_text = response.text
                logger.error(
                    "Canva token refresh auth failure",
                    status=response.status_code,
                    error=error_text,
                    tenant_id=tenant_id,
                )
                raise ValueError(f"Canva auth failure: {response.status_code} - {error_text}")

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                raise RateLimitedError(
                    retry_after=max(retry_after, 30),
                    message=f"Canva token refresh rate limited, retry after {retry_after}s",
                )

            if not response.is_success:
                error_text = response.text
                logger.error(
                    "Canva token refresh failed",
                    status=response.status_code,
                    error=error_text,
                    tenant_id=tenant_id,
                )
                # Treat other failures as transient
                raise RateLimitedError(
                    retry_after=30,
                    message=f"Canva token refresh failed: {response.status_code}",
                )

            data = response.json()
            return data["access_token"], data["refresh_token"]

    except httpx.ReadTimeout as e:
        logger.warning("Canva token refresh timeout", tenant_id=tenant_id, error=str(e))
        raise RateLimitedError(retry_after=30, message="Canva token refresh timeout")
    except httpx.ConnectError as e:
        logger.warning("Canva token refresh connection error", tenant_id=tenant_id, error=str(e))
        raise RateLimitedError(retry_after=30, message="Canva token refresh connection error")


async def get_canva_client_for_tenant(tenant_id: str) -> CanvaClient:
    """
    Create a CanvaClient for a specific tenant.

    Canva access tokens expire in ~4 hours, so we refresh on every client creation.
    This ensures we always have a valid token.

    Args:
        tenant_id: The tenant ID

    Returns:
        Configured CanvaClient instance

    Raises:
        ValueError: If no credentials found or refresh fails
    """
    from src.clients.ssm import SSMClient

    ssm_client = SSMClient()

    # Get current tokens from SSM
    refresh_token = await ssm_client.get_api_key(tenant_id, "CANVA_REFRESH_TOKEN")
    if not refresh_token:
        raise ValueError(f"No Canva refresh token found for tenant {tenant_id}")

    # Get client credentials from environment
    client_id = os.environ.get("CANVA_CLIENT_ID")
    client_secret = os.environ.get("CANVA_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError("CANVA_CLIENT_ID and CANVA_CLIENT_SECRET environment variables required")

    # Refresh the token to get a fresh access token
    new_access_token, new_refresh_token = await _refresh_canva_token(
        tenant_id=tenant_id,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )

    # Update tokens in storage
    await ssm_client.store_api_key(tenant_id, "CANVA_ACCESS_TOKEN", new_access_token)
    await ssm_client.store_api_key(tenant_id, "CANVA_REFRESH_TOKEN", new_refresh_token)

    logger.info("Refreshed Canva tokens for tenant", tenant_id=tenant_id)

    return CanvaClient(access_token=new_access_token)
