from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from typing import Any

import httpx
from aiolimiter import AsyncLimiter

from connectors.asana.client.asana_api_errors import (
    AsanaApiInvalidSyncTokenError,
    AsanaApiPaymentRequiredError,
    AsanaApiServiceAccountOnlyError,
)
from connectors.asana.client.asana_api_models import (
    AsanaEvent,
    AsanaEventListErrorRes,
    AsanaEventListRes,
    AsanaListRes,
    AsanaProject,
    AsanaProjectListRes,
    AsanaStory,
    AsanaStoryListRes,
    AsanaTask,
    AsanaTaskSearchRes,
    AsanaWorkspace,
    AsanaWorkspaceListRes,
    asana_resource_set_difference,
)
from connectors.asana.client.asana_oauth_token_models import AsanaOauthTokenRes
from connectors.asana.client.asana_permissions_models import (
    AsanaProjectMembership,
    AsanaProjectMembershipListRes,
    AsanaTeamMembership,
    AsanaTeamMembershipListRes,
)
from src.utils.config import require_config_value
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)

# https://developers.asana.com/docs/rate-limits#concurrent-request-limits
# Max concurrent requests is 50, lets undershoot a bit.
_asana_connection_limits = httpx.Limits(
    max_connections=15,
    max_keepalive_connections=15,
)


@dataclass
class AsanaLimiters:
    tenant_id: str
    general: AsyncLimiter
    search: AsyncLimiter


# https://developers.asana.com/docs/rate-limits#standard-rate-limits
# Standard rate limit is 1500 requests per minute, lets undershoot a bit.
# Search rate limit is 60 requests per minute, lets undershoot a bit.
# Note: these are tuned so that full backfill and incremental backfill can execute concurrently.
# a better approach might be to increase these limits but control concurrency between workers.
@cache
def _get_limiters(tenant_id: str) -> AsanaLimiters:
    return AsanaLimiters(
        tenant_id=tenant_id,
        # 600 req / min no bursting
        general=AsyncLimiter(1, 60 / 600),
        # 20 req / min no bursting, we likely don't hit this limit anyways because processing search pages takes a while.
        search=AsyncLimiter(1, 60 / 20),
    )


