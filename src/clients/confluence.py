import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from pydantic import BaseModel

from src.utils.logging import get_logger
from src.utils.tenant_config import get_tenant_config_value

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)


class ConfluenceSpace(BaseModel):
    id: str
    key: str
    name: str
    type: str | None = None


class ConfluencePageSummary(BaseModel):
    id: str
    title: str
    status: str


class ConfluenceClient:
    """A client for interacting with the Confluence REST API v2 via Atlassian API Gateway."""

    def __init__(self, forge_oauth_token: str, cloud_id: str | None = None):
        if not forge_oauth_token:
            raise ValueError("Confluence Forge OAuth token is required and cannot be empty")

        self.api_base_url = f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/api/v2/"

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
        """Make a REST API request to the Confluence API."""
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
                logger.error(f"Confluence API error response body: {error_body}")
            except Exception:
                logger.error("Could not read error response body")

            if e.response.status_code == 429:
                # Handle rate limiting
                retry_after = int(e.response.headers.get("Retry-After", 60))
                logger.warning(f"Confluence API rate limited, retry after {retry_after}s")
                raise RateLimitedError(retry_after)
            elif e.response.status_code == 401:
                logger.error(
                    f"Confluence API authentication failed - Status: {e.response.status_code}, Error: {error_body}"
                )
                raise ValueError("Invalid Confluence credentials")
            elif e.response.status_code == 403:
                logger.error(
                    f"Confluence API access forbidden - Status: {e.response.status_code}, Error: {error_body}"
                )
                raise ValueError("Insufficient Confluence permissions")
            else:
                logger.error(
                    f"Confluence API request failed - Status: {e.response.status_code}, Error: {error_body}"
                )
                raise

        except requests.exceptions.RequestException as e:
            logger.error(f"Confluence API request error: {e}")
            raise

    def get_spaces(self) -> list[ConfluenceSpace]:
        """Get all spaces"""
        try:
            data = self._make_request("spaces")
            results = data.get("results", [])
            return [
                ConfluenceSpace(
                    id=space["id"], key=space["key"], name=space["name"], type=space.get("type")
                )
                for space in results
            ]
        except Exception as e:
            logger.error(f"Failed to fetch Confluence spaces: {e}")
            raise

    def get_space(self, space_id: str) -> dict[str, Any] | None:
        """Get a single space by its ID."""
        try:
            return self._make_request(f"spaces/{space_id}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Confluence space {space_id} not found")
                return None
            elif e.response.status_code == 403:
                logger.warning(f"Confluence space {space_id} access forbidden")
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to fetch Confluence space {space_id}: {e}")
            raise

    def get_page(self, page_id: str) -> dict[str, Any] | None:
        """Get a single page by its ID."""
        try:
            params = {
                "body-format": "export_view",
            }
            return self._make_request(f"pages/{page_id}", params=params)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Confluence page {page_id} not found")
                return None
            elif e.response.status_code == 403:
                logger.warning(f"Confluence page {page_id} access forbidden")
                return None
            raise
        except Exception as e:
            logger.error(f"Failed to fetch Confluence page {page_id}: {e}")
            raise

    def get_space_pages(
        self, space_id: str, cursor: str | None = None, limit: int = 250
    ) -> dict[str, Any]:
        try:
            params: dict[str, Any] = {"limit": limit}
            if cursor:
                params["cursor"] = cursor

            return self._make_request(f"spaces/{space_id}/pages", params=params)
        except Exception as e:
            logger.error(f"Failed to fetch pages for space {space_id}: {e}")
            raise

    def search_pages(
        self,
        cql: str | None = None,
        start: int = 0,
        limit: int = 250,
        space_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search for pages using CQL (Confluence Query Language)."""
        try:
            params = {
                "start": start,
                "limit": limit,
                "body-format": "storage",
            }

            if cql:
                params["cql"] = cql
            elif space_ids:
                # Build CQL query from space IDs
                space_filter = " OR ".join(f"space.id = {space_id}" for space_id in space_ids)
                params["cql"] = f"({space_filter}) AND type = page ORDER BY created DESC"
            else:
                params["cql"] = "type = page ORDER BY created DESC"

            return self._make_request("pages", params=params)
        except Exception as e:
            logger.error(f"Failed to search Confluence pages with CQL '{cql}': {e}")
            raise

    def get_all_pages(self, space_ids: list[str] | None = None) -> list[str]:
        """Get all page IDs, optionally filtered by spaces."""
        try:
            page_ids = []
            start = 0
            limit = 250

            while True:
                response = self.search_pages(
                    start=start,
                    limit=limit,
                    space_ids=space_ids,
                )

                pages = response.get("results", [])
                if not pages:
                    break

                # Extract page IDs
                page_ids.extend([page["id"] for page in pages])

                # Check if we've reached the end
                if len(pages) < limit:
                    break

                start += limit

            logger.info(f"Found {len(page_ids)} Confluence pages")
            return page_ids

        except Exception as e:
            logger.error(f"Failed to fetch all Confluence pages: {e}")
            raise

    async def get_site_domain(self, tenant_id: str) -> str | None:
        """Get the Confluence site domain from the configured CONFLUENCE_SITE_URL."""
        try:
            # Get the configured Confluence site URL
            confluence_site_url = await get_tenant_config_value("CONFLUENCE_SITE_URL", tenant_id)
            return confluence_site_url
        except Exception as e:
            logger.error(f"Failed to fetch Confluence site domain: {e}")
            raise
