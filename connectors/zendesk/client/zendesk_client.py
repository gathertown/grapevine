from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from typing import Any
from urllib.parse import quote, urlencode

import httpx
from aiolimiter import AsyncLimiter

from connectors.zendesk.client.zendesk_help_center_models import (
    ZendeskCommentRes,
    ZendeskIncrementalArticlesRes,
)
from connectors.zendesk.client.zendesk_models import DateWindow, ZendeskTokenResponse
from src.utils.config import get_config_value_str, require_config_value
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

from .zendesk_ticketing_models import (
    ZendeskBrandResponse,
    ZendeskCustomTicketStatus,
    ZendeskGroupResponse,
    ZendeskIncrementalTicketEventResponse,
    ZendeskIncrementalTicketResponse,
    ZendeskOrganization,
    ZendeskSearchTicketResponse,
    ZendeskTicketFieldResponse,
    ZendeskTicketMetrics,
    ZendeskUser,
)

logger = get_logger(__name__)


# https://developer.zendesk.com/api-reference/introduction/rate-limits/
# Standard rate limit is 700 requests per minute.
# Search export rate limit is 100 requests per minute.
# Incremental rate limit is 10 requests per minute.
# These are shared across the entire Zendesk instance, so lets undershoot
@dataclass
class ZendeskLimiters:
    subdomain: str
    general: AsyncLimiter
    search: AsyncLimiter
    incremental: AsyncLimiter


@cache
def _get_limiters(subdomain: str) -> ZendeskLimiters:
    return ZendeskLimiters(
        subdomain=subdomain,
        general=AsyncLimiter(1, 60 / 350),  # 350 req / min no bursting,
        search=AsyncLimiter(1, 60 / 60),  # 60 req / min no bursting,
        incremental=AsyncLimiter(1, 60 / 8),  # 8 req / min no bursting,
    )


_zendesk_connection_limits = httpx.Limits(
    max_connections=20,
    max_keepalive_connections=20,
)


def _get_zendesk_marketplace_headers() -> dict[str, str]:
    zendesk_app_name = get_config_value_str("ZENDESK_MARKETPLACE_APP_NAME")
    zendesk_app_id = get_config_value_str("ZENDESK_MARKETPLACE_APP_ID")
    zendesk_org_id = get_config_value_str("ZENDESK_MARKETPLACE_ORG_ID")

    return {
        "X-Zendesk-Marketplace-Name": zendesk_app_name or "",
        "X-Zendesk-Marketplace-App-Id": zendesk_app_id or "",
        "X-Zendesk-Marketplace-Organization-Id": zendesk_org_id or "",
    }


def _get_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        **_get_zendesk_marketplace_headers(),
    }


def _window_to_zendesk_created_search_query(window: DateWindow) -> str:
    """Inclusive range (created_after, created_before)"""

    query = ""

    if window.start:
        query += f" created>={window.start.astimezone().isoformat(timespec='seconds')}"
    if window.end:
        query += f" created<={window.end.astimezone().isoformat(timespec='seconds')}"

    return query.strip()


class ZendeskOauthClient:
    def __init__(self, subdomain: str):
        base_url = f"https://{subdomain}.zendesk.com"

        self._subdomain = subdomain
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=_get_headers(),
        )

    async def __aenter__(self) -> "ZendeskOauthClient":
        return self

    async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        await self._client.aclose()

    async def oauth_refresh(self, refresh_token: str) -> ZendeskTokenResponse:
        """Refresh the OAuth token using the refresh token."""
        path = "/oauth/tokens"

        client_id = require_config_value("ZENDESK_CLIENT_ID")
        client_secret = require_config_value("ZENDESK_CLIENT_SECRET")

        body = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "scopes": "read",
        }

        response = await self._client.post(path, json=body)
        response.raise_for_status()
        res_data = response.json()
        return ZendeskTokenResponse(**res_data)


