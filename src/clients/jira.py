import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from pydantic import BaseModel

from src.utils.logging import get_logger

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)


class JiraProject(BaseModel):
    id: str
    key: str
    name: str


class JiraIssueType(BaseModel):
    id: str
    name: str


class JiraClient:
    """A client for interacting with the Jira REST API via Atlassian API Gateway."""

    def __init__(self, forge_oauth_token: str, cloud_id: str | None = None):
        if not forge_oauth_token:
            raise ValueError("Jira Forge OAuth token is required and cannot be empty")

        self.api_base_url = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3/"

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {forge_oauth_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    @rate_limited(max_retries=5, base_delay=1)  # Conservative rate limit with backoff
    def _make_request(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a REST API request to the Jira API."""
        url = urljoin(self.api_base_url, endpoint)

        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()

            return response.json()

        except requests.exceptions.HTTPError as e:
            # Log the full error response for debugging
            error_body = ""
            try:
                error_body = e.response.text
                logger.error(f"Jira API error response body: {error_body}")
            except Exception:
                logger.error("Could not read error response body")

            if e.response.status_code == 429:
                # Handle rate limiting
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning(f"Jira API rate limited, retry after {retry_after}s")
                raise RateLimitedError(retry_after)
            elif e.response.status_code == 401:
                logger.error(
                    f"Jira API authentication failed - Status: {e.response.status_code}, Error: {error_body}"
                )
                raise ValueError("Invalid Jira credentials")
            elif e.response.status_code == 403:
                logger.error(
                    f"Jira API access forbidden - Status: {e.response.status_code}, Error: {error_body}"
                )
                raise ValueError("Insufficient Jira permissions")
            else:
                logger.error(
                    f"Jira API request failed - Status: {e.response.status_code}, Error: {error_body}"
                )
                raise

        except requests.exceptions.RequestException as e:
            logger.error(f"Jira API request error: {e}")
            raise

    def get_projects(self) -> list[JiraProject]:
        """Get all projects the user has access to."""
        try:
            data = self._make_request("project", params={"expand": "description"})
            return [
                JiraProject(id=project["id"], key=project["key"], name=project["name"])
                for project in data
            ]
        except Exception as e:
            logger.error(f"Failed to fetch Jira projects: {e}")
            raise

    def get_issue(self, issue_key: str) -> dict[str, Any] | None:
        """Get a single issue by its key."""
        try:
            # Expand to get comments only
            params = {"expand": "comments"}
            response = self._make_request(f"issue/{issue_key}", params=params)

            # Additional validation to ensure we got valid data
            if response is None:
                logger.warning(f"Jira issue {issue_key} returned null response")
                return None

            return response
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Jira issue {issue_key} not found")
                return None
            elif e.response.status_code == 403:
                logger.warning(f"Jira issue {issue_key} access forbidden")
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to fetch Jira issue {issue_key}: {e}")
            raise

    def get_project_issues(
        self, project_key: str, cursor: str | None = None, limit: int = 250
    ) -> dict[str, Any]:
        """Get issues from a specific project with cursor-based pagination and comments expanded."""
        try:
            jql = f"project = {project_key} ORDER BY created DESC"
            params: dict[str, Any] = {
                "jql": jql,
                "maxResults": limit,
                "fields": "key,summary,created,updated,status,assignee,reporter,comment,description,priority,project",
            }

            if cursor:
                params["nextPageToken"] = cursor

            return self._make_request("search/jql", params=params)
        except Exception as e:
            logger.error(f"Failed to fetch issues for project {project_key}: {e}")
            raise

    def search_issues(
        self,
        jql: str,
        start_at: int = 0,
        max_results: int = 50,
        expand: str = "comments",
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search for issues using JQL."""
        try:
            params = {"jql": jql, "startAt": start_at, "maxResults": max_results}

            if expand:
                params["expand"] = expand

            if fields:
                params["fields"] = ",".join(fields)

            return self._make_request("search/jql", params=params)
        except Exception as e:
            logger.error(f"Failed to search Jira issues with JQL '{jql}': {e}")
            raise

    def get_all_issues(self, project_keys: list[str] | None = None) -> list[str]:
        """Get all issue keys, optionally filtered by projects."""
        try:
            issue_keys = []
            start_at = 0
            max_results = 100

            # Build JQL query
            if project_keys:
                project_filter = " OR ".join(f"project = {key}" for key in project_keys)
                jql = f"({project_filter}) ORDER BY created DESC"
            else:
                jql = "ORDER BY created DESC"

            while True:
                response = self.search_issues(
                    jql=jql,
                    start_at=start_at,
                    max_results=max_results,
                    expand="",  # Don't expand for key-only search
                    fields=["key"],  # Only request the key field
                )

                issues = response.get("issues", [])
                if not issues:
                    break

                # Extract issue keys
                issue_keys.extend([issue["key"] for issue in issues])

                # Check if we've reached the end using isLast
                if response.get("isLast", True):
                    break

                start_at += max_results

            logger.info(f"Found {len(issue_keys)} Jira issues")
            return issue_keys

        except Exception as e:
            logger.error(f"Failed to fetch all Jira issues: {e}")
            raise

    async def get_site_domain(self, tenant_id: str, extractor) -> str:
        """Get the Jira site domain from the configured JIRA_SITE_URL."""
        try:
            # Get the configured Jira site URL
            jira_site_url = await extractor.get_tenant_config_value("JIRA_SITE_URL", tenant_id)
            if jira_site_url:
                # Extract domain from the full URL (e.g., "https://company.atlassian.net" -> "company.atlassian.net")
                from urllib.parse import urlparse

                parsed_url = urlparse(jira_site_url)
                return parsed_url.netloc
            else:
                # Fallback to extracting from API URL if site URL not configured
                import re

                match = re.search(r"/ex/jira/([^/]+)/", self.api_base_url)
                if match:
                    return match.group(1)
                else:
                    # Last resort fallback
                    return (
                        self.api_base_url.split("/")[4]
                        if len(self.api_base_url.split("/")) > 4
                        else "unknown"
                    )
        except Exception:
            # If anything fails, fallback to the old method
            import re

            match = re.search(r"/ex/jira/([^/]+)/", self.api_base_url)
            if match:
                return match.group(1)
            else:
                return (
                    self.api_base_url.split("/")[4]
                    if len(self.api_base_url.split("/")) > 4
                    else "unknown"
                )
