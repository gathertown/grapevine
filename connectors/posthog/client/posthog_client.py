"""
PostHog REST API client with rate limiting support.

PostHog rate limits:
- Analytics endpoints: 240/min, 1200/hour
- Query endpoint: 2400/hour
- Create/Read/Update/Delete: 480/min, 4800/hour
- Feature flag local evaluation: 600/min

The client implements exponential backoff and respects rate limit headers.
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


# Pydantic models for PostHog API responses
class PostHogUser(BaseModel):
    """PostHog user information."""

    id: int
    uuid: str
    distinct_id: str
    first_name: str | None = None
    last_name: str | None = None
    email: str


class PostHogProject(BaseModel):
    """PostHog project (team) information."""

    id: int
    uuid: str
    name: str
    api_token: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class PostHogDashboard(BaseModel):
    """PostHog dashboard information."""

    id: int
    name: str
    description: str | None = None
    pinned: bool = False
    created_at: str
    updated_at: str | None = None
    created_by: dict[str, Any] | None = None
    is_shared: bool = False
    deleted: bool = False
    tags: list[str] = Field(default_factory=list)
    tiles: list[dict[str, Any]] = Field(default_factory=list)


class PostHogInsight(BaseModel):
    """PostHog insight (chart/query) information."""

    id: int
    short_id: str
    name: str | None = None
    description: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] | None = None
    created_at: str
    updated_at: str | None = None
    created_by: dict[str, Any] | None = None
    last_modified_at: str | None = None
    last_modified_by: dict[str, Any] | None = None
    deleted: bool = False
    saved: bool = True
    tags: list[str] = Field(default_factory=list)
    dashboards: list[int] = Field(default_factory=list)
    result: Any = None


class PostHogFeatureFlag(BaseModel):
    """PostHog feature flag information."""

    id: int
    key: str
    name: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    created_at: str
    updated_at: str | None = None
    created_by: dict[str, Any] | None = None
    deleted: bool = False
    ensure_experience_continuity: bool = False
    rollout_percentage: int | None = None
    tags: list[str] = Field(default_factory=list)


class PostHogAnnotation(BaseModel):
    """PostHog annotation information."""

    id: int
    content: str
    date_marker: str
    created_at: str
    updated_at: str | None = None
    created_by: dict[str, Any] | None = None
    deleted: bool = False
    scope: str = "organization"
    dashboard_item: int | None = None


class PostHogExperiment(BaseModel):
    """PostHog experiment (A/B test) information."""

    id: int
    name: str
    description: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    created_at: str
    updated_at: str | None = None
    created_by: dict[str, Any] | None = None
    feature_flag_key: str | None = None
    feature_flag: dict[str, Any] | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    archived: bool = False


class PostHogSurvey(BaseModel):
    """PostHog survey information."""

    id: str
    name: str
    description: str | None = None
    type: str = "popover"
    questions: list[dict[str, Any]] = Field(default_factory=list)
    appearance: dict[str, Any] | None = None
    targeting_flag_filters: dict[str, Any] | None = None
    start_date: str | None = None
    end_date: str | None = None
    created_at: str
    updated_at: str | None = None
    created_by: dict[str, Any] | None = None
    archived: bool = False


@dataclass
class PostHogRateLimitInfo:
    """Rate limit information from PostHog response headers."""

    retry_after: int | None = None
    limit: int | None = None
    remaining: int | None = None


class PostHogAPIError(Exception):
    """Exception raised for PostHog API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        rate_limit_info: PostHogRateLimitInfo | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.rate_limit_info = rate_limit_info


