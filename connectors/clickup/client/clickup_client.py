import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from typing import Any

import httpx
from aiolimiter import AsyncLimiter

from connectors.clickup.client.clickup_api_models import (
    ClickupComment,
    ClickupCommentsRes,
    ClickupFoldersRes,
    ClickupListMembersRes,
    ClickupListsRes,
    ClickupListWithFolder,
    ClickupSpace,
    ClickupSpacesRes,
    ClickupTask,
    ClickupTasksRes,
    ClickupUser,
    ClickupWorkspace,
    ClickupWorkspaceRes,
)
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)

_clickup_connection_limits = httpx.Limits(
    max_connections=15,
    max_keepalive_connections=15,
)


@dataclass
class ClickupLimiters:
    tenant_id: str
    general: AsyncLimiter


# https://developer.clickup.com/docs/rate-limits
# Rate limits vary by plan, undershoot by half to be safe:
# - Free Forever, Unlimited, Business: 100 requests per minute per token.
# - Business Plus: 1,000 requests per minute per token.
# - Enterprise: 10,000 requests per minute per token.
@cache
def _get_limiters(tenant_id: str, req_per_minute: int) -> ClickupLimiters:
    half_per_minute = req_per_minute // 2

    return ClickupLimiters(
        tenant_id=tenant_id,
        general=AsyncLimiter(1, 60 / half_per_minute),
    )


class ClickupClient:
    def __init__(self, access_token: str | None, tenant_id: str):
        """Default to lowest tier rate limit. Call setup_rate_limit to get actual rate limit."""

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        self._client = httpx.AsyncClient(
            base_url="https://api.clickup.com/api/v2",
            headers=headers,
            limits=_clickup_connection_limits,
            timeout=httpx.Timeout(5, read=30, pool=30),
        )

        # Default to 100 requests per minute until we can fetch the actual rate limit
        self._limiters = _get_limiters(tenant_id, 100)

    async def __aenter__(self) -> "ClickupClient":
        return self

    async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        await self._client.aclose()

    async def setup_rate_limit(self) -> None:
        """Setup the actual rate limit based on a request to the API"""
        rate_limit = await self._get_rate_limit()
        self._limiters = _get_limiters(self._limiters.tenant_id, rate_limit)

    async def _get_rate_limit(self) -> int:
        """Make a request to get the authorized user and check headers for rate limit info"""
        res = await self._get("/user")
        rate_limit_header = res.headers.get("x-ratelimit-limit")

        try:
            return int(rate_limit_header)
        except (TypeError, ValueError):
            logger.error(
                "Failed to parse rate limit header, defaulting to 100",
                tenant_id=self._limiters.tenant_id,
                rate_limit_header=rate_limit_header,
            )

        return 100

    @rate_limited()
    async def _get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        async with self._limiters.general:
            try:
                response = await self._client.get(path, params=params)
            except httpx.TimeoutException as e:
                msg = f"Clickup {type(e).__name__}, retrying in 10 seconds: {e.request.url}"
                logger.warning(msg)
                raise RateLimitedError(message=msg, retry_after=10) from e

        if response.is_server_error:
            msg = f"Clickup server error {response.status_code}, retrying in 10 seconds: {response.request.url}"
            logger.warning(msg)
            raise RateLimitedError(message=msg, retry_after=10)

        if response.status_code == httpx.codes.TOO_MANY_REQUESTS.value:
            ratelimit_reset_header = response.headers.get("x-ratelimit-reset")

            try:
                rate_limit_reset = int(ratelimit_reset_header) + 1
                retry_after = max(1, rate_limit_reset - datetime.now(UTC).timestamp())
            except (TypeError, ValueError):
                retry_after = 60

            raise RateLimitedError(retry_after)
        response.raise_for_status()
        return response

    async def get_authorized_workspaces(self) -> list[ClickupWorkspace]:
        res = await self._get("/team")
        data = ClickupWorkspaceRes.model_validate(res.json())
        return data.teams

    async def get_spaces(self, workspace_id: str) -> list[ClickupSpace]:
        res = await self._get(f"/team/{workspace_id}/space")
        data = ClickupSpacesRes.model_validate(res.json())
        return data.spaces

    async def get_space(self, space_id: str) -> ClickupSpace:
        res = await self._get(f"/space/{space_id}")
        data = ClickupSpace.model_validate(res.json())
        return data

    async def get_lists(self, space_id: str) -> list[ClickupListWithFolder]:
        async with asyncio.TaskGroup() as tg:
            foldered = tg.create_task(self._get_foldered_lists(space_id))
            folderless = tg.create_task(self._get_folderless_lists(space_id))

        return foldered.result() + folderless.result()

    async def _get_foldered_lists(self, space_id: str) -> list[ClickupListWithFolder]:
        res = await self._get(f"/space/{space_id}/folder")
        data = ClickupFoldersRes.model_validate(res.json())
        return [
            ClickupListWithFolder.from_list_folder(l, folder.to_folder())
            for folder in data.folders
            for l in folder.lists
        ]

    async def _get_folderless_lists(self, space_id: str) -> list[ClickupListWithFolder]:
        res = await self._get(f"/space/{space_id}/list")
        data = ClickupListsRes.model_validate(res.json())
        return data.lists

    async def get_list_members(self, list_id: str) -> list[ClickupUser]:
        """Get the members of a list"""
        res = await self._get(f"/list/{list_id}/member")
        data = ClickupListMembersRes.model_validate(res.json())
        return data.members

    async def get_tasks(
        self,
        workspace_id: str,
        updated_gte: datetime | None = None,
        updated_lte: datetime | None = None,
        reverse: bool = False,
    ) -> AsyncGenerator[list[ClickupTask]]:
        """
        Get tasks in a workspace, filtered by update time (yes those are inclusive bounds).
        reverse=True returns tasks in chronological order (oldest first).
        referse=False returns tasks in reverse chronological order (newest first).

        For example a full backfill goes back in time using updated_lte and reverse=False.
        while an incremental backfill goes forward in time using updated_gte and reverse=True.
        """
        path = f"/team/{workspace_id}/task"
        params: dict[str, str] = {
            "subtasks": "true",
            "include_closed": "true",
            "include_markdown_description": "true",
            "order_by": "updated",
            "reverse": "true" if reverse else "false",
        }

        if updated_gte:
            params["date_updated_gt"] = str(int(updated_gte.timestamp() * 1000))
        if updated_lte:
            params["date_updated_lt"] = str(int(updated_lte.timestamp() * 1000))

        page = 0
        while True:
            params["page"] = str(page)
            res = await self._get(path, params=params)
            data = ClickupTasksRes.model_validate(res.json())

            if not data.tasks:
                break

            yield data.tasks

            if data.last_page:
                break

            page += 1

    async def get_task_comments(
        self,
        task_id: str,
    ) -> AsyncGenerator[list[ClickupComment]]:
        path = f"/task/{task_id}/comment"
        params: dict[str, str] = {}

        while True:
            res = await self._get(path, params=params)
            data = ClickupCommentsRes.model_validate(res.json())

            if not data.comments:
                break

            yield data.comments

            params["start"] = data.comments[-1].date
            params["start_id"] = data.comments[-1].id

    async def get_comment_replies(self, comment_id: str) -> list[ClickupComment]:
        path = f"/comment/{comment_id}/reply"
        res = await self._get(path)
        data = ClickupCommentsRes.model_validate(res.json())
        return data.comments
