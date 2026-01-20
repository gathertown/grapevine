"""
Gather meetings API client.
"""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel

from src.utils.env import GATHER_API_URL
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

logger = get_logger(__name__)


class GatherMeeting(BaseModel):
    """Model for a Gather meeting."""

    id: str
    type: str
    visibility: str


class GatherClient:
    """A client for interacting with the Gather meetings API."""

    def __init__(self, api_key: str, base_url: str = GATHER_API_URL):
        if not api_key:
            raise ValueError("Gather API key is required and cannot be empty")

        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "x-api-key": api_key,
            }
        )

    def _make_request(
        self, method: str, endpoint: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a REST API request to the Gather API."""
        url = f"{self.base_url}/{endpoint}"

        try:
            response = self.session.request(method, url, params=params)

            # Check for rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                logger.warning(f"Gather API rate limit hit, retrying after {retry_after}s")
                raise RateLimitedError(retry_after=retry_after)

            response.raise_for_status()

            return response.json()

        except RateLimitedError:
            raise
        except requests.exceptions.HTTPError:
            logger.error(f"Gather API HTTP error: {response.status_code} - {response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Gather API request error: {e}")
            raise

    @rate_limited()
    def get_space(self, space_id: str) -> dict[str, Any]:
        """
        Get information about a Gather space.

        Args:
            space_id: The Gather space ID

        Returns:
            Space information dictionary
        """
        endpoint = f"spaces/{space_id}"
        return self._make_request("GET", endpoint)

    @rate_limited()
    def start_meeting_export_session(self, space_id: str) -> dict[str, Any]:
        """
        Start a meeting export session for a Gather space.

        Args:
            space_id: The Gather space ID

        """

        endpoint = f"spaces/{space_id}/meetings/exports"

        response = self._make_request("POST", endpoint)
        return response.get("sessionId", "")

    @rate_limited()
    def get_meetings(
        self,
        space_id: str,
        session_id: str,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """
        Get meetings from a Gather space.

        Args:
            space_id: The Gather space ID
            session_id: The export session ID
            limit: Number of meetings to fetch (max 100)
            cursor: Pagination cursor

        Returns:
            Response with meetings list and pagination info
        """
        params: dict[str, Any] = {
            "limit": min(limit, 100),
        }
        if cursor:
            params["cursor"] = cursor

        endpoint = f"spaces/{space_id}/meetings/exports/{session_id}/meetings"
        return self._make_request("GET", endpoint, params=params)

    def get_all_meetings(
        self,
        space_id: str,
        limit_per_request: int = 100,
    ) -> Iterator[dict[str, Any]]:
        """
        Get all meetings from a space, handling pagination automatically.

        Args:
            space_id: The Gather space ID
            limit_per_request: Number of meetings to fetch per request

        Yields:
            Meeting dictionaries
        """
        cursor = None

        export_session_id = self.start_meeting_export_session(space_id)
        if not export_session_id:
            logger.error(f"Failed to start export session for space {space_id}")
            raise Exception("Could not start export session")

        while True:
            response = self.get_meetings(
                space_id=space_id,
                session_id=export_session_id,
                limit=limit_per_request,
                cursor=cursor,
            )

            items = response.get("items", [])
            yield from items

            # Check for next page
            next_cursor = response.get("nextCursor")
            if not next_cursor:
                break

            cursor = next_cursor
