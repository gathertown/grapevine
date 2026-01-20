"""Async Gong API client used by ingest extractors."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx

from src.utils.logging import get_logger
from src.utils.rate_limiter import rate_limited

logger = get_logger(__name__)


DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 3
MAX_RETRY_DELAY_SECONDS = 60
SUCCESS_STATUS_MIN = 200
SUCCESS_STATUS_MAX = 299
RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
TRANSCRIPT_BATCH_SIZE = 20  # Gong API limit for transcript requests
CALLS_EXTENSIVE_BATCH_SIZE = 50  # Conservative limit for calls extensive requests
GONG_API_CALL_DELAY_SECONDS = 1  # Delay between sequential API calls to avoid rate limits


class GongAPIError(Exception):
    """Base exception for Gong API failures."""

    def __init__(
        self, message: str, *, status_code: int | None = None, response_body: Any | None = None
    ):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class GongClient:
    """Thin async wrapper around Gong REST API endpoints."""

    def __init__(
        self,
        *,
        access_token: str,
        api_base_url: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not access_token:
            raise ValueError("access_token is required")
        if not api_base_url:
            raise ValueError("api_base_url is required")

        normalized_base = api_base_url.rstrip("/")
        self._access_token = access_token
        self._api_base_url = normalized_base
        self._timeout_seconds = timeout_seconds
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=normalized_base,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": "corporate-context-gong-client/1.0",
            },
            timeout=timeout_seconds,
        )
        self._last_api_call_time = 0.0  # Track time of last API call for global rate limiting

    async def __aenter__(self) -> GongClient:
        return self

    async def __aexit__(self, _exc_type, _exc, _tb) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Public API wrappers
    # ------------------------------------------------------------------
    @rate_limited(max_retries=5, base_delay=5)
    async def get_workspaces(self) -> list[dict[str, Any]]:
        data = await self._get("/v2/workspaces")
        return self._extract_list(data, "workspaces")

    @rate_limited(max_retries=5, base_delay=5)
    async def get_users_extensive(self) -> list[dict[str, Any]]:
        data = await self._post("/v2/users/extensive", json_body={"filter": {}})
        return self._extract_list(data, "users")

    @rate_limited(max_retries=5, base_delay=5)
    async def get_permission_profiles(self, workspace_id: str) -> list[dict[str, Any]]:
        data = await self._get("/v2/all-permission-profiles", params={"workspaceId": workspace_id})
        return self._extract_list(data, "profiles")

    @rate_limited(max_retries=5, base_delay=5)
    async def get_permission_profile_users(self, profile_id: str) -> list[dict[str, Any]]:
        data = await self._get("/v2/permission-profile/users", params={"profileId": profile_id})
        return self._extract_list(data, "users")

    @rate_limited(max_retries=5, base_delay=5)
    async def get_library_folders(self, workspace_id: str) -> list[dict[str, Any]]:
        data = await self._get("/v2/library/folders", params={"workspaceId": workspace_id})
        return self._extract_list(data, "folders")

    @rate_limited(max_retries=5, base_delay=5)
    async def get_library_folder_content(self, folder_id: str) -> list[dict[str, Any]]:
        data = await self._get("/v2/library/folder-content", params={"folderId": folder_id})
        return self._extract_list(data, "calls")

    @rate_limited(max_retries=5, base_delay=5)
    async def iter_calls(
        self,
        *,
        workspace_id: str,
        from_datetime: str | None = None,
        to_datetime: str | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Iterate through calls using cursor-based pagination.

        Args:
            workspace_id: Workspace to fetch calls from
            from_datetime: Start datetime filter
            to_datetime: End datetime filter
            limit: Maximum calls per page (None for API default, typically ~100)
        """
        cursor = None

        while True:
            params: dict[str, Any] = {
                "workspaceId": workspace_id,
            }
            if cursor:
                params["cursor"] = cursor
            if from_datetime:
                params["fromDateTime"] = from_datetime
            if to_datetime:
                params["toDateTime"] = to_datetime

            data = await self._get("/v2/calls", params=params)
            calls = self._extract_list(data, "calls")
            if not calls:
                break

            # Apply per-page limit if specified
            if limit:
                calls = calls[:limit]

            for call in calls:
                yield call

            # Check if there's a cursor for the next page
            records = data.get("records", {})
            next_cursor = records.get("cursor")
            if not next_cursor:
                break
            cursor = next_cursor

    @rate_limited(max_retries=5, base_delay=5)
    async def get_calls_extensive(self, call_ids: Sequence[str]) -> list[dict[str, Any]]:
        if not call_ids:
            return []

        all_calls: list[dict[str, Any]] = []

        # Process call_ids in batches of CALLS_EXTENSIVE_BATCH_SIZE (50)
        for i in range(0, len(call_ids), CALLS_EXTENSIVE_BATCH_SIZE):
            batch_call_ids = call_ids[i : i + CALLS_EXTENSIVE_BATCH_SIZE]

            payload = {
                "filter": {"callIds": [str(call_id) for call_id in batch_call_ids]},
                "contentSelector": {"exposedFields": {"parties": True}},
            }

            logger.debug(
                "Requesting Gong calls extensive batch",
                endpoint="/v2/calls/extensive",
                batch_call_count=len(batch_call_ids),
                total_calls=len(call_ids),
                batch_index=f"{i // CALLS_EXTENSIVE_BATCH_SIZE + 1}/{(len(call_ids) + CALLS_EXTENSIVE_BATCH_SIZE - 1) // CALLS_EXTENSIVE_BATCH_SIZE}",
            )

            try:
                data = await self._post("/v2/calls/extensive", json_body=payload)
                calls = self._extract_list(data, "calls")
                all_calls.extend(calls)
                logger.debug(
                    "Fetched Gong calls extensive batch",
                    batch_call_count=len(calls),
                    total_calls_so_far=len(all_calls),
                )
            except Exception as e:
                logger.error(
                    "Failed to fetch Gong calls extensive batch",
                    batch_call_ids=batch_call_ids,
                    error=str(e),
                )
                raise

        logger.debug(
            "Fetched all Gong calls extensive",
            total_call_count=len(call_ids),
            total_calls_returned=len(all_calls),
        )
        return all_calls

    @rate_limited(max_retries=5, base_delay=5)
    async def get_call_transcripts(
        self,
        call_ids: Sequence[str],
        from_datetime: str | None = None,
        to_datetime: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get transcripts for calls.

        Args:
            call_ids: List of call IDs
            from_datetime: ISO datetime string for start of range (defaults to 1 year ago)
            to_datetime: ISO datetime string for end of range (defaults to now)

        Returns:
            List of call transcript objects
        """
        if not call_ids:
            return []

        # Default to a very wide window if not specified (last 2 years to now)
        # Gong expects ISO 8601 with timezone
        if not from_datetime:
            from datetime import UTC, datetime, timedelta

            from_datetime = (datetime.now(UTC) - timedelta(days=730)).isoformat()
        if not to_datetime:
            from datetime import UTC, datetime

            to_datetime = datetime.now(UTC).isoformat()

        all_transcripts: list[dict[str, Any]] = []

        # Process call_ids in batches of TRANSCRIPT_BATCH_SIZE (20)
        for i in range(0, len(call_ids), TRANSCRIPT_BATCH_SIZE):
            batch_call_ids = call_ids[i : i + TRANSCRIPT_BATCH_SIZE]

            payload = {
                "filter": {
                    "callIds": [str(call_id) for call_id in batch_call_ids],
                    "fromDateTime": from_datetime,
                    "toDateTime": to_datetime,
                }
            }

            logger.debug(
                "Requesting Gong transcripts batch",
                endpoint="/v2/calls/transcript",
                batch_call_count=len(batch_call_ids),
                total_calls=len(call_ids),
                batch_index=f"{i // TRANSCRIPT_BATCH_SIZE + 1}/{(len(call_ids) + TRANSCRIPT_BATCH_SIZE - 1) // TRANSCRIPT_BATCH_SIZE}",
                from_datetime=from_datetime,
                to_datetime=to_datetime,
            )

            try:
                data = await self._post("/v2/calls/transcript", json_body=payload)
                transcripts = self._extract_list(data, "callTranscripts")
                all_transcripts.extend(transcripts)
                logger.debug(
                    "Fetched Gong transcripts batch",
                    batch_transcript_count=len(transcripts),
                    total_transcripts_so_far=len(all_transcripts),
                )
            except Exception as e:
                logger.error(
                    "Failed to fetch Gong transcripts batch",
                    batch_call_ids=batch_call_ids,
                    error=str(e),
                )
                raise

        logger.debug(
            "Fetched all Gong transcripts",
            total_call_count=len(call_ids),
            total_transcript_count=len(all_transcripts),
        )
        return all_transcripts

    @rate_limited(max_retries=5, base_delay=5)
    async def get_call_users_access(self, call_ids: Sequence[str]) -> list[dict[str, Any]]:
        if not call_ids:
            return []

        all_access_entries: list[dict[str, Any]] = []

        # Process call_ids in batches of CALLS_EXTENSIVE_BATCH_SIZE (50)
        for i in range(0, len(call_ids), CALLS_EXTENSIVE_BATCH_SIZE):
            batch_call_ids = call_ids[i : i + CALLS_EXTENSIVE_BATCH_SIZE]

            payload = {"filter": {"callIds": [str(call_id) for call_id in batch_call_ids]}}

            logger.debug(
                "Requesting Gong call users access batch",
                endpoint="/v2/calls/users-access",
                batch_call_count=len(batch_call_ids),
                total_calls=len(call_ids),
                batch_index=f"{i // CALLS_EXTENSIVE_BATCH_SIZE + 1}/{(len(call_ids) + CALLS_EXTENSIVE_BATCH_SIZE - 1) // CALLS_EXTENSIVE_BATCH_SIZE}",
            )

            try:
                data = await self._post("/v2/calls/users-access", json_body=payload)
                access_entries = self._extract_list(data, "callAccessList")
                all_access_entries.extend(access_entries)
                logger.debug(
                    "Fetched Gong call users access batch",
                    batch_access_count=len(access_entries),
                    total_access_so_far=len(all_access_entries),
                )
            except Exception as e:
                logger.error(
                    "Failed to fetch Gong call users access batch",
                    batch_call_ids=batch_call_ids,
                    error=str(e),
                )
                raise

        logger.debug(
            "Fetched all Gong call users access",
            total_call_count=len(call_ids),
            total_access_entries=len(all_access_entries),
        )
        return all_access_entries

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def _post(self, path: str, json_body: dict[str, Any]) -> dict[str, Any]:
        return await self._request("POST", path, json=json_body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            # Enforce global rate limiting - ensure minimum delay between API calls
            current_time = time.time()
            time_since_last_call = current_time - self._last_api_call_time
            if time_since_last_call < GONG_API_CALL_DELAY_SECONDS:
                delay_needed = GONG_API_CALL_DELAY_SECONDS - time_since_last_call
                logger.debug(
                    f"Gong API global rate limiting: waiting {delay_needed:.1f} seconds before next call",
                    method=method,
                    path=path,
                )
                await asyncio.sleep(delay_needed)

            try:
                response = await self._client.request(method, path, params=params, json=json)
                self._last_api_call_time = (
                    time.time()
                )  # Update last call time on successful request
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                logger.warning(
                    "Gong request transport failure",
                    method=method,
                    path=path,
                    attempt=attempt,
                    error=str(exc),
                )
                await self._sleep_before_retry(response=None, attempt=attempt)
                continue

            if SUCCESS_STATUS_MIN <= response.status_code <= SUCCESS_STATUS_MAX:
                return self._parse_json_response(response)

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_RETRIES:
                retry_after = self._sleep_time_from_response(response, attempt)
                logger.info(
                    "Gong request retrying",
                    method=method,
                    path=path,
                    status=response.status_code,
                    attempt=attempt,
                    retry_after_seconds=retry_after,
                )
                await asyncio.sleep(retry_after)
                continue

            # Non-retryable or exhausted retries
            error_body = self._safe_get_content(response)
            logger.error(
                "Gong API request failed",
                method=method,
                path=path,
                status_code=response.status_code,
                response_body=error_body,
                request_params=params,
                request_json=json,
            )
            raise GongAPIError(
                f"Gong API request failed with status {response.status_code}",
                status_code=response.status_code,
                response_body=error_body,
            )

        raise GongAPIError(
            "Gong API request exhausted retries",
            response_body=str(last_error) if last_error else None,
        )

    def _parse_json_response(self, response: httpx.Response) -> dict[str, Any]:
        try:
            return response.json()
        except ValueError as exc:  # pragma: no cover - unexpected from Gong
            text = response.text
            raise GongAPIError(
                "Failed to parse Gong JSON response",
                status_code=response.status_code,
                response_body=text,
            ) from exc

    async def _sleep_before_retry(self, response: httpx.Response | None, attempt: int) -> None:
        retry_after = self._sleep_time_from_response(response, attempt)
        await asyncio.sleep(retry_after)

    def _sleep_time_from_response(self, response: httpx.Response | None, attempt: int) -> float:
        # Exponential backoff with jitter, honoring Retry-After when provided.
        if response is not None:
            retry_after_header = response.headers.get("Retry-After")
            if retry_after_header:
                try:
                    retry_after = float(retry_after_header)
                    if retry_after > 0:
                        return min(retry_after, MAX_RETRY_DELAY_SECONDS)
                except ValueError:
                    pass

        backoff = min(MAX_RETRY_DELAY_SECONDS, (2 ** (attempt - 1)))
        jitter = random.uniform(0, 0.25 * backoff)
        return max(1.0, backoff + jitter)

    def _extract_list(
        self, data: dict[str, Any] | None, *preferred_keys: str
    ) -> list[dict[str, Any]]:
        if not data:
            return []
        for key in preferred_keys:
            value = data.get(key)
            if isinstance(value, list):
                return value
        for value in data.values():
            if isinstance(value, list):
                return value
        return []

    def _safe_get_content(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text
