import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel

from src.jobs.exceptions import ExtendVisibilityException
from src.utils.logging import get_logger

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)


class LinearTeam(BaseModel):
    id: str
    name: str


class LinearClient:
    """A client for interacting with the Linear GraphQL API."""

    API_URL = "https://api.linear.app/graphql"

    def __init__(self, token: str):
        if not token:
            raise ValueError("Linear token is required and cannot be empty")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": token,
                "Content-Type": "application/json",
            }
        )

    def _make_request(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a GraphQL request to the Linear API."""
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = self.session.post(self.API_URL, json=payload)

            # Log rate limit headers for monitoring (do this first)
            self._log_rate_limit_headers(response.headers)

            # Parse JSON response regardless of status code to check for GraphQL errors
            try:
                data = response.json()
            except ValueError:
                # If we can't parse JSON, fall back to HTTP status handling
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Linear HTTP 429 rate limit hit, retrying after {retry_after}s")
                    raise RateLimitedError(retry_after=retry_after)
                response.raise_for_status()
                return {}

            # Check for GraphQL-level rate limiting errors FIRST (Linear uses 400 status for these)
            if "errors" in data:
                for error in data["errors"]:
                    extensions = error.get("extensions", {})
                    if extensions.get("code") == "RATELIMITED":
                        # Try to get retry time from headers first (most accurate)
                        retry_after = self._calculate_retry_from_headers(response.headers)
                        retry_method = "headers"

                        if retry_after == 60:  # Default fallback from headers
                            retry_after = self._calculate_retry_from_rate_limit_meta(extensions)
                            retry_method = "metadata"

                        logger.warning(
                            f"Linear GraphQL rate limit hit: {error.get('message', 'Rate limited')}"
                        )
                        logger.warning(
                            f"Retrying after {retry_after}s (calculated from {retry_method})"
                        )
                        raise RateLimitedError(retry_after=retry_after)

                # Handle other GraphQL errors (non-rate-limit)
                response.raise_for_status()
                raise ValueError(f"GraphQL errors: {data['errors']}")

            # Only raise for status if no GraphQL errors
            response.raise_for_status()

            return data.get("data", {})

        except (RateLimitedError, ExtendVisibilityException):
            # Let rate limit errors propagate to @rate_limited decorator
            raise
        except requests.exceptions.HTTPError:
            logger.error(f"Linear API HTTP error: {response.status_code} - {response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Linear API request error: {e}")
            raise

    def _log_rate_limit_headers(self, headers: Any) -> None:
        """Log Linear's rate limit headers for monitoring."""
        # Request rate limits
        req_limit = headers.get("X-RateLimit-Requests-Limit")
        req_remaining = headers.get("X-RateLimit-Requests-Remaining")

        # Complexity limits
        complexity = headers.get("X-Complexity")
        comp_limit = headers.get("X-RateLimit-Complexity-Limit")
        comp_remaining = headers.get("X-RateLimit-Complexity-Remaining")

        # Endpoint-specific limits
        endpoint_limit = headers.get("X-RateLimit-Endpoint-Requests-Limit")
        endpoint_remaining = headers.get("X-RateLimit-Endpoint-Requests-Remaining")
        endpoint_name = headers.get("X-RateLimit-Endpoint-Name")

        if req_limit and req_remaining:
            usage_pct = ((int(req_limit) - int(req_remaining)) / int(req_limit)) * 100
            logger.debug(
                f"Linear requests: {req_remaining}/{req_limit} remaining ({usage_pct:.1f}% used)"
            )

            # Warn if getting close to limit
            if usage_pct > 80:
                logger.warning(f"Linear request rate limit approaching: {usage_pct:.1f}% used")

        if comp_limit and comp_remaining and complexity:
            comp_usage_pct = ((int(comp_limit) - int(comp_remaining)) / int(comp_limit)) * 100
            logger.debug(
                f"Linear complexity: {complexity} points, {comp_remaining}/{comp_limit} remaining ({comp_usage_pct:.1f}% used)"
            )

            # Warn if getting close to complexity limit
            if comp_usage_pct > 80:
                logger.warning(
                    f"Linear complexity rate limit approaching: {comp_usage_pct:.1f}% used"
                )

        if endpoint_limit and endpoint_remaining and endpoint_name:
            endpoint_usage_pct = (
                (int(endpoint_limit) - int(endpoint_remaining)) / int(endpoint_limit)
            ) * 100
            logger.debug(
                f"Linear endpoint {endpoint_name}: {endpoint_remaining}/{endpoint_limit} remaining ({endpoint_usage_pct:.1f}% used)"
            )

    def _calculate_retry_from_headers(self, headers: Any) -> int:
        """Calculate appropriate retry delay from Linear's rate limit headers."""
        import time

        # Check for endpoint-specific reset time first
        endpoint_reset = headers.get("X-RateLimit-Endpoint-Requests-Reset")
        if endpoint_reset:
            try:
                reset_time = int(endpoint_reset) / 1000  # Convert from milliseconds
                retry_after = max(1, int(reset_time - time.time()) + 1)  # Add 1s buffer
                return min(retry_after, 300)  # Cap at 5 minutes
            except (ValueError, TypeError):
                pass

        # Check request rate limit reset time
        req_reset = headers.get("X-RateLimit-Requests-Reset")
        if req_reset:
            try:
                reset_time = int(req_reset) / 1000  # Convert from milliseconds
                retry_after = max(1, int(reset_time - time.time()) + 1)  # Add 1s buffer
                return min(retry_after, 300)  # Cap at 5 minutes
            except (ValueError, TypeError):
                pass

        # Check complexity rate limit reset time
        comp_reset = headers.get("X-RateLimit-Complexity-Reset")
        if comp_reset:
            try:
                reset_time = int(comp_reset) / 1000  # Convert from milliseconds
                retry_after = max(1, int(reset_time - time.time()) + 1)  # Add 1s buffer
                return min(retry_after, 300)  # Cap at 5 minutes
            except (ValueError, TypeError):
                pass

        # Fallback to default retry time
        return 60

    def _calculate_retry_from_rate_limit_meta(self, extensions: dict[str, Any]) -> int:
        """Calculate retry delay from Linear's rate limit metadata using leaky bucket algorithm."""
        try:
            # Linear provides rate limit info in extensions.meta.rateLimitResult
            meta = extensions.get("meta", {})
            rate_limit_result = meta.get("rateLimitResult", {})

            # Get the limit and duration to calculate refill rate
            limit = rate_limit_result.get("limit")
            duration_ms = rate_limit_result.get("duration")

            if limit and duration_ms and limit > 0 and duration_ms > 0:
                # Calculate leaky bucket refill rate: requests per second
                duration_seconds = duration_ms / 1000
                refill_rate = limit / duration_seconds  # requests per second

                # Time between token refills (seconds per request)
                time_per_token = 1 / refill_rate

                # Wait for enough tokens to accumulate to avoid immediate re-rate-limiting
                # For high-frequency APIs, wait for 2-3 tokens. For low-frequency, wait for 1-2 tokens.
                tokens_to_wait = (
                    2 if refill_rate >= 1.0 else 1
                )  # At least 1 request per second vs less

                retry_after = int(time_per_token * tokens_to_wait) + 1  # Add 1s buffer

                logger.debug(
                    f"Linear leaky bucket: {limit} requests/{duration_seconds}s = {refill_rate:.3f} req/s"
                )
                logger.debug(
                    f"Time per token: {time_per_token:.1f}s, waiting for {tokens_to_wait} tokens = {retry_after}s"
                )

                return max(1, min(retry_after, 300))

        except (ValueError, TypeError, KeyError) as e:
            logger.debug(f"Failed to parse Linear rate limit metadata: {e}")

        # Smart fallback based on Linear's documented limits
        # Standard rate is 1500 requests/hour = 0.417 requests/second = 2.4 seconds per request
        # Wait for 2-3 intervals to be safe
        return 5

    def get_rate_limit_status(self) -> dict[str, Any]:
        """Get current rate limit status by making a minimal query."""
        query = """
        query {
            viewer {
                id
            }
        }
        """

        try:
            # Make a minimal request to get headers
            response = self.session.post(self.API_URL, json={"query": query})
            response.raise_for_status()

            headers = response.headers
            status = {
                "requests": {
                    "limit": headers.get("X-RateLimit-Requests-Limit"),
                    "remaining": headers.get("X-RateLimit-Requests-Remaining"),
                    "reset": headers.get("X-RateLimit-Requests-Reset"),
                },
                "complexity": {
                    "limit": headers.get("X-RateLimit-Complexity-Limit"),
                    "remaining": headers.get("X-RateLimit-Complexity-Remaining"),
                    "reset": headers.get("X-RateLimit-Complexity-Reset"),
                    "last_query": headers.get("X-Complexity"),
                },
            }

            # Calculate usage percentages
            if status["requests"]["limit"] and status["requests"]["remaining"]:
                limit = int(status["requests"]["limit"])
                remaining = int(status["requests"]["remaining"])
                status["requests"]["usage_percent"] = f"{((limit - remaining) / limit) * 100:.1f}%"

            if status["complexity"]["limit"] and status["complexity"]["remaining"]:
                limit = int(status["complexity"]["limit"])
                remaining = int(status["complexity"]["remaining"])
                status["complexity"]["usage_percent"] = (
                    f"{((limit - remaining) / limit) * 100:.1f}%"
                )

            return status

        except Exception as e:
            logger.error(f"Failed to get rate limit status: {e}")
            return {}

    @rate_limited()
    def get_public_teams(self) -> list[LinearTeam]:
        """Get only public teams accessible to the user."""
        query = """
        query {
            teams(filter: { private: { eq: false } }) {
                nodes {
                    id
                    name
                }
            }
        }
        """
        result = self._make_request(query)
        teams_data = result.get("teams", {}).get("nodes", [])
        public_teams = [LinearTeam(**team) for team in teams_data]

        logger.info(f"Found {len(public_teams)} public teams")

        return public_teams

    @rate_limited()
    def get_issue_ids(
        self,
        team_id: str | None = None,
        first: int = 100,  # capped at 250 (verified manually)
        after: str | None = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        """
        Get issues, optionally filtered by team and date range.

        Args:
            team_id: Optional team ID to filter issues
            first: Number of issues to fetch
            after: Cursor for pagination
            include_archived: Whether to include archived issues
        """
        # Build the filter
        filter_parts = []
        if team_id:
            filter_parts.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')

        filter_str = ""
        if filter_parts:
            filter_str = f"filter: {{ {', '.join(filter_parts)} }}"

        query = f"""
        query($first: Int, $after: String) {{
            issues(first: $first, after: $after, includeArchived: {str(include_archived).lower()}, {filter_str}) {{
                nodes {{
                    id
                }}
                pageInfo {{
                    hasNextPage
                    endCursor
                }}
            }}
        }}
        """

        variables: dict[str, Any] = {"first": first}
        if after:
            variables["after"] = after

        return self._make_request(query, variables)

    def get_issue_by_id(self, issue_id: str) -> dict[str, Any]:
        """Get a specific issue by UUID."""
        issues_data = self.get_issues_by_ids([issue_id])
        return issues_data.get(issue_id, {})

    @rate_limited()
    def get_issue_by_identifier(self, identifier: str) -> dict[str, Any]:
        """Get a specific issue by human-readable identifier (e.g., 'ENG-123').

        Args:
            identifier: Human-readable issue identifier (e.g., 'ENG-123', 'PROD-456')

        Returns:
            Issue data dict or empty dict if not found
        """
        query = f"""
        query {{
            issue(id: "{identifier}") {{
                id
                identifier
                title
                description
                priority
                estimate
                url
                createdAt
                updatedAt
                completedAt
                canceledAt
                archivedAt
                assignee {{
                    id
                    name
                    email
                }}
                creator {{
                    id
                    name
                    email
                }}
                team {{
                    id
                    name
                    key
                    private
                }}
                state {{
                    id
                    name
                    type
                }}
                project {{
                    id
                    name
                }}
                labels {{
                    nodes {{
                        id
                        name
                        color
                    }}
                }}
            }}
        }}
        """

        result = self._make_request(query)
        return result.get("issue") or {}

    @rate_limited()
    def get_issues_by_ids(self, issue_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Get multiple issues by their IDs in a single request."""
        if not issue_ids:
            return {}

        # Build OR filter for multiple issue IDs
        or_conditions = [f'{{ id: {{ eq: "{issue_id}" }} }}' for issue_id in issue_ids]
        filter_str = f"filter: {{ or: [{', '.join(or_conditions)}] }}"

        query = f"""
        query {{
            issues({filter_str}) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    priority
                    estimate
                    url
                    createdAt
                    updatedAt
                    completedAt
                    canceledAt
                    archivedAt
                    assignee {{
                        id
                        name
                        email
                    }}
                    creator {{
                        id
                        name
                        email
                    }}
                    team {{
                        id
                        name
                        key
                        private
                    }}
                    state {{
                        id
                        name
                        type
                    }}
                    project {{
                        id
                        name
                    }}
                    labels {{
                        nodes {{
                            id
                            name
                            color
                        }}
                    }}
                }}
            }}
        }}
        """

        result = self._make_request(query)
        issues = result.get("issues", {}).get("nodes", [])

        # Convert to dict keyed by issue ID for easy lookup
        return {issue["id"]: issue for issue in issues if issue.get("id")}

    @rate_limited()
    def get_issue_comments(
        self, issue_id: str, first: int = 100, after: str | None = None
    ) -> dict[str, Any]:
        """Get comments for an issue."""
        query = """
        query($issueId: String!, $first: Int, $after: String) {
            issue(id: $issueId) {
                comments(first: $first, after: $after) {
                    nodes {
                        id
                        body
                        createdAt
                        updatedAt
                        user {
                            id
                            name
                            displayName
                            email
                        }
                        parent {
                            id
                        }
                    }
                    pageInfo {
                        hasNextPage
                        endCursor
                    }
                }
            }
        }
        """

        variables = {"issueId": issue_id, "first": first}
        if after:
            variables["after"] = after

        result = self._make_request(query, variables)
        issue_data = result.get("issue", {})
        return issue_data.get("comments", {})

    def create_issue(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a new issue.

        Args:
            input_data: Issue creation data (e.g., {"title": "...", "teamId": "...", "description": "..."}).
        """
        query = """
        mutation IssueCreate($input: IssueCreateInput!) {
            issueCreate(input: $input) {
                issue {
                    id
                    identifier
                    title
                    url
                    state {
                        id
                        name
                        type
                    }
                    assignee {
                        id
                        name
                    }
                    priority
                }
                success
            }
        }
        """
        variables = {"input": input_data}
        result = self._make_request(query, variables)
        return result.get("issueCreate", {})

    def update_issue(self, issue_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Update an issue.

        Args:
            issue_id: The ID of the issue to update.
            input_data: The fields to update (e.g., {"stateId": "..."}).
        """
        query = """
        mutation IssueUpdate($id: String!, $input: IssueUpdateInput!) {
            issueUpdate(id: $id, input: $input) {
                issue {
                    id
                    identifier
                    title
                    state {
                        id
                        name
                        type
                    }
                    assignee {
                        id
                        name
                    }
                    priority
                }
                success
            }
        }
        """
        variables = {"id": issue_id, "input": input_data}
        result = self._make_request(query, variables)
        return result.get("issueUpdate", {})

    def get_team_states(self, team_id: str) -> list[dict[str, Any]]:
        """Get workflow states for a team."""
        query = """
        query($teamId: String!) {
            team(id: $teamId) {
                states {
                    nodes {
                        id
                        name
                        type
                    }
                }
            }
        }
        """
        variables = {"teamId": team_id}
        result = self._make_request(query, variables)
        return result.get("team", {}).get("states", {}).get("nodes", [])

    @rate_limited()
    def get_team_by_key(self, team_key: str) -> dict[str, Any]:
        """Get a team by its short key (e.g., 'ENG', 'PROD').

        Args:
            team_key: Short team key/identifier (e.g., 'PROD', 'ENG')

        Returns:
            Team data dict with id, name, key or empty dict if not found
        """
        query = """
        query($key: String!) {
            teams(filter: { key: { eq: $key } }) {
                nodes {
                    id
                    name
                    key
                }
            }
        }
        """
        variables = {"key": team_key}
        result = self._make_request(query, variables)
        teams = result.get("teams", {}).get("nodes", [])
        return teams[0] if teams else {}

    @rate_limited()
    def get_user_by_email(self, email: str) -> dict[str, Any]:
        """Get a user by email address.

        Args:
            email: Email address of the user

        Returns:
            User data dict with id, name, email or empty dict if not found
        """
        query = """
        query($email: String!) {
            users(filter: { email: { eq: $email } }) {
                nodes {
                    id
                    name
                    email
                }
            }
        }
        """
        variables = {"email": email}
        result = self._make_request(query, variables)
        users = result.get("users", {}).get("nodes", [])
        return users[0] if users else {}

    def create_issue_relation(
        self, issue_id: str, related_issue_id: str, relation_type: str = "related"
    ) -> dict[str, Any]:
        """Create a relation between two issues.

        Args:
            issue_id: The issue to add the relation to
            related_issue_id: The related issue
            relation_type: Type of relation (e.g., 'related', 'blocks', 'blocked_by')

        Returns:
            Mutation result
        """
        query = """
        mutation IssueRelationCreate($input: IssueRelationCreateInput!) {
            issueRelationCreate(input: $input) {
                issueRelation {
                    id
                    type
                }
                success
            }
        }
        """
        variables = {
            "input": {
                "issueId": issue_id,
                "relatedIssueId": related_issue_id,
                "type": relation_type,
            }
        }
        result = self._make_request(query, variables)
        return result.get("issueRelationCreate", {})

    def get_all_issue_ids(
        self,
        team_id: str | None = None,
        include_archived: bool = True,
    ) -> Iterator[str]:
        """
        Get all issue IDs, handling pagination automatically.

        Args:
            team_id: Optional team ID to filter issues
            include_archived: Whether to include archived issues (default True)
        """
        after = None

        while True:
            response = self.get_issue_ids(
                team_id=team_id,
                first=250,  # fetching more per request reduces # of requests, but increases risk of hitting per-query complexity limits
                after=after,
                include_archived=include_archived,
            )

            issues = response.get("issues", {})
            nodes = issues.get("nodes", [])

            yield from [node.get("id") for node in nodes]

            page_info = issues.get("pageInfo", {})
            if not page_info.get("hasNextPage", False):
                break

            after = page_info.get("endCursor")

    def get_all_issue_comments(self, issue_id: str) -> list[dict[str, Any]]:
        """
        Get all comments for an issue, handling pagination.
        """
        comments: list[dict[str, Any]] = []
        after = None

        while True:
            response = self.get_issue_comments(issue_id, first=100, after=after)

            # Handle case where response might be None or empty
            if not response or not isinstance(response, dict):
                break

            nodes = response.get("nodes", [])
            if nodes:
                comments.extend(n for n in nodes if n is not None)

            page_info = response.get("pageInfo", {})
            if not page_info.get("hasNextPage", False):
                break

            after = page_info.get("endCursor")

        return comments
