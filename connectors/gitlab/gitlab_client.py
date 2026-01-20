"""GitLab REST API client for MR and file ingestion.

Note: This client currently only supports gitlab.com. Self-hosted GitLab
instances are not supported in this version.
"""

import logging
from dataclasses import dataclass
from functools import cache
from typing import Any
from urllib.parse import quote_plus

import httpx
from aiolimiter import AsyncLimiter

from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = logging.getLogger(__name__)

# GitLab.com API base URL (self-hosted instances not supported)
GITLAB_API_URL = "https://gitlab.com/api/v4"

# API pagination
DEFAULT_PER_PAGE = 100
MAX_PER_PAGE = 100

# Default retry after seconds when not provided by server
DEFAULT_RETRY_AFTER_SECONDS = 10

# Retry after seconds for timeouts - set >30s to trigger SQS visibility extension
# (see src/utils/rate_limiter.py - ExtendVisibilityException threshold is 30s)
TIMEOUT_RETRY_AFTER_SECONDS = 35

# HTTP client timeout in seconds - lower than default to avoid long-running retries
CLIENT_TIMEOUT_SECONDS = 30.0

# Rate limiting: GitLab has ~300-2000 req/min depending on tier
# Use conservative 5 req/sec (300/min) to avoid bursts and 429s
REQUESTS_PER_SECOND = 5.0


@dataclass
class GitLabLimiters:
    """Per-tenant rate limiters for GitLab API."""

    tenant_id: str
    general: AsyncLimiter


@cache
def _get_limiters(tenant_id: str) -> GitLabLimiters:
    """Get or create rate limiters for a tenant (cached per tenant_id)."""
    return GitLabLimiters(
        tenant_id=tenant_id,
        # 5 req/sec, no bursting (1 token, refill every 0.2 seconds)
        general=AsyncLimiter(1, 1 / REQUESTS_PER_SECOND),
    )


def _parse_retry_after(header_value: str | None) -> int:
    """Safely parse the Retry-After header value.

    Per RFC 7231, Retry-After can be either:
    - An integer (delay in seconds)
    - An HTTP-date format (e.g., "Wed, 21 Oct 2015 07:28:00 GMT")

    This function handles both cases and falls back to the default on parse errors.

    Args:
        header_value: The Retry-After header value, or None if not present

    Returns:
        Number of seconds to wait before retrying
    """
    if not header_value:
        return DEFAULT_RETRY_AFTER_SECONDS

    try:
        return int(header_value)
    except ValueError:
        # Could be HTTP-date format or other unexpected value
        # Fall back to default rather than trying to parse dates
        logger.debug(f"Could not parse Retry-After header '{header_value}', using default")
        return DEFAULT_RETRY_AFTER_SECONDS


def _get_safe_endpoint_tag(endpoint: str) -> str:
    """Extract a safe, redacted endpoint tag for logging.

    Removes customer-sensitive data like project IDs, file paths, and commit SHAs.
    Only logs the general endpoint pattern without specific identifiers.

    Examples:
        /projects/123/merge_requests/45 -> /projects/.../merge_requests
        /projects/foo%2Fbar/repository/files/secret.txt -> /projects/.../repository/files
        /user -> /user

    Args:
        endpoint: The API endpoint path

    Returns:
        A redacted endpoint tag safe for logging
    """
    # Split by "/" and redact dynamic segments
    parts = endpoint.strip("/").split("/")
    safe_parts = []

    i = 0
    while i < len(parts):
        part = parts[i]

        # Known resource types that are followed by an ID
        if part in ("projects", "groups", "users", "merge_requests", "commits", "files"):
            safe_parts.append(part)
            # Skip the next part (the ID/path)
            if i + 1 < len(parts):
                safe_parts.append("...")
                i += 1
        elif part.isdigit() or "%" in part:
            # Skip numeric IDs and URL-encoded paths (likely sensitive)
            if safe_parts and safe_parts[-1] != "...":
                safe_parts.append("...")
        else:
            safe_parts.append(part)

        i += 1

    return "/" + "/".join(safe_parts) if safe_parts else endpoint