class AsanaClient:
    def __init__(self, access_token: str | None, tenant_id: str):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        self._client = httpx.AsyncClient(
            base_url="https://app.asana.com/api/1.0",
            headers=headers,
            limits=_asana_connection_limits,
            timeout=httpx.Timeout(5, read=30, pool=30),
        )

        self._limiters = _get_limiters(tenant_id)

    async def __aenter__(self) -> "AsanaClient":
        return self

    async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        await self._client.aclose()

    async def oauth_refresh(self, refresh_token: str) -> AsanaOauthTokenRes:
        client_id = require_config_value("ASANA_CLIENT_ID")
        client_secret = require_config_value("ASANA_CLIENT_SECRET")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        }

        async with self._limiters.general:
            response = await self._client.post(
                "https://app.asana.com/-/oauth_token",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data=data,
            )
        response.raise_for_status()
        return AsanaOauthTokenRes.model_validate(response.json())

    @rate_limited()
    async def _get(self, path: str, params: dict[str, str]) -> httpx.Response:
        async with self._limiters.general:
            try:
                response = await self._client.get(path, params=params)
            except httpx.TimeoutException as e:
                msg = f"Asana {type(e).__name__}, retrying in 10 seconds: {e.request.url}"
                logger.warning(msg)
                raise RateLimitedError(message=msg, retry_after=10) from e

        if response.is_server_error:
            msg = f"Asana server error {response.status_code}, retrying in 10 seconds: {response.request.url}"
            logger.warning(msg)
            raise RateLimitedError(message=msg, retry_after=10)

        if response.status_code == httpx.codes.TOO_MANY_REQUESTS.value:
            retry_after: str | None = response.headers.get("Retry-After")
            retry_after_int = int(retry_after) if retry_after else None
            raise RateLimitedError(retry_after_int)

        response.raise_for_status()
        return response

    # Add additional rate limiting for search endpoint
    async def _search(self, path: str, params: dict[str, str]) -> httpx.Response:
        async with self._limiters.search:
            try:
                return await self._get(path, params=params)
            except httpx.HTTPStatusError as e:
                # Search is a paid feature, supporting only paying Asana workspaces is reasonable.
                if e.response.status_code == httpx.codes.PAYMENT_REQUIRED.value:
                    raise AsanaApiPaymentRequiredError(
                        "Search is only available to premium users."
                    ) from e

                raise

    async def _list_events(
        self, path: str, sync_token: str | None
    ) -> AsyncIterator[AsanaEventListRes]:
        params: dict[str, str] = {
            "opt_fields": ",".join(AsanaEvent.get_opt_fields()),
        }
        if sync_token:
            params["sync"] = sync_token

        while True:
            try:
                response = await self._get(path, params)
            except httpx.HTTPStatusError as e:
                if e.response.is_client_error:
                    data: dict[str, Any] = e.response.json()
                    error_codes: list[str | None] = [
                        error.get("error") for error in data.get("errors", [])
                    ]

                    # Fetching a sync token for the first time or after a 4+ hour gap results in a 400
                    # error with a new sync token. Let the caller handle this special case by catching
                    # the AsanaApiInvalidSyncTokenError.
                    if "sync" in data:
                        raise AsanaApiInvalidSyncTokenError(
                            AsanaEventListErrorRes.model_validate(data)
                        ) from e

                    # Fetching workspace events with an oauth token results in this error.
                    if "only_service_account_can_access" in error_codes:
                        raise AsanaApiServiceAccountOnlyError(
                            "The Asana API returned an error indicating that only service accounts can access the requested resource."
                        ) from e
                raise

            page = AsanaEventListRes.model_validate(response.json())

            yield page

            if page.has_more and page.sync:
                params["sync"] = page.sync
            else:
                break

    async def _list_pages[T: AsanaListRes[Any]](
        self, page_class: type[T], path: str, params_arg: dict[str, str]
    ) -> AsyncIterator[T]:
        params = params_arg.copy()

        while True:
            response = await self._get(path, params)
            page = page_class.model_validate(response.json())

            yield page

            if page.next_page and page.next_page.offset:
                params["offset"] = page.next_page.offset
            else:
                break

    async def get_workspace(self, workspace_gid: str) -> AsanaWorkspace:
        params: dict[str, str] = {
            "opt_fields": ",".join(AsanaWorkspace.get_opt_fields()),
        }

        response = await self._get(f"/workspaces/{workspace_gid}", params)
        return AsanaWorkspace.model_validate(response.json()["data"])

    async def get_task(self, task_gid: str) -> AsanaTask:
        params: dict[str, str] = {
            "opt_fields": ",".join(AsanaTask.get_opt_fields()),
        }

        response = await self._get(f"/tasks/{task_gid}", params)
        return AsanaTask.model_validate(response.json()["data"])

    async def list_workspaces(self) -> AsyncIterator[AsanaWorkspaceListRes]:
        initial_params: dict[str, str] = {
            "limit": "100",
            "opt_fields": ",".join(AsanaWorkspace.get_opt_fields()),
        }

        async for page in self._list_pages(AsanaWorkspaceListRes, "/workspaces", initial_params):
            yield page

    async def list_projects(self, workspace_gid: str) -> AsyncIterator[AsanaProjectListRes]:
        path = f"/workspaces/{workspace_gid}/projects"
        initial_params: dict[str, str] = {
            "limit": "100",
            "opt_fields": ",".join(AsanaProject.get_opt_fields()),
        }

        async for page in self._list_pages(AsanaProjectListRes, path, initial_params):
            yield page

    async def search_tasks(
        self,
        workspace_gid: str,
        initial_modified_at_before: datetime | None = None,
        modified_at_after: datetime | None = None,
        project_gid: str | None = None,
    ) -> AsyncIterator[AsanaTaskSearchRes]:
        path = f"/workspaces/{workspace_gid}/tasks/search"

        params: dict[str, str] = {
            "limit": "100",
            "sort_by": "modified_at",
            "sort_ascending": "false",
            "opt_fields": ",".join(AsanaTask.get_opt_fields()),
        }

        if initial_modified_at_before:
            params["modified_at.before"] = initial_modified_at_before.isoformat()
        else:
            params["modified_at.before"] = datetime.now(UTC).isoformat()

        if modified_at_after:
            params["modified_at.after"] = modified_at_after.isoformat()
        if project_gid:
            params["projects.any"] = project_gid

        previous_page: AsanaTaskSearchRes | None = None
        while True:
            response = await self._search(path, params)
            page = AsanaTaskSearchRes.model_validate(response.json())

            # Nothing more returned, we are done!
            if not page.data:
                break

            # Remove tasks that were present in the previous page to avoid duplicates with same modified_at over page boundaries
            page.data = asana_resource_set_difference(
                page.data, previous_page.data if previous_page else []
            )

            # All tasks in this page were duplicates (happens if more than 100 tasks with the same
            # modified_at down to the ms), Nothing to yield, continue to next page by decrementing
            # modified_at.before (exclusive and respects 1 ms granularity), clear previous_tasks.
            if not page.data:
                prev_modified_at_before = datetime.fromisoformat(params["modified_at.before"])
                next_modified_at_before = prev_modified_at_before - timedelta(milliseconds=1)
                params["modified_at.before"] = next_modified_at_before.isoformat()
                previous_page = None
                continue

            # Bump modified_at.before by 1 ms (exclusive and respects 1 ms granularity) to avoid
            # skipping tasks with the same modified_at hiding in the next "page". This will result
            # in at least 1 dupe, so track previous page data and remove dupes.
            last_task = page.data[-1]
            next_modified_at_before = datetime.fromisoformat(last_task.modified_at) + timedelta(
                milliseconds=1
            )
            params["modified_at.before"] = next_modified_at_before.isoformat()

            previous_page = page
            yield page

    async def list_stories(self, task_gid: str) -> AsyncIterator[AsanaStoryListRes]:
        initial_params: dict[str, str] = {
            "limit": "100",
            "opt_fields": ",".join(AsanaStory.get_opt_fields()),
        }

        async for page in self._list_pages(
            AsanaStoryListRes, f"/tasks/{task_gid}/stories", initial_params
        ):
            yield page

    async def list_project_memberships(
        self, project_gid: str
    ) -> AsyncIterator[AsanaProjectMembershipListRes]:
        initial_params: dict[str, str] = {
            "limit": "100",
            "opt_fields": ",".join(AsanaProjectMembership.get_opt_fields()),
            "parent": project_gid,
        }

        async for page in self._list_pages(
            AsanaProjectMembershipListRes, "/memberships", initial_params
        ):
            yield page

    async def list_team_memberships(
        self, team_gid: str
    ) -> AsyncIterator[AsanaTeamMembershipListRes]:
        initial_params: dict[str, str] = {
            "limit": "100",
            "opt_fields": ",".join(AsanaTeamMembership.get_opt_fields()),
        }

        async for page in self._list_pages(
            AsanaTeamMembershipListRes, f"/teams/{team_gid}/team_memberships", initial_params
        ):
            yield page

    async def list_workspace_events(
        self, workspace_gid: str, sync_token: str | None
    ) -> AsyncIterator[AsanaEventListRes]:
        async for page in self._list_events(f"/workspaces/{workspace_gid}/events", sync_token):
            yield page

    async def list_project_events(
        self, project_gid: str, sync_token: str | None
    ) -> AsyncIterator[AsanaEventListRes]:
        async for page in self._list_events(f"/projects/{project_gid}/events", sync_token):
            yield page
