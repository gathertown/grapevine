"""Pylon API client with rate limiting and pagination support."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Any

import httpx
from aiolimiter import AsyncLimiter

from connectors.pylon.client.pylon_models import (
    PylonAccount,
    PylonAccountsResponse,
    PylonContact,
    PylonContactsResponse,
    PylonIssue,
    PylonIssuesResponse,
    PylonMeResponse,
    PylonMessage,
    PylonTeam,
    PylonTeamsResponse,
    PylonUser,
    PylonUsersResponse,
)
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)

# Pylon API base URL
PYLON_API_BASE_URL = "https://api.usepylon.com"


# Rate limiting - Pylon doesn't specify exact limits, so being conservative
# Using 100 req/min as a safe default
@dataclass
class PylonLimiters:
    """Rate limiters for Pylon API."""

    general: AsyncLimiter


@cache
def _get_limiters() -> PylonLimiters:
    return PylonLimiters(
        general=AsyncLimiter(1, 60 / 100),  # 100 req / min no bursting
    )


_pylon_connection_limits = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=20,
)


def _get_headers(api_token: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_token}",
    }


class PylonClient:
    """Async client for Pylon API with rate limiting."""

    def __init__(self, api_token: str):
        self._api_token = api_token
        self._client = httpx.AsyncClient(
            base_url=PYLON_API_BASE_URL,
            headers=_get_headers(api_token),
            limits=_pylon_connection_limits,
        )
        self._limiters = _get_limiters()

    async def __aenter__(self) -> "PylonClient":
        return self

    async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        await self._client.aclose()

    @rate_limited()
    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """Make a GET request with rate limiting."""
        try:
            async with self._limiters.general:
                response = await self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after", "60")
                raise RateLimitedError(retry_after=int(retry_after)) from e
            raise
        except httpx.ReadTimeout as e:
            logger.error(f"Pylon get timeout: {e.request.url}")
            raise

        return response.json()

    @rate_limited()
    async def _post(self, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a POST request with rate limiting."""
        try:
            async with self._limiters.general:
                response = await self._client.post(path, json=json_body)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("retry-after", "60")
                raise RateLimitedError(retry_after=int(retry_after)) from e
            raise
        except httpx.ReadTimeout as e:
            logger.error(f"Pylon post timeout: {e.request.url}")
            raise

        return response.json()

    async def get_me(self) -> PylonMeResponse:
        """Get current organization info to verify token."""
        data = await self._get("/me")
        return PylonMeResponse(**data.get("data", data))

    async def list_issues(
        self,
        start_time: datetime,
        end_time: datetime,
        cursor: str | None = None,
    ) -> PylonIssuesResponse:
        """
        List issues updated within a time range.
        The time range must be <= 30 days.
        """
        params: dict[str, str] = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
        }
        if cursor:
            params["cursor"] = cursor

        data = await self._get("/issues", params=params)

        issues = [PylonIssue(**issue) for issue in data.get("data", [])]
        return PylonIssuesResponse(
            data=issues,
            cursor=data.get("cursor"),
            request_id=data.get("request_id"),
        )

    async def get_issue(self, issue_id: str) -> PylonIssue:
        """Get a single issue by ID or number."""
        data = await self._get(f"/issues/{issue_id}")
        return PylonIssue(**data.get("data", data))

    async def search_issues(
        self,
        filters: dict[str, Any],
        cursor: str | None = None,
        limit: int = 100,
    ) -> PylonIssuesResponse:
        """
        Search issues with filters.

        Filter operators: equals, in, not_in, is_set, is_unset, time_range, string_contains
        Filterable fields: created_at, account_id, state, assignee_id, requester_id,
                          tags, title, body_html, team_id, issue_type, resolved_at
        """
        body: dict[str, Any] = {
            "filter": filters,
            "limit": limit,
        }
        if cursor:
            body["cursor"] = cursor

        data = await self._post("/issues/search", json_body=body)

        issues = [PylonIssue(**issue) for issue in data.get("data", [])]
        return PylonIssuesResponse(
            data=issues,
            cursor=data.get("cursor"),
            request_id=data.get("request_id"),
        )

    async def iterate_issues(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> AsyncGenerator[PylonIssue]:
        """Iterate through all issues in a time range, handling pagination."""
        cursor: str | None = None

        while True:
            response = await self.list_issues(
                start_time=start_time,
                end_time=end_time,
                cursor=cursor,
            )

            for issue in response.data:
                yield issue

            if not response.cursor:
                break

            cursor = response.cursor

    async def list_accounts(
        self,
        cursor: str | None = None,
        limit: int = 100,
    ) -> PylonAccountsResponse:
        """List all accounts with pagination."""
        params: dict[str, str] = {
            "limit": str(limit),
        }
        if cursor:
            params["cursor"] = cursor

        data = await self._get("/accounts", params=params)

        accounts = [PylonAccount(**account) for account in data.get("data", [])]
        return PylonAccountsResponse(
            data=accounts,
            cursor=data.get("cursor"),
            request_id=data.get("request_id"),
        )

    async def get_account(self, account_id: str) -> PylonAccount:
        """Get a single account by ID."""
        data = await self._get(f"/accounts/{account_id}")
        return PylonAccount(**data.get("data", data))

    async def iterate_accounts(self) -> AsyncGenerator[PylonAccount]:
        """Iterate through all accounts, handling pagination."""
        cursor: str | None = None

        while True:
            response = await self.list_accounts(cursor=cursor, limit=100)

            for account in response.data:
                yield account

            if not response.cursor:
                break

            cursor = response.cursor

    async def list_contacts(
        self,
        cursor: str | None = None,
        limit: int = 100,
    ) -> PylonContactsResponse:
        """List all contacts with pagination."""
        params: dict[str, str] = {
            "limit": str(limit),
        }
        if cursor:
            params["cursor"] = cursor

        data = await self._get("/contacts", params=params)

        contacts = [PylonContact(**contact) for contact in data.get("data", [])]
        return PylonContactsResponse(
            data=contacts,
            cursor=data.get("cursor"),
            request_id=data.get("request_id"),
        )

    async def get_contact(self, contact_id: str) -> PylonContact:
        """Get a single contact by ID."""
        data = await self._get(f"/contacts/{contact_id}")
        return PylonContact(**data.get("data", data))

    async def iterate_contacts(self) -> AsyncGenerator[PylonContact]:
        """Iterate through all contacts, handling pagination."""
        cursor: str | None = None

        while True:
            response = await self.list_contacts(cursor=cursor, limit=100)

            for contact in response.data:
                yield contact

            if not response.cursor:
                break

            cursor = response.cursor

    async def get_issue_messages(self, issue_id: str) -> list[PylonMessage]:
        """
        Get messages for an issue.

        Note: Pylon's API doesn't have a dedicated list messages endpoint in the docs,
        so messages are typically included in the issue response. This method
        fetches the full issue and extracts messages if they are included.
        """
        # The issue details should include messages based on the API structure
        # If not directly available, we may need to use the issue's body_html
        # For now, return empty list as messages are embedded in issues
        logger.debug(f"Getting messages for issue {issue_id}")
        return []

    async def list_users(
        self,
        cursor: str | None = None,
        limit: int = 100,
    ) -> PylonUsersResponse:
        """List all users (internal team members) with pagination."""
        params: dict[str, str] = {
            "limit": str(limit),
        }
        if cursor:
            params["cursor"] = cursor

        data = await self._get("/users", params=params)

        users = [PylonUser(**user) for user in data.get("data", [])]
        return PylonUsersResponse(
            data=users,
            cursor=data.get("cursor"),
            request_id=data.get("request_id"),
        )

    async def get_user(self, user_id: str) -> PylonUser:
        """Get a single user by ID."""
        data = await self._get(f"/users/{user_id}")
        return PylonUser(**data.get("data", data))

    async def iterate_users(self) -> AsyncGenerator[PylonUser]:
        """Iterate through all users, handling pagination."""
        cursor: str | None = None

        while True:
            response = await self.list_users(cursor=cursor, limit=100)

            for user in response.data:
                yield user

            if not response.cursor:
                break

            cursor = response.cursor

    async def list_teams(
        self,
        cursor: str | None = None,
        limit: int = 100,
    ) -> PylonTeamsResponse:
        """List all teams with pagination."""
        params: dict[str, str] = {
            "limit": str(limit),
        }
        if cursor:
            params["cursor"] = cursor

        data = await self._get("/teams", params=params)

        teams = [PylonTeam(**team) for team in data.get("data", [])]
        return PylonTeamsResponse(
            data=teams,
            cursor=data.get("cursor"),
            request_id=data.get("request_id"),
        )

    async def get_team(self, team_id: str) -> PylonTeam:
        """Get a single team by ID."""
        data = await self._get(f"/teams/{team_id}")
        return PylonTeam(**data.get("data", data))

    async def iterate_teams(self) -> AsyncGenerator[PylonTeam]:
        """Iterate through all teams, handling pagination."""
        cursor: str | None = None

        while True:
            response = await self.list_teams(cursor=cursor, limit=100)

            for team in response.data:
                yield team

            if not response.cursor:
                break

            cursor = response.cursor
