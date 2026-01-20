"""
Teamwork API client for project and task management operations.

Based on Teamwork REST API v3:
- API Docs: https://apidocs.teamwork.com/docs/teamwork

Rate limits:
- 150 requests per minute per user (Premium+)
- 30 requests per minute (free tier)

Pagination:
- Page-based pagination with `page` and `pageSize` parameters
- Default pageSize is 50, max is 250

OAuth:
- Authorization: https://www.teamwork.com/launchpad/login/
- Token exchange: https://www.teamwork.com/launchpad/v1/token.json
- Access tokens are long-lived (no refresh needed)
"""

import contextlib
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import requests
from pydantic import BaseModel

from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited
from src.utils.tenant_config import get_tenant_config_value

logger = get_logger(__name__)

# Teamwork API configuration
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 250

# Default includes for batch task fetching - get all related data in one call
DEFAULT_TASK_INCLUDES = [
    "projects",
    "tasklists",
    "tags",
    "comments",
    "attachments",
    "users",
    "parentTasks",
]

# Fields to request for tasks - explicitly include isPrivate for privacy filtering
# When not specified, V3 API returns all fields, but we explicitly request to be safe
# Note: Include both ID fields (projectId) AND relationship fields (project) for enrichment
DEFAULT_TASK_FIELDS = [
    "id",
    "name",
    "description",
    "status",
    "priority",
    "progress",
    "startDate",
    "dueDate",
    "createdAt",
    "updatedAt",
    "completedAt",
    "completed",  # Boolean for task completion status
    "isPrivate",  # Critical for privacy filtering
    "estimatedMinutes",
    # Relationship fields needed for enrich_tasks_with_included()
    "project",
    "taskList",
    "parentTask",
    "createdBy",
    "assignees",
    "tags",
]


class TeamworkSearchResult(BaseModel):
    """Result from a Teamwork list/query operation."""

    items: list[dict[str, Any]]
    next_page: int | None = None
    total_items: int | None = None