class ZendeskClient:
    def __init__(self, subdomain: str, access_token: str):
        base_url = f"https://{subdomain}.zendesk.com/api/v2"

        self._subdomain = subdomain
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                **_get_headers(),
                "Authorization": f"Bearer {access_token}",
            },
            limits=_zendesk_connection_limits,
        )
        self._limiters = _get_limiters(subdomain)

    async def __aenter__(self) -> "ZendeskClient":
        return self

    async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        await self._client.aclose()

    @rate_limited()
    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """Most instances have a shared rate limit of 700 req / min"""

        try:
            async with self._limiters.general:
                response = await self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                resets_seconds = e.response.headers.get("ratelimit-reset")
                raise RateLimitedError(retry_after=int(resets_seconds)) from e

            raise
        except httpx.ReadTimeout as e:
            logger.error(f"Zendesk get timeout: {e.request.url}")
            raise

        return response.json()

    @rate_limited()
    async def _get_search(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """
        Search can have pretty long responses, so custom timeout here.
        Most instances have a shared search rate limit of 100 req / min.
        Also handle our own param encoding because zendesk servers don't like spaces encoded as +.
        """
        try:
            if params:
                encoded_params = urlencode(params, quote_via=quote)
                url_search = f"?{encoded_params}"
            else:
                url_search = ""

            timeout = httpx.Timeout(5, read=30)
            async with self._limiters.search:
                response = await self._client.get(f"{path}{url_search}", timeout=timeout)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                resets_seconds = e.response.headers.get("ratelimit-reset")
                raise RateLimitedError(retry_after=int(resets_seconds)) from e

            raise
        except httpx.ReadTimeout as e:
            logger.error(f"Zendesk search timeout: {e.request.url}")
            raise

        return response.json()

    @rate_limited()
    async def _get_incremental(
        self,
        path: str,
        params: dict[str, str],
    ) -> dict[str, Any]:
        """
        Incremental endpoints have pretty long responses, so custom timeout here. Additionally,
        we implement a recursive page size reduction on ReadTimeout to try and work around Zendesk's
        fairly regular slowness. basically ticket events with large comments are huge to fetch. Most
        instances have a shared incremental rate limit of 10 req / min.
        """

        page_size = int(params["per_page"])
        if page_size < 100:
            msg = f"Zendesk incremental ReadTimeout avoidance, recursive page size reduction failed, not attempting: {path} {params}"
            raise ValueError(msg)

        try:
            timeout = httpx.Timeout(5, read=60)
            async with self._limiters.incremental:
                response = await self._client.get(path, params=params, timeout=timeout)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                resets_seconds = e.response.headers.get("ratelimit-reset")
                raise RateLimitedError(retry_after=int(resets_seconds)) from e

            raise
        except httpx.ReadTimeout as e:
            half_size = page_size // 2
            new_params = {**params, "per_page": str(half_size)}
            logger.warning(
                f"Zendesk incremental ReadTimeout: {e.request.url}. Retrying with page size {half_size}"
            )
            return await self._get_incremental(path, params=new_params)

        return response.json()

    async def show_users(
        self,
        user_ids: list[int],
    ) -> list[ZendeskUser]:
        params = {
            "ids": ",".join(str(user_id) for user_id in user_ids),
        }
        results = await self._get("/users/show_many", params=params)
        return [ZendeskUser(**user) for user in results["users"]]

    async def show_organizations(self, organization_ids: list[int]) -> list[ZendeskOrganization]:
        params = {
            "ids": ",".join(str(org_id) for org_id in organization_ids),
        }
        results = await self._get("/organizations/show_many", params=params)
        return [ZendeskOrganization(**org) for org in results["organizations"]]

    async def show_metrics_for_tickets(self, ticket_ids: list[int]) -> list[ZendeskTicketMetrics]:
        params = {
            "ids": ",".join(str(ticket_id) for ticket_id in ticket_ids),
            "include": "metric_sets",
        }
        results = await self._get("/tickets/show_many", params=params)

        return [
            ZendeskTicketMetrics(**ticket["metric_set"])
            for ticket in results["tickets"]
            if "metric_set" in ticket
        ]

    async def search_tickets_window(
        self, window: DateWindow, cursor: str | None = None
    ) -> ZendeskSearchTicketResponse:
        """
        Search tickets created within the given window.
        Filter out deleted tickets and populate subdomains.
        """
        query = _window_to_zendesk_created_search_query(window)

        path = "/search/export"
        params: dict[str, str] = {
            "query": f"type:ticket {query}",
            "page[size]": "1000",
            "filter[type]": "ticket",
        }
        if cursor:
            params["page[after]"] = cursor

        data = await self._get_search(path, params=params)
        data["results"] = [ticket for ticket in data["results"] if ticket["status"] != "deleted"]
        for ticket in data["results"]:
            ticket["subdomain"] = self._subdomain

        return ZendeskSearchTicketResponse(**data)

    async def incremental_tickets(
        self,
        cursor: str | None = None,
        start_time: int | None = None,
    ) -> ZendeskIncrementalTicketResponse:
        """
        Incrementally fetch tickets updated since start_time or from the given cursor.
        Filter out deleted tickets and populate subdomains.
        """

        path = "/incremental/tickets/cursor"
        params: dict[str, str] = {
            "per_page": "1000",
            "include": "metric_sets",
        }

        if cursor is None and start_time is None:
            raise ValueError("Either cursor or start_time must be provided to incremental_tickets")

        if cursor:
            params["cursor"] = cursor
        if start_time:
            params["start_time"] = str(start_time)

        data = await self._get_incremental(path, params=params)

        data["tickets"] = [ticket for ticket in data["tickets"] if ticket["status"] != "deleted"]
        for ticket in data["tickets"]:
            ticket["subdomain"] = self._subdomain

        return ZendeskIncrementalTicketResponse(**data)

    async def incremental_ticket_events(
        self,
        start_time: int,
    ) -> ZendeskIncrementalTicketEventResponse:
        path = "/incremental/ticket_events"
        params: dict[str, str] = {
            "per_page": "1000",
            "include": "comment_events",
            "start_time": str(start_time),
        }

        data = await self._get_incremental(path, params=params)
        return ZendeskIncrementalTicketEventResponse(**data)

    async def list_groups(self) -> AsyncGenerator[ZendeskGroupResponse]:
        path = "/groups"
        params: dict[str, str] = {
            "page[size]": "100",
        }

        while True:
            res = await self._get(path, params=params)
            data = ZendeskGroupResponse(**res)

            yield data

            if not data.meta.has_more or data.meta.after_cursor is None:
                break

            params["page[after]"] = data.meta.after_cursor

    async def list_brands(self) -> AsyncGenerator[ZendeskBrandResponse]:
        path = "/brands"
        params: dict[str, str] = {
            "page[size]": "100",
        }

        while True:
            res = await self._get(path, params=params)
            data = ZendeskBrandResponse(**res)

            yield data

            if not data.meta.has_more or data.meta.after_cursor is None:
                break

            params["page[after]"] = data.meta.after_cursor

    async def list_ticket_fields(self) -> AsyncGenerator[ZendeskTicketFieldResponse]:
        path = "/ticket_fields"
        params: dict[str, str] = {
            "page[size]": "100",
        }

        while True:
            res = await self._get(path, params=params)
            data = ZendeskTicketFieldResponse(**res)

            yield data

            if not data.meta.has_more or data.meta.after_cursor is None:
                break

            params["page[after]"] = data.meta.after_cursor

    async def list_custom_statuses(self) -> list[ZendeskCustomTicketStatus]:
        data = await self._get("/custom_statuses")
        return [ZendeskCustomTicketStatus(**result) for result in data["custom_statuses"]]

    async def incremental_articles(
        self, start_time: datetime, end_time: datetime | None = None
    ) -> AsyncGenerator[ZendeskIncrementalArticlesRes]:
        """Partially inclusive range [start_time, end_time), start time included, end time excluded. for ez windowing."""

        path = "/help_center/incremental/articles"
        params: dict[str, str] = {
            "per_page": "1000",
            "start_time": str(int(start_time.timestamp())),
            "include": "sections,categories",
        }

        while True:
            res = await self._get(path, params=params)
            data = ZendeskIncrementalArticlesRes(**res)

            data.articles = [
                article
                for article in data.articles
                if end_time is None or datetime.fromisoformat(article.updated_at) < end_time
            ]

            if not data.articles:
                break

            yield data

            if data.next_page is None:
                break

            # naive approach means possibly missing articles updated in the same second off the end of the page
            params["start_time"] = str(data.end_time)

    async def list_article_comments(self, article_id: int) -> AsyncGenerator[ZendeskCommentRes]:
        path = f"/help_center/articles/{article_id}/comments"
        params: dict[str, str] = {
            "page[size]": "100",
        }

        while True:
            res = await self._get(path, params=params)
            data = ZendeskCommentRes(**res)

            if not data.comments:
                break

            yield data

            if not data.meta.has_more or data.meta.after_cursor is None:
                break

            params["page[after]"] = data.meta.after_cursor
