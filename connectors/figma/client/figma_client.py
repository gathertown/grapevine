"""
Figma REST API client with rate limiting support.

Figma uses a tiered rate limiting system:
- Tier 1: Heavy operations (file content) - 10-20 req/min
- Tier 2: Moderate operations (comments, versions, projects) - 25-100 req/min
- Tier 3: Light operations (metadata) - 50-150 req/min

The client implements exponential backoff and respects the Retry-After header on 429 responses.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import BaseModel, Field

from src.jobs.exceptions import ExtendVisibilityException
from src.utils.logging import get_logger

logger = get_logger(__name__)

FIGMA_API_BASE = "https://api.figma.com"


# Pydantic models for Figma API responses
class FigmaUser(BaseModel):
    """Figma user information."""

    id: str
    handle: str
    img_url: str
    email: str | None = None


class FigmaProject(BaseModel):
    """Figma project information."""

    id: str
    name: str


class FigmaFileMetadata(BaseModel):
    """Figma file metadata from the files endpoint."""

    key: str
    name: str
    thumbnail_url: str | None = None
    last_modified: str


class FigmaFile(BaseModel):
    """Figma file with full document structure."""

    name: str
    role: str
    last_modified: str = Field(alias="lastModified")
    editor_type: str = Field(alias="editorType")
    thumbnail_url: str | None = Field(default=None, alias="thumbnailUrl")
    version: str
    document: dict[str, Any]
    components: dict[str, Any] = Field(default_factory=dict)
    component_sets: dict[str, Any] = Field(default_factory=dict, alias="componentSets")
    styles: dict[str, Any] = Field(default_factory=dict)

    class Config:
        populate_by_name = True


class FigmaComment(BaseModel):
    """Figma comment on a file."""

    id: str
    file_key: str
    parent_id: str | None = None
    user: FigmaUser
    created_at: str
    resolved_at: str | None = None
    message: str
    client_meta: dict[str, Any] | None = None
    order_id: str | None = None


class FigmaVersion(BaseModel):
    """Figma file version."""

    id: str
    created_at: str
    label: str | None = None
    description: str | None = None
    user: FigmaUser


class FigmaTeam(BaseModel):
    """Figma team information."""

    id: str
    name: str


@dataclass
class FigmaRateLimitInfo:
    """Rate limit information from Figma response headers."""

    retry_after: int | None = None
    plan_tier: str | None = None
    rate_limit_type: str | None = None


class FigmaAPIError(Exception):
    """Exception raised for Figma API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        rate_limit_info: FigmaRateLimitInfo | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limit_info = rate_limit_info


