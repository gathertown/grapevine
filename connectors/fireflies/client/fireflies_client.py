from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from typing import Any

import httpx
from aiolimiter import AsyncLimiter

from connectors.fireflies.client.fireflies_errors import (
    FirefliesGraphqlException,
    FirefliesObjectNotFoundException,
    FirefliesTooManyRequestsErrorRes,
)
from connectors.fireflies.client.fireflies_models import (
    FirefliesGraphqlRes,
    FirefliesTranscript,
    FirefliesTranscriptRes,
    FirefliesTranscriptsRes,
    GetFirefliesTranscriptsReq,
    GetFirefliesTranscriptsVariables,
)
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)

_fireflies_connection_limits = httpx.Limits(
    max_connections=15,
    max_keepalive_connections=15,
)


@dataclass
class FirefliesLimiters:
    tenant_id: str
    general: AsyncLimiter


# https://docs.fireflies.ai/fundamentals/limits#api-rate-limits
# general rate limit of 60 requests per minute, technically the free and pro tier only have 50
# requests per day, if we have customers on that tier and hit rate limiting issues we can probably
# not do a full backfill for them and just do incremental updates.
@cache
def _get_limiters(tenant_id: str) -> FirefliesLimiters:
    return FirefliesLimiters(
        tenant_id=tenant_id,
        # 60 requests per minute
        general=AsyncLimiter(1, 60 / 60),
    )


_get_transcripts_query = """
query ($limit: Int, $skip: Int, $from_date: DateTime, $to_date: DateTime) {
  transcripts(limit: $limit, skip: $skip, fromDate: $from_date, toDate: $to_date) {
    id
    title
    dateString
    duration
    transcript_url
    organizer_email
    participants

    meeting_info {
      summary_status
    }

    speakers {
      id
      name
    }

    summary {
      notes
    }

    sentences {
      text
      speaker_id
    }
  }
}
"""

_get_transcript_query = """
query ($id: String!) {
  transcript(id: $id) {
    id
    title
    dateString
    duration
    transcript_url
    organizer_email
    participants

    meeting_info {
      summary_status
    }

    speakers {
      id
      name
    }

    summary {
      notes
    }

    sentences {
      text
      speaker_id
    }
  }
}
"""


class FirefliesClient:
    def __init__(self, access_token: str | None, tenant_id: str):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        self._client = httpx.AsyncClient(
            base_url="https://api.fireflies.ai",
            headers=headers,
            limits=_fireflies_connection_limits,
            timeout=httpx.Timeout(5, read=30, pool=30),
        )

        self._limiters = _get_limiters(tenant_id)

    async def __aenter__(self) -> "FirefliesClient":
        return self

    async def __aexit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        await self._client.aclose()

    @rate_limited()
    async def _graphql(self, query: str, variables: dict[str, Any]) -> FirefliesGraphqlRes[Any]:
        async with self._limiters.general:
            try:
                response = await self._client.post(
                    "graphql", json={"query": query, "variables": variables}
                )
            except httpx.TimeoutException as e:
                msg = f"Fireflies {type(e).__name__}, retrying in 10 seconds: {e.request.url}"
                logger.warning(msg)
                raise RateLimitedError(message=msg, retry_after=10) from e

        if response.is_server_error:
            msg = f"Fireflies server error {response.status_code}, retrying in 10 seconds: {response.request.url}"
            logger.warning(msg)
            raise RateLimitedError(message=msg, retry_after=10)

        response.raise_for_status()

        res = FirefliesGraphqlRes(**response.json())

        if res.errors:
            too_many_requests_error = next(
                (e for e in res.errors if isinstance(e, FirefliesTooManyRequestsErrorRes)), None
            )
            if too_many_requests_error:
                retry_after_ms = too_many_requests_error.extensions.metadata.retry_after
                now_timestamp = datetime.now(UTC).timestamp()
                wait_seconds = max(0, (retry_after_ms / 1000) - now_timestamp)

                raise RateLimitedError(retry_after=wait_seconds)

            # We want to be able to catch not found errors specifically
            object_not_found_error = next(
                (e for e in res.errors if e.code == "object_not_found"), None
            )
            if object_not_found_error:
                raise FirefliesObjectNotFoundException(res.errors)

            raise FirefliesGraphqlException(res.errors)

        return res

    async def get_transcripts(
        self, req: GetFirefliesTranscriptsReq
    ) -> AsyncGenerator[list[FirefliesTranscript]]:
        vars = GetFirefliesTranscriptsVariables.from_req(req)
        while True:
            res = await self._graphql(_get_transcripts_query, vars.model_dump())
            typed_res = FirefliesTranscriptsRes(**res.model_dump())
            transcripts = typed_res.data.transcripts

            if not transcripts:
                break

            yield transcripts

            vars.skip += len(transcripts)

    async def get_transcript(self, transcript_id: str) -> FirefliesTranscript:
        vars = {"id": transcript_id}
        res = await self._graphql(_get_transcript_query, vars)
        typed_res = FirefliesTranscriptRes(**res.model_dump())
        return typed_res.data.transcript