class TeamworkClient:
    """A client for interacting with the Teamwork REST API.

    Teamwork uses OAuth 2.0 with long-lived access tokens (no refresh needed).
    The api_domain is instance-specific (e.g., https://yourcompany.teamwork.com).

    Rate limits are per-user with minute-based windows.
    """

    def __init__(self, access_token: str, api_domain: str):
        """Initialize the Teamwork client.

        Args:
            access_token: OAuth access token
            api_domain: Company-specific API domain (e.g., https://company.teamwork.com)
        """
        if not access_token:
            raise ValueError("Teamwork access token is required and cannot be empty")
        if not api_domain:
            raise ValueError("Teamwork API domain is required and cannot be empty")

        self.api_domain = api_domain.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
        )

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> dict[str, Any]:
        """Make a request to the Teamwork API.

        Args:
            endpoint: API endpoint path (e.g., "/projects/api/v3/tasks")
            method: HTTP method (GET, POST)
            params: Optional query parameters
            json_body: Optional JSON body for POST requests
            resource_type: Optional resource type for 404 handling
            resource_id: Optional resource ID for 404 handling

        Returns:
            API response as dict

        Raises:
            RateLimitedError: When rate limited by Teamwork
            requests.exceptions.HTTPError: For other HTTP errors
        """
        url = f"{self.api_domain}{endpoint}"

        try:
            if method == "GET":
                response = self.session.get(url, params=params, timeout=30.0)
            elif method == "POST":
                response = self.session.post(url, params=params, json=json_body, timeout=30.0)
            elif method == "DELETE":
                response = self.session.delete(url, params=params, timeout=30.0)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Check for rate limiting (429)
            if response.status_code == 429:
                retry_after_str = response.headers.get("Retry-After")
                retry_after: float = 60.0  # Default to 1 minute for Teamwork
                if retry_after_str:
                    with contextlib.suppress(ValueError):
                        retry_after = float(retry_after_str)
                logger.warning("Teamwork API rate limit hit")
                raise RateLimitedError(
                    retry_after=retry_after, message="Teamwork rate limit exceeded"
                )

            # Check for not found (404)
            if response.status_code == 404:
                if resource_type and resource_id:
                    logger.warning(f"Teamwork {resource_type} {resource_id} not found")
                response.raise_for_status()

            # Check for unauthorized (401)
            if response.status_code == 401:
                logger.error("Teamwork API unauthorized - invalid or expired access token")
                response.raise_for_status()

            response.raise_for_status()

            # Handle empty responses
            if not response.content:
                return {}

            return response.json()

        except RateLimitedError:
            raise
        except requests.exceptions.HTTPError:
            logger.error(f"Teamwork API HTTP error: {response.status_code} - {response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Teamwork API request error: {e}")
            raise

    # =========================================================================
    # Tasks API
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_tasks(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        updated_after: datetime | None = None,
        include_completed: bool = True,
        include_deleted: bool = False,
    ) -> TeamworkSearchResult:
        """Get tasks with page-based pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Maximum tasks per page (default 100, max 250)
            updated_after: Filter for tasks updated after this time
            include_completed: Whether to include completed tasks
            include_deleted: Whether to include deleted tasks

        Returns:
            TeamworkSearchResult with tasks and pagination info
        """
        params: dict[str, Any] = {
            "page": page,
            "pageSize": min(page_size, MAX_PAGE_SIZE),
            "includeCompletedTasks": str(include_completed).lower(),
            # Explicitly request fields including isPrivate for privacy filtering
            "fields[tasks]": ",".join(DEFAULT_TASK_FIELDS),
        }

        if updated_after:
            # Teamwork expects ISO 8601 format
            params["updatedAfter"] = updated_after.strftime("%Y-%m-%dT%H:%M:%SZ")

        if include_deleted:
            params["includeDeletedTasks"] = "true"

        response = self._make_request("/projects/api/v3/tasks", params=params)

        tasks = response.get("tasks") or []
        meta = response.get("meta", {})
        page_info = meta.get("page", {})

        # Determine if there are more pages
        total_items = page_info.get("count")
        has_more = page_info.get("hasMore", False)
        next_page = page + 1 if has_more else None

        logger.debug(f"Retrieved {len(tasks)} tasks (page {page})")

        return TeamworkSearchResult(
            items=tasks,
            next_page=next_page,
            total_items=total_items,
        )

    def iterate_tasks(
        self,
        page_size: int = DEFAULT_PAGE_SIZE,
        start_page: int = 1,
        updated_after: datetime | None = None,
        include_completed: bool = True,
        include_deleted: bool = False,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all tasks.

        Yields pages of tasks until exhausted.

        Args:
            page_size: Tasks per page
            start_page: Page to start from (1-indexed)
            updated_after: Filter for tasks updated after this time
            include_completed: Whether to include completed tasks
            include_deleted: Whether to include deleted tasks

        Yields:
            Lists of task dictionaries
        """
        page = start_page

        while True:
            result = self.get_tasks(
                page=page,
                page_size=page_size,
                updated_after=updated_after,
                include_completed=include_completed,
                include_deleted=include_deleted,
            )

            if result.items:
                yield result.items

            if not result.next_page:
                break

            page = result.next_page

    def iterate_tasks_with_page(
        self,
        page_size: int = DEFAULT_PAGE_SIZE,
        start_page: int = 1,
        updated_after: datetime | None = None,
        include_completed: bool = True,
        include_deleted: bool = False,
    ) -> Iterator[tuple[list[dict[str, Any]], int | None]]:
        """Iterate through all tasks, yielding tasks with next page info.

        Similar to iterate_tasks but yields tuples of (tasks, next_page) allowing
        callers to save progress for resumable backfills.
        """
        page = start_page

        while True:
            result = self.get_tasks(
                page=page,
                page_size=page_size,
                updated_after=updated_after,
                include_completed=include_completed,
                include_deleted=include_deleted,
            )

            if result.items:
                yield result.items, result.next_page

            if not result.next_page:
                break

            page = result.next_page

    @rate_limited(max_retries=5, base_delay=2)
    def get_task(self, task_id: int) -> dict[str, Any] | None:
        """Get a single task by ID.

        Args:
            task_id: The task ID

        Returns:
            Task data dictionary or None if not found
        """
        try:
            response = self._make_request(
                f"/projects/api/v3/tasks/{task_id}",
                resource_type="task",
                resource_id=str(task_id),
            )
            return response.get("task")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    @rate_limited(max_retries=5, base_delay=2)
    def get_tasks_by_ids(
        self,
        task_ids: list[int],
        includes: list[str] | None = None,
    ) -> dict[str, Any]:
        """Batch fetch multiple tasks by their IDs with optional related data.

        This method uses the v3 API's `ids` parameter to fetch multiple tasks
        in a single request, significantly reducing API calls and rate limit issues.

        Args:
            task_ids: List of task IDs to fetch
            includes: List of related data to include. If None, uses DEFAULT_TASK_INCLUDES.
                     Options: projects, tasklists, tags, comments, attachments, users, parentTasks

        Returns:
            Dict containing:
                - tasks: List of task dictionaries
                - included: Dict of related data keyed by type (projects, users, etc.)
                  Each value is a dict mapping ID to the related object for easy lookup.

        Example response structure:
            {
                "tasks": [...],
                "included": {
                    "projects": {123: {...}, 456: {...}},
                    "users": {789: {...}},
                    "tags": {111: {...}},
                    ...
                }
            }
        """
        if not task_ids:
            return {"tasks": [], "included": {}}

        if includes is None:
            includes = DEFAULT_TASK_INCLUDES

        params: dict[str, Any] = {
            "ids": ",".join(str(tid) for tid in task_ids),
            # Explicitly request fields including isPrivate for privacy filtering
            "fields[tasks]": ",".join(DEFAULT_TASK_FIELDS),
        }

        if includes:
            params["include"] = ",".join(includes)

        response = self._make_request("/projects/api/v3/tasks", params=params)

        tasks = response.get("tasks") or []

        # Parse the included data into ID-keyed dictionaries for easy lookup
        included_raw = response.get("included", {})
        included: dict[str, dict[int, dict[str, Any]]] = {}

        for include_type, items in included_raw.items():
            if isinstance(items, list):
                included[include_type] = {item["id"]: item for item in items if "id" in item}
            elif isinstance(items, dict):
                # Some includes might already be keyed by ID
                included[include_type] = items

        logger.info(
            f"Batch fetched {len(tasks)} tasks with includes",
            requested_count=len(task_ids),
            fetched_count=len(tasks),
            includes=list(included.keys()),
        )

        return {"tasks": tasks, "included": included}

    def enrich_tasks_with_included(
        self,
        tasks: list[dict[str, Any]],
        included: dict[str, dict[int, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Enrich tasks with their related included data.

        Takes the batch response and merges related data directly into task objects
        for easier consumption by extractors.

        Args:
            tasks: List of task dictionaries from get_tasks_by_ids
            included: The included data dict from get_tasks_by_ids

        Returns:
            List of tasks with related data merged in as:
                - _project: Full project object
                - _tasklist: Full tasklist object
                - _assignees: List of full user objects
                - _creator: Full user object
                - _tags: List of full tag objects
                - _comments: List of full comment objects
                - _attachments: List of full attachment objects
                - _parentTask: Full parent task object (for subtasks)
        """
        projects = included.get("projects", {})
        tasklists = included.get("tasklists", {})
        users = included.get("users", {})
        tags = included.get("tags", {})
        comments = included.get("comments", {})
        attachments = included.get("attachments", {})
        parent_tasks = included.get("parentTasks", {})

        def extract_id(value: Any) -> int | None:
            """Extract ID from a value that can be int, dict with 'id', or None."""
            if value is None:
                return None
            if isinstance(value, int):
                return value
            if isinstance(value, dict):
                return value.get("id")
            return None

        enriched_tasks = []
        for task in tasks:
            enriched = task.copy()

            # Enrich project (can be int ID or dict with id)
            project_id = extract_id(task.get("project"))
            if project_id and project_id in projects:
                enriched["_project"] = projects[project_id]

            # Enrich tasklist (can be int ID or dict with id)
            tasklist_id = extract_id(task.get("taskList"))
            if tasklist_id and tasklist_id in tasklists:
                enriched["_tasklist"] = tasklists[tasklist_id]

            # Enrich assignees (can be list of ints or list of dicts)
            assignees = task.get("assignees", [])
            if assignees and isinstance(assignees, list):
                assignee_ids = [extract_id(a) for a in assignees]
                assignee_ids = [aid for aid in assignee_ids if aid is not None]
                if assignee_ids:
                    enriched["_assignees"] = [users[uid] for uid in assignee_ids if uid in users]

            # Enrich creator (can be int ID or dict with id)
            creator_id = extract_id(task.get("createdBy"))
            if creator_id and creator_id in users:
                enriched["_creator"] = users[creator_id]

            # Enrich tags (can be list of ints or list of dicts)
            task_tags = task.get("tags", [])
            if task_tags and isinstance(task_tags, list):
                tag_ids = [extract_id(t) for t in task_tags]
                tag_ids = [tid for tid in tag_ids if tid is not None]
                if tag_ids:
                    enriched["_tags"] = [tags[tid] for tid in tag_ids if tid in tags]

            # Collect comments for this task
            task_id = task.get("id")
            task_comments = [c for c in comments.values() if extract_id(c.get("task")) == task_id]
            if task_comments:
                enriched["_comments"] = task_comments

            # Collect attachments for this task
            task_attachments = [
                a for a in attachments.values() if extract_id(a.get("task")) == task_id
            ]
            if task_attachments:
                enriched["_attachments"] = task_attachments

            # Enrich parent task (can be int ID or dict with id)
            parent_task_id = extract_id(task.get("parentTask"))
            if parent_task_id and parent_task_id in parent_tasks:
                enriched["_parentTask"] = parent_tasks[parent_task_id]

            enriched_tasks.append(enriched)

        return enriched_tasks

    # =========================================================================
    # Projects API
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_projects(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        include_archived: bool = False,
    ) -> TeamworkSearchResult:
        """Get projects with page-based pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Maximum projects per page (default 100, max 250)
            include_archived: Whether to include archived projects

        Returns:
            TeamworkSearchResult with projects and pagination info
        """
        params: dict[str, Any] = {
            "page": page,
            "pageSize": min(page_size, MAX_PAGE_SIZE),
        }

        if include_archived:
            params["includeArchivedProjects"] = "true"

        response = self._make_request("/projects/api/v3/projects", params=params)

        projects = response.get("projects") or []
        meta = response.get("meta", {})
        page_info = meta.get("page", {})

        has_more = page_info.get("hasMore", False)
        next_page = page + 1 if has_more else None
        total_items = page_info.get("count")

        logger.debug(f"Retrieved {len(projects)} projects (page {page})")

        return TeamworkSearchResult(
            items=projects,
            next_page=next_page,
            total_items=total_items,
        )

    def iterate_projects(
        self,
        page_size: int = DEFAULT_PAGE_SIZE,
        include_archived: bool = False,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all projects."""
        page = 1

        while True:
            result = self.get_projects(
                page=page,
                page_size=page_size,
                include_archived=include_archived,
            )

            if result.items:
                yield result.items

            if not result.next_page:
                break

            page = result.next_page

    @rate_limited(max_retries=5, base_delay=2)
    def get_project(self, project_id: int) -> dict[str, Any] | None:
        """Get a single project by ID.

        Returns:
            Project data dictionary or None if not found
        """
        try:
            response = self._make_request(
                f"/projects/api/v3/projects/{project_id}",
                resource_type="project",
                resource_id=str(project_id),
            )
            return response.get("project")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    # =========================================================================
    # Users API
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_users(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> TeamworkSearchResult:
        """Get users with page-based pagination.

        Args:
            page: Page number (1-indexed)
            page_size: Maximum users per page (default 100, max 250)

        Returns:
            TeamworkSearchResult with users and pagination info
        """
        params: dict[str, Any] = {
            "page": page,
            "pageSize": min(page_size, MAX_PAGE_SIZE),
        }

        response = self._make_request("/projects/api/v3/people", params=params)

        people = response.get("people") or []
        meta = response.get("meta", {})
        page_info = meta.get("page", {})

        has_more = page_info.get("hasMore", False)
        next_page = page + 1 if has_more else None
        total_items = page_info.get("count")

        logger.debug(f"Retrieved {len(people)} users (page {page})")

        return TeamworkSearchResult(
            items=people,
            next_page=next_page,
            total_items=total_items,
        )

    def iterate_users(
        self,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all users."""
        page = 1

        while True:
            result = self.get_users(page=page, page_size=page_size)

            if result.items:
                yield result.items

            if not result.next_page:
                break

            page = result.next_page

    def get_all_users(self) -> list[dict[str, Any]]:
        """Get all users as a flat list.

        Returns:
            List of all user dictionaries
        """
        all_users: list[dict[str, Any]] = []
        for page in self.iterate_users():
            all_users.extend(page)
        return all_users

    @rate_limited(max_retries=5, base_delay=2)
    def get_user(self, user_id: int) -> dict[str, Any] | None:
        """Get a single user by ID.

        Returns:
            User data dictionary or None if not found
        """
        try:
            response = self._make_request(
                f"/projects/api/v3/people/{user_id}",
                resource_type="user",
                resource_id=str(user_id),
            )
            return response.get("person")
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return None
            raise

    # =========================================================================
    # Current User
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user (me).

        Returns:
            Current user data dictionary
        """
        response = self._make_request("/projects/api/v3/me")
        return response.get("person") or {}

    # =========================================================================
    # Comments API (for task comments)
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_task_comments(
        self,
        task_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> TeamworkSearchResult:
        """Get comments for a specific task.

        Args:
            task_id: The task ID
            page: Page number (1-indexed)
            page_size: Maximum comments per page

        Returns:
            TeamworkSearchResult with comments and pagination info
        """
        params: dict[str, Any] = {
            "page": page,
            "pageSize": min(page_size, MAX_PAGE_SIZE),
        }

        response = self._make_request(f"/projects/api/v3/tasks/{task_id}/comments", params=params)

        comments = response.get("comments") or []
        meta = response.get("meta", {})
        page_info = meta.get("page", {})

        has_more = page_info.get("hasMore", False)
        next_page = page + 1 if has_more else None

        logger.debug(f"Retrieved {len(comments)} comments for task {task_id}")

        return TeamworkSearchResult(
            items=comments,
            next_page=next_page,
        )

    def get_all_task_comments(self, task_id: int) -> list[dict[str, Any]]:
        """Get all comments for a specific task.

        Args:
            task_id: The task ID

        Returns:
            List of all comment dictionaries for the task
        """
        all_comments: list[dict[str, Any]] = []
        page = 1

        while True:
            result = self.get_task_comments(task_id=task_id, page=page)
            all_comments.extend(result.items)

            if not result.next_page:
                break

            page = result.next_page

        return all_comments


async def get_teamwork_client_for_tenant(tenant_id: str, ssm_client: SSMClient) -> TeamworkClient:
    """Factory method to get Teamwork client for a tenant.

    Teamwork uses long-lived access tokens, so no refresh flow is needed.

    Args:
        tenant_id: Tenant ID
        ssm_client: SSM client for retrieving secrets

    Returns:
        TeamworkClient configured with valid access token

    Raises:
        ValueError: If credentials are not found for the tenant
    """
    # Get access token from SSM Parameter Store
    access_token = await ssm_client.get_api_key(tenant_id, "TEAMWORK_ACCESS_TOKEN")

    if not access_token:
        raise ValueError(f"No Teamwork access token configured for tenant {tenant_id}")

    # Get API domain from database (non-sensitive config)
    api_domain = await get_tenant_config_value("TEAMWORK_API_DOMAIN", tenant_id)

    if not api_domain:
        raise ValueError(f"No Teamwork API domain configured for tenant {tenant_id}")

    # Log credential source with token redaction
    redacted_token = (
        f"{access_token[:8]}...{access_token[-4:]}" if len(access_token) > 12 else "***"
    )

    logger.info(
        "Teamwork client credentials loaded",
        tenant_id=tenant_id,
        token_preview=redacted_token,
        api_domain=api_domain,
    )

    return TeamworkClient(access_token=access_token, api_domain=api_domain)