class GitLabClient:
    """Async client for GitLab REST API v4 (gitlab.com only)."""

    def __init__(
        self,
        access_token: str,
        tenant_id: str,
        per_page: int = DEFAULT_PER_PAGE,
    ):
        """Initialize GitLab client.

        Args:
            access_token: OAuth access token or personal access token
            tenant_id: Tenant ID for per-tenant rate limiting
            per_page: Number of items per page for paginated requests
        """
        self.access_token = access_token
        self.tenant_id = tenant_id
        self.api_url = GITLAB_API_URL
        self.per_page = min(per_page, MAX_PER_PAGE)

        # Get per-tenant rate limiters (cached per tenant_id)
        self._limiters = _get_limiters(tenant_id)

        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=CLIENT_TIMEOUT_SECONDS,
        )

    async def aclose(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "GitLabClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    @rate_limited(max_retries=5, base_delay=5)
    async def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> httpx.Response:
        """Make a GET request to the GitLab API with rate limiting and retry logic."""
        url = f"{self.api_url}{endpoint}"
        safe_endpoint = _get_safe_endpoint_tag(endpoint)

        try:
            async with self._limiters.general:
                response = await self._client.get(url, params=params)
        except httpx.TimeoutException as e:
            logger.warning(f"GitLab GET {safe_endpoint} timeout, retrying")
            raise RateLimitedError(
                retry_after=TIMEOUT_RETRY_AFTER_SECONDS,
                message=f"GitLab timeout on {safe_endpoint}",
            ) from e

        # Handle rate limiting (429 Too Many Requests)
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            logger.warning(
                f"GitLab GET {safe_endpoint} rate limited (429), retry after {retry_after}s"
            )
            raise RateLimitedError(
                retry_after=retry_after,
                message=f"GitLab rate limited on {safe_endpoint}",
            )

        # Handle server errors (5xx) with retry
        if response.is_server_error:
            logger.warning(
                f"GitLab GET {safe_endpoint} server error ({response.status_code}), retrying"
            )
            raise RateLimitedError(
                retry_after=DEFAULT_RETRY_AFTER_SECONDS,
                message=f"GitLab server error on {safe_endpoint}",
            )

        response.raise_for_status()
        return response

    @rate_limited(max_retries=5, base_delay=5)
    async def _get_raw(self, url: str, params: dict[str, Any] | None = None) -> bytes:
        """Make a GET request for raw content with rate limiting and retry logic."""
        # Extract endpoint from full URL for safe logging
        endpoint = url.replace(self.api_url, "") if url.startswith(self.api_url) else url
        safe_endpoint = _get_safe_endpoint_tag(endpoint)

        try:
            async with self._limiters.general:
                response = await self._client.get(url, params=params)
        except httpx.TimeoutException as e:
            logger.warning(f"GitLab GET {safe_endpoint} timeout, retrying")
            raise RateLimitedError(
                retry_after=TIMEOUT_RETRY_AFTER_SECONDS,
                message=f"GitLab timeout on {safe_endpoint}",
            ) from e

        # Handle rate limiting (429 Too Many Requests)
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            logger.warning(
                f"GitLab GET {safe_endpoint} rate limited (429), retry after {retry_after}s"
            )
            raise RateLimitedError(
                retry_after=retry_after,
                message=f"GitLab rate limited on {safe_endpoint}",
            )

        # Handle server errors (5xx) with retry
        if response.is_server_error:
            logger.warning(
                f"GitLab GET {safe_endpoint} server error ({response.status_code}), retrying"
            )
            raise RateLimitedError(
                retry_after=DEFAULT_RETRY_AFTER_SECONDS,
                message=f"GitLab server error on {safe_endpoint}",
            )

        response.raise_for_status()
        return response.content

    async def _get_paginated(
        self, endpoint: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Make paginated GET requests and return all results."""
        results: list[dict[str, Any]] = []
        params = params or {}
        params["per_page"] = self.per_page
        page = 1

        while True:
            params["page"] = page
            response = await self._get(endpoint, params)
            data = response.json()

            if not data:
                break

            results.extend(data)

            # Check for next page using headers
            total_pages = response.headers.get("x-total-pages")
            if total_pages and page >= int(total_pages):
                break

            # Also check if we got fewer results than per_page (last page)
            if len(data) < self.per_page:
                break

            page += 1

        return results

    # ========== User Info ==========

    async def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user."""
        response = await self._get("/user")
        return response.json()

    # ========== Projects ==========

    async def get_project(self, project_id_or_path: str | int) -> dict[str, Any]:
        """Get a single project by ID or path.

        Args:
            project_id_or_path: Project ID (int) or URL-encoded path (e.g., "group%2Fproject")
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)
        response = await self._get(f"/projects/{project_id_or_path}")
        return response.json()

    async def get_accessible_projects(
        self,
        membership: bool = True,
        archived: bool = False,
        min_access_level: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all projects accessible to the authenticated user.

        Args:
            membership: Only return projects the user is a member of
            archived: Include archived projects
            min_access_level: Minimum access level (10=guest, 20=reporter, 30=developer, 40=maintainer, 50=owner)
        """
        params: dict[str, Any] = {
            "membership": str(membership).lower(),
            "archived": str(archived).lower(),
            "simple": "false",  # Get full project info
        }
        if min_access_level is not None:
            params["min_access_level"] = min_access_level

        return await self._get_paginated("/projects", params)

    async def get_group_projects(self, group_id_or_path: str | int) -> list[dict[str, Any]]:
        """Get all projects in a group.

        Args:
            group_id_or_path: Group ID (int) or URL-encoded path
        """
        if isinstance(group_id_or_path, str):
            group_id_or_path = quote_plus(group_id_or_path)
        return await self._get_paginated(f"/groups/{group_id_or_path}/projects")

    # ========== Groups ==========

    async def get_user_groups(self) -> list[dict[str, Any]]:
        """Get all groups the authenticated user is a member of."""
        return await self._get_paginated("/groups", {"membership": "true"})

    # ========== Merge Requests ==========

    async def get_project_merge_requests(
        self,
        project_id_or_path: str | int,
        state: str = "all",
        scope: str = "all",
        order_by: str = "updated_at",
        sort: str = "desc",
        updated_after: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all merge requests for a project.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            state: MR state filter (opened, closed, merged, all)
            scope: Scope filter (all, created_by_me, assigned_to_me)
            order_by: Order by field (created_at, updated_at)
            sort: Sort direction (asc, desc)
            updated_after: Only return MRs updated after this ISO 8601 datetime
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        params: dict[str, str] = {
            "state": state,
            "scope": scope,
            "order_by": order_by,
            "sort": sort,
        }
        if updated_after:
            params["updated_after"] = updated_after
        return await self._get_paginated(f"/projects/{project_id_or_path}/merge_requests", params)

    async def get_merge_request(self, project_id_or_path: str | int, mr_iid: int) -> dict[str, Any]:
        """Get a single merge request.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            mr_iid: Merge request internal ID
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        response = await self._get(f"/projects/{project_id_or_path}/merge_requests/{mr_iid}")
        return response.json()

    async def get_merge_request_changes(
        self, project_id_or_path: str | int, mr_iid: int
    ) -> dict[str, Any]:
        """Get merge request with changes (diffs).

        Args:
            project_id_or_path: Project ID or URL-encoded path
            mr_iid: Merge request internal ID
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        response = await self._get(
            f"/projects/{project_id_or_path}/merge_requests/{mr_iid}/changes"
        )
        return response.json()

    async def get_merge_request_diffs(
        self, project_id_or_path: str | int, mr_iid: int
    ) -> list[dict[str, Any]]:
        """Get merge request diffs (file changes).

        Args:
            project_id_or_path: Project ID or URL-encoded path
            mr_iid: Merge request internal ID
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        return await self._get_paginated(
            f"/projects/{project_id_or_path}/merge_requests/{mr_iid}/diffs"
        )

    # ========== MR Notes (Comments) ==========

    async def get_merge_request_notes(
        self, project_id_or_path: str | int, mr_iid: int, sort: str = "asc"
    ) -> list[dict[str, Any]]:
        """Get all notes (comments) on a merge request.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            mr_iid: Merge request internal ID
            sort: Sort direction (asc, desc)
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        params = {"sort": sort}
        return await self._get_paginated(
            f"/projects/{project_id_or_path}/merge_requests/{mr_iid}/notes", params
        )

    # ========== MR Approvals ==========

    async def get_merge_request_approvals(
        self, project_id_or_path: str | int, mr_iid: int
    ) -> dict[str, Any]:
        """Get merge request approvals.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            mr_iid: Merge request internal ID
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        response = await self._get(
            f"/projects/{project_id_or_path}/merge_requests/{mr_iid}/approvals"
        )
        return response.json()

    # ========== MR Pipelines ==========

    async def get_merge_request_pipelines(
        self, project_id_or_path: str | int, mr_iid: int
    ) -> list[dict[str, Any]]:
        """Get all pipelines for a merge request.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            mr_iid: Merge request internal ID
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        return await self._get_paginated(
            f"/projects/{project_id_or_path}/merge_requests/{mr_iid}/pipelines"
        )

    # ========== Repository Files ==========

    async def get_repository_tree(
        self,
        project_id_or_path: str | int,
        path: str = "",
        ref: str | None = None,
        recursive: bool = True,
    ) -> list[dict[str, Any]]:
        """Get repository file tree.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            path: Path inside the repository (empty for root)
            ref: Branch, tag, or commit SHA (default branch if not specified)
            recursive: Whether to get tree recursively
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        params: dict[str, Any] = {
            "recursive": str(recursive).lower(),
        }
        if path:
            params["path"] = path
        if ref:
            params["ref"] = ref

        return await self._get_paginated(f"/projects/{project_id_or_path}/repository/tree", params)

    async def get_file_content(
        self,
        project_id_or_path: str | int,
        file_path: str,
        ref: str | None = None,
    ) -> dict[str, Any]:
        """Get file content from repository.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            file_path: URL-encoded path of the file
            ref: Branch, tag, or commit SHA (default branch if not specified)

        Returns:
            Dict with file info including base64 encoded content
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        encoded_file_path = quote_plus(file_path)
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref

        response = await self._get(
            f"/projects/{project_id_or_path}/repository/files/{encoded_file_path}", params
        )
        return response.json()

    async def get_file_raw(
        self,
        project_id_or_path: str | int,
        file_path: str,
        ref: str | None = None,
    ) -> bytes:
        """Get raw file content from repository.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            file_path: URL-encoded path of the file
            ref: Branch, tag, or commit SHA (default branch if not specified)

        Returns:
            Raw file content as bytes
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        encoded_file_path = quote_plus(file_path)
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref

        url = (
            f"{self.api_url}/projects/{project_id_or_path}/repository/files/{encoded_file_path}/raw"
        )
        return await self._get_raw(url, params)

    async def get_file_blame(
        self,
        project_id_or_path: str | int,
        file_path: str,
        ref: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get file blame information (contributors).

        Args:
            project_id_or_path: Project ID or URL-encoded path
            file_path: URL-encoded path of the file
            ref: Branch, tag, or commit SHA (default branch if not specified)

        Returns:
            List of blame chunks with commit info
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        encoded_file_path = quote_plus(file_path)
        params: dict[str, Any] = {}
        if ref:
            params["ref"] = ref

        return await self._get_paginated(
            f"/projects/{project_id_or_path}/repository/files/{encoded_file_path}/blame", params
        )

    async def get_repository_commits(
        self,
        project_id_or_path: str | int,
        path: str | None = None,
        ref: str | None = None,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get repository commits, optionally filtered by path and date.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            path: File path to filter commits (optional)
            ref: Branch, tag, or commit SHA (default branch if not specified)
            since: Only return commits after this ISO 8601 datetime (optional)

        Returns:
            List of commits
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        params: dict[str, Any] = {}
        if path:
            params["path"] = path
        if ref:
            params["ref_name"] = ref
        if since:
            params["since"] = since

        return await self._get_paginated(
            f"/projects/{project_id_or_path}/repository/commits", params
        )

    async def get_commit(
        self,
        project_id_or_path: str | int,
        commit_sha: str,
    ) -> dict[str, Any]:
        """Get a single commit by SHA.

        Args:
            project_id_or_path: Project ID or URL-encoded path
            commit_sha: The commit SHA

        Returns:
            Commit data including id, authored_date, committed_date, etc.
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        response = await self._get(
            f"/projects/{project_id_or_path}/repository/commits/{commit_sha}"
        )
        return response.json()

    async def get_commit_diff(
        self,
        project_id_or_path: str | int,
        commit_sha: str,
    ) -> list[dict[str, Any]]:
        """Get the diff of a specific commit (list of changed files).

        Args:
            project_id_or_path: Project ID or URL-encoded path
            commit_sha: The commit SHA

        Returns:
            List of diffs with file paths and changes
        """
        if isinstance(project_id_or_path, str):
            project_id_or_path = quote_plus(project_id_or_path)

        return await self._get_paginated(
            f"/projects/{project_id_or_path}/repository/commits/{commit_sha}/diff"
        )

    async def get_default_branch(self, project_id_or_path: str | int) -> str:
        """Get the default branch of a project.

        Args:
            project_id_or_path: Project ID or URL-encoded path

        Returns:
            Default branch name (e.g., "main", "master")
        """
        project = await self.get_project(project_id_or_path)
        return project.get("default_branch", "main")