class PostHogClient:
    """
    PostHog REST API client.

    Handles authentication, rate limiting, and retry logic for PostHog API requests.
    """

    def __init__(
        self,
        personal_api_key: str,
        host: str = "https://us.posthog.com",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        """
        Initialize the PostHog client.

        Args:
            personal_api_key: Personal API key for PostHog API
            host: PostHog instance host (us.posthog.com, eu.posthog.com, or self-hosted)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts for rate-limited requests
        """
        self.personal_api_key = personal_api_key
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create an async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.host,
                headers={
                    "Authorization": f"Bearer {self.personal_api_key}",
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

    async def __aenter__(self) -> PostHogClient:
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        _exc_type: type | None,
        _exc_val: Exception | None,
        _exc_tb: object,
    ) -> None:
        """Async context manager exit - ensures client is closed."""
        await self.close()

    def _extract_rate_limit_info(self, response: httpx.Response) -> PostHogRateLimitInfo:
        """Extract rate limit information from response headers."""
        retry_after_str = response.headers.get("Retry-After")
        limit_str = response.headers.get("X-RateLimit-Limit")
        remaining_str = response.headers.get("X-RateLimit-Remaining")

        return PostHogRateLimitInfo(
            retry_after=int(retry_after_str) if retry_after_str else None,
            limit=int(limit_str) if limit_str else None,
            remaining=int(remaining_str) if remaining_str else None,
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
            PostHogAPIError: For API errors
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
                        "PostHog rate limit hit",
                        retry_after=retry_after,
                        limit=rate_limit_info.limit,
                        remaining=rate_limit_info.remaining,
                        attempt=attempt,
                    )

                    # If retry_after is long, raise ExtendVisibilityException
                    if retry_after > 60:
                        raise ExtendVisibilityException(
                            visibility_timeout_seconds=retry_after + 30,
                            message=f"PostHog rate limited, need to wait {retry_after} seconds",
                        )

                    if attempt < self.max_retries:
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        raise PostHogAPIError(
                            f"Rate limit exceeded after {self.max_retries} retries",
                            status_code=429,
                            rate_limit_info=rate_limit_info,
                        )

                if response.status_code == 401:
                    raise PostHogAPIError("Unauthorized - API key may be invalid or expired", 401)

                if response.status_code == 403:
                    raise PostHogAPIError("Forbidden - insufficient permissions", 403)

                if response.status_code == 404:
                    raise PostHogAPIError("Not found", 404)

                if response.status_code >= 400:
                    raise PostHogAPIError(
                        f"PostHog API error: {response.status_code} - {response.text}",
                        response.status_code,
                    )

                return response.json()

            except httpx.TimeoutException as e:
                logger.error(
                    "PostHog API timeout", endpoint=endpoint, attempt=attempt, error=str(e)
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(2**attempt)
                    continue
                raise PostHogAPIError(f"Request timeout after {self.max_retries} retries")

            except httpx.RequestError as e:
                logger.error("PostHog API request error", endpoint=endpoint, error=str(e))
                raise PostHogAPIError(f"Request failed: {e}")

        raise PostHogAPIError("Max retries exceeded")

    async def _paginate(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Paginate through all results for an endpoint.

        PostHog uses limit/offset pagination for most endpoints.

        Args:
            endpoint: API endpoint path
            params: Additional query parameters
            limit: Number of results per page

        Returns:
            List of all results
        """
        all_results: list[dict[str, Any]] = []
        offset = 0
        params = params or {}

        while True:
            page_params = {**params, "limit": limit, "offset": offset}
            data = await self._request("GET", endpoint, params=page_params)

            results = data.get("results", [])
            all_results.extend(results)

            # Check if there are more pages
            if data.get("next") is None or len(results) < limit:
                break

            offset += limit

        return all_results

    # User/Me endpoints
    async def get_current_user(self) -> PostHogUser:
        """Get the current authenticated user's information."""
        data = await self._request("GET", "/api/users/@me/")
        return PostHogUser(**data)

    # Project endpoints
    async def get_projects(self) -> list[PostHogProject]:
        """Get all accessible projects."""
        results = await self._paginate("/api/projects/")
        return [PostHogProject(**p) for p in results]

    async def get_project(self, project_id: int) -> PostHogProject:
        """Get a specific project by ID."""
        data = await self._request("GET", f"/api/projects/{project_id}/")
        return PostHogProject(**data)

    # Dashboard endpoints
    async def get_dashboards(self, project_id: int) -> list[PostHogDashboard]:
        """Get all dashboards for a project."""
        results = await self._paginate(f"/api/projects/{project_id}/dashboards/")
        return [PostHogDashboard(**d) for d in results if not d.get("deleted", False)]

    async def get_dashboard(self, project_id: int, dashboard_id: int) -> PostHogDashboard:
        """Get a specific dashboard."""
        data = await self._request("GET", f"/api/projects/{project_id}/dashboards/{dashboard_id}/")
        return PostHogDashboard(**data)

    # Insight endpoints
    async def get_insights(self, project_id: int, saved_only: bool = True) -> list[PostHogInsight]:
        """Get all insights for a project."""
        params = {"saved": "true"} if saved_only else {}
        results = await self._paginate(f"/api/projects/{project_id}/insights/", params=params)
        return [PostHogInsight(**i) for i in results if not i.get("deleted", False)]

    async def get_insight(self, project_id: int, insight_id: int) -> PostHogInsight:
        """Get a specific insight."""
        data = await self._request("GET", f"/api/projects/{project_id}/insights/{insight_id}/")
        return PostHogInsight(**data)

    # Feature flag endpoints
    async def get_feature_flags(self, project_id: int) -> list[PostHogFeatureFlag]:
        """Get all feature flags for a project."""
        results = await self._paginate(f"/api/projects/{project_id}/feature_flags/")
        return [PostHogFeatureFlag(**f) for f in results if not f.get("deleted", False)]

    async def get_feature_flag(self, project_id: int, flag_id: int) -> PostHogFeatureFlag:
        """Get a specific feature flag."""
        data = await self._request("GET", f"/api/projects/{project_id}/feature_flags/{flag_id}/")
        return PostHogFeatureFlag(**data)

    # Annotation endpoints
    async def get_annotations(self, project_id: int) -> list[PostHogAnnotation]:
        """Get all annotations for a project."""
        results = await self._paginate(f"/api/projects/{project_id}/annotations/")
        return [PostHogAnnotation(**a) for a in results if not a.get("deleted", False)]

    async def get_annotation(self, project_id: int, annotation_id: int) -> PostHogAnnotation:
        """Get a specific annotation."""
        data = await self._request(
            "GET", f"/api/projects/{project_id}/annotations/{annotation_id}/"
        )
        return PostHogAnnotation(**data)

    # Experiment endpoints
    async def get_experiments(self, project_id: int) -> list[PostHogExperiment]:
        """Get all experiments for a project."""
        results = await self._paginate(f"/api/projects/{project_id}/experiments/")
        return [PostHogExperiment(**e) for e in results if not e.get("archived", False)]

    async def get_experiment(self, project_id: int, experiment_id: int) -> PostHogExperiment:
        """Get a specific experiment."""
        data = await self._request(
            "GET", f"/api/projects/{project_id}/experiments/{experiment_id}/"
        )
        return PostHogExperiment(**data)

    # Survey endpoints
    async def get_surveys(self, project_id: int) -> list[PostHogSurvey]:
        """Get all surveys for a project."""
        results = await self._paginate(f"/api/projects/{project_id}/surveys/")
        return [PostHogSurvey(**s) for s in results if not s.get("archived", False)]

    async def get_survey(self, project_id: int, survey_id: str) -> PostHogSurvey:
        """Get a specific survey."""
        data = await self._request("GET", f"/api/projects/{project_id}/surveys/{survey_id}/")
        return PostHogSurvey(**data)

    # Query endpoints (HogQL)
    async def execute_hogql_query(
        self,
        project_id: int,
        query: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Execute a HogQL query against PostHog.

        HogQL is PostHog's SQL-like query language for analytics data.

        Args:
            project_id: The project ID to query
            query: HogQL query string (SQL-like syntax)
            limit: Maximum number of rows to return

        Returns:
            Dictionary with:
            - results: List of result rows
            - columns: List of column names
            - types: List of column types
            - hasMore: Whether there are more results
            - error: Error message if query failed

        Example queries:
            - "SELECT count() FROM events WHERE event = '$pageview'"
            - "SELECT distinct_id, count() FROM events GROUP BY distinct_id LIMIT 10"
            - "SELECT properties.$current_url, count() FROM events GROUP BY 1 ORDER BY 2 DESC"
        """
        # Add LIMIT if not present
        query_upper = query.upper()
        if "LIMIT" not in query_upper:
            query = f"{query.rstrip().rstrip(';')} LIMIT {limit}"

        request_body = {
            "query": {
                "kind": "HogQLQuery",
                "query": query,
            }
        }

        data = await self._request(
            "POST",
            f"/api/projects/{project_id}/query/",
            json_data=request_body,
        )

        return {
            "results": data.get("results", []),
            "columns": data.get("columns", []),
            "types": data.get("types", []),
            "hasMore": data.get("hasMore", False),
            "error": data.get("error"),
            "hogql": data.get("hogql"),  # The actual HogQL that was executed
        }

    @staticmethod
    def _escape_hogql_string(value: str) -> str:
        """Escape a string for safe use in HogQL queries."""
        # Escape single quotes by doubling them and backslashes
        return value.replace("\\", "\\\\").replace("'", "''")

    async def get_event_count(
        self,
        project_id: int,
        event_name: str | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """
        Get event counts for the last N days.

        Args:
            project_id: The project ID
            event_name: Optional specific event to count (e.g., '$pageview', 'signup')
            days: Number of days to look back (default: 7)

        Returns:
            Dictionary with count and breakdown by day
        """
        if event_name:
            # Escape the event name to prevent HogQL injection
            escaped_event_name = self._escape_hogql_string(event_name)
            query = f"""
                SELECT
                    toDate(timestamp) as date,
                    count() as count
                FROM events
                WHERE event = '{escaped_event_name}'
                AND timestamp > now() - INTERVAL {days} DAY
                GROUP BY date
                ORDER BY date DESC
            """
        else:
            query = f"""
                SELECT
                    toDate(timestamp) as date,
                    count() as count
                FROM events
                WHERE timestamp > now() - INTERVAL {days} DAY
                GROUP BY date
                ORDER BY date DESC
            """

        return await self.execute_hogql_query(project_id, query, limit=days + 1)

    async def get_unique_users(
        self,
        project_id: int,
        days: int = 7,
    ) -> dict[str, Any]:
        """
        Get unique user counts for the last N days.

        Args:
            project_id: The project ID
            days: Number of days to look back (default: 7)

        Returns:
            Dictionary with unique user count per day
        """
        query = f"""
            SELECT
                toDate(timestamp) as date,
                count(DISTINCT distinct_id) as unique_users
            FROM events
            WHERE timestamp > now() - INTERVAL {days} DAY
            GROUP BY date
            ORDER BY date DESC
        """
        return await self.execute_hogql_query(project_id, query, limit=days + 1)

    async def get_top_events(
        self,
        project_id: int,
        days: int = 7,
        limit: int = 10,
    ) -> dict[str, Any]:
        """
        Get the top events by count.

        Args:
            project_id: The project ID
            days: Number of days to look back
            limit: Number of top events to return

        Returns:
            Dictionary with event names and counts
        """
        query = f"""
            SELECT
                event,
                count() as count
            FROM events
            WHERE timestamp > now() - INTERVAL {days} DAY
            GROUP BY event
            ORDER BY count DESC
            LIMIT {limit}
        """
        return await self.execute_hogql_query(project_id, query, limit=limit)


async def get_posthog_client_for_tenant(tenant_id: str) -> PostHogClient:
    """
    Create a PostHogClient for a specific tenant.

    Args:
        tenant_id: The tenant ID

    Returns:
        Configured PostHogClient instance
    """
    from src.clients.ssm import SSMClient

    ssm_client = SSMClient()

    # PostHog API key stored in SSM
    personal_api_key = await ssm_client.get_api_key(tenant_id, "POSTHOG_PERSONAL_API_KEY")

    if not personal_api_key:
        raise ValueError(f"No PostHog API key found for tenant {tenant_id}")

    # Get optional host configuration (defaults to US cloud)
    host = await ssm_client.get_api_key(tenant_id, "POSTHOG_HOST")
    if not host:
        host = "https://us.posthog.com"

    return PostHogClient(personal_api_key=personal_api_key, host=host)