class FigmaClient:
    """
    Figma REST API client.

    Handles authentication, rate limiting, and retry logic for Figma API requests.
    Figma access tokens are long-lived (90 days), so we don't need to refresh on every request.
    """

    def __init__(self, access_token: str, timeout: float = 30.0, max_retries: int = 3):
        """
        Initialize the Figma client.

        Args:
            access_token: OAuth access token for Figma API
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
                base_url=FIGMA_API_BASE,
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

    async def __aenter__(self) -> FigmaClient:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self, exc_type: type | None, exc_val: Exception | None, exc_tb: object
    ) -> None:
        """Async context manager exit - ensures client is closed."""
        await self.close()

    def _extract_rate_limit_info(self, response: httpx.Response) -> FigmaRateLimitInfo:
        """Extract rate limit information from response headers."""
        retry_after_str = response.headers.get("Retry-After")
        return FigmaRateLimitInfo(
            retry_after=int(retry_after_str) if retry_after_str else None,
            plan_tier=response.headers.get("X-Figma-Plan-Tier"),
            rate_limit_type=response.headers.get("X-Figma-Rate-Limit-Type"),
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
            FigmaAPIError: For API errors
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
                        "Figma rate limit hit",
                        retry_after=retry_after,
                        plan_tier=rate_limit_info.plan_tier,
                        rate_limit_type=rate_limit_info.rate_limit_type,
                        attempt=attempt,
                    )

                    # If retry_after is long, raise ExtendVisibilityException to extend SQS visibility
                    if retry_after > 60:
                        raise ExtendVisibilityException(
                            visibility_timeout_seconds=retry_after + 30,
                            message=f"Figma rate limited, need to wait {retry_after} seconds",
                        )

                    if attempt < self.max_retries:
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        raise FigmaAPIError(
                            f"Rate limit exceeded after {self.max_retries} retries",
                            status_code=429,
                            rate_limit_info=rate_limit_info,
                        )

                if response.status_code == 401:
                    raise FigmaAPIError(
                        "Unauthorized - access token may be invalid or expired", 401
                    )

                if response.status_code == 403:
                    raise FigmaAPIError("Forbidden - insufficient permissions", 403)

                if response.status_code == 404:
                    raise FigmaAPIError("Not found", 404)

                if response.status_code >= 400:
                    raise FigmaAPIError(
                        f"Figma API error: {response.status_code} - {response.text}",
                        response.status_code,
                    )

                return response.json()

            except httpx.TimeoutException as e:
                logger.error("Figma API timeout", endpoint=endpoint, attempt=attempt, error=str(e))
                if attempt < self.max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise FigmaAPIError(f"Request timeout after {self.max_retries} retries")

            except httpx.RequestError as e:
                logger.error("Figma API request error", endpoint=endpoint, error=str(e))
                raise FigmaAPIError(f"Request failed: {e}")

        raise FigmaAPIError("Max retries exceeded")

    # User endpoints
    async def get_current_user(self) -> FigmaUser:
        """Get the current authenticated user's information."""
        data = await self._request("GET", "/v1/me")
        return FigmaUser(**data)

    # Team endpoints
    async def get_team_projects(self, team_id: str) -> list[FigmaProject]:
        """
        Get all projects in a team.

        Note: This endpoint is only available for private OAuth apps.

        Args:
            team_id: The team ID

        Returns:
            List of projects in the team
        """
        data = await self._request("GET", f"/v1/teams/{team_id}/projects")
        return [FigmaProject(**p) for p in data.get("projects", [])]

    # Project endpoints
    async def get_project_files(self, project_id: str) -> list[FigmaFileMetadata]:
        """
        Get all files in a project.

        Args:
            project_id: The project ID

        Returns:
            List of file metadata
        """
        data = await self._request("GET", f"/v1/projects/{project_id}/files")
        return [FigmaFileMetadata(**f) for f in data.get("files", [])]

    # File endpoints
    async def get_file(
        self,
        file_key: str,
        version: str | None = None,
        depth: int | None = None,
        geometry: str | None = None,
    ) -> FigmaFile:
        """
        Get a file's document structure.

        Args:
            file_key: The file key (from URL)
            version: Specific version ID to retrieve
            depth: Depth of document tree to return
            geometry: Include geometry data ("paths" or "bounds")

        Returns:
            File document structure
        """
        params: dict[str, Any] = {}
        if version:
            params["version"] = version
        if depth is not None:
            params["depth"] = depth
        if geometry:
            params["geometry"] = geometry

        data = await self._request("GET", f"/v1/files/{file_key}", params=params or None)
        return FigmaFile(**data)

    async def get_file_meta(self, file_key: str) -> dict[str, Any]:
        """
        Get file metadata only (faster than full file fetch).

        This is a Tier 3 endpoint with higher rate limits.

        Args:
            file_key: The file key

        Returns:
            File metadata
        """
        data = await self._request("GET", f"/v1/files/{file_key}/meta")
        return data

    async def get_file_versions(self, file_key: str) -> list[FigmaVersion]:
        """
        Get version history for a file.

        Args:
            file_key: The file key

        Returns:
            List of versions
        """
        data = await self._request("GET", f"/v1/files/{file_key}/versions")
        return [FigmaVersion(**v) for v in data.get("versions", [])]

    # Comment endpoints
    async def get_file_comments(self, file_key: str) -> list[FigmaComment]:
        """
        Get all comments on a file.

        Note: Comments are not paginated - all are returned at once.

        Args:
            file_key: The file key

        Returns:
            List of comments with replies
        """
        data = await self._request("GET", f"/v1/files/{file_key}/comments")
        comments = data.get("comments", [])
        # Add file_key to each comment
        for comment in comments:
            comment["file_key"] = file_key
        return [FigmaComment(**c) for c in comments]

    # Iteration helpers
    async def iter_team_files(self, team_id: str) -> list[tuple[FigmaProject, FigmaFileMetadata]]:
        """
        Iterate through all files in all projects of a team.

        Args:
            team_id: The team ID

        Yields:
            Tuples of (project, file_metadata)
        """
        results: list[tuple[FigmaProject, FigmaFileMetadata]] = []
        projects = await self.get_team_projects(team_id)

        for project in projects:
            files = await self.get_project_files(project.id)
            for file in files:
                results.append((project, file))

        return results


async def get_figma_client_for_tenant(tenant_id: str) -> FigmaClient:
    """
    Create a FigmaClient for a specific tenant.

    Figma access tokens are long-lived (90 days), so we don't need to refresh on every request.
    However, if approaching expiration, we should refresh proactively.

    Args:
        tenant_id: The tenant ID

    Returns:
        Configured FigmaClient instance
    """
    from src.clients.ssm import SSMClient

    ssm_client = SSMClient()

    # Figma tokens are stored in SSM
    access_token = await ssm_client.get_api_key(tenant_id, "FIGMA_ACCESS_TOKEN")

    if not access_token:
        raise ValueError(f"No Figma access token found for tenant {tenant_id}")

    return FigmaClient(access_token=access_token)
