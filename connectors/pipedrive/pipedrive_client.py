"""
Pipedrive API client for CRM data operations.

Based on Pipedrive REST API v1/v2:
- API v1: https://developers.pipedrive.com/docs/api/v1
- API v2: https://developers.pipedrive.com/docs/api/v1 (v2 endpoints)

Rate limits:
- Token-based daily budget: 30,000 base tokens x plan multiplier x seats
- Burst limits: Rolling 2-second window per user
- Search API: 10 requests per 2 seconds

Pagination:
- Cursor-based for v2 endpoints (deals, persons, organizations, activities)
- Offset-based for v1 endpoints
- Max 500 items per page

OAuth:
- Authorization: https://oauth.pipedrive.com/oauth/authorize
- Token exchange: https://oauth.pipedrive.com/oauth/token
- Refresh tokens expire after 60 days of non-use
"""

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import requests
from pydantic import BaseModel

from connectors.base.utils import parse_iso_timestamp
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited
from src.utils.tenant_config import get_tenant_config_value

# Pipedrive OAuth configuration
PIPEDRIVE_OAUTH_TOKEN_URL = "https://oauth.pipedrive.com/oauth/token"

logger = get_logger(__name__)

# Pipedrive API configuration
MAX_RECORDS_PER_PAGE = 100  # Default limit
MAX_ALLOWED_LIMIT = 500  # Maximum allowed by API


class PipedriveSearchResult(BaseModel):
    """Result from a Pipedrive list/query operation."""

    items: list[dict[str, Any]]
    next_cursor: str | None = None
    additional_data: dict[str, Any] | None = None


class PipedriveClient:
    """A client for interacting with the Pipedrive REST API.

    Pipedrive uses OAuth 2.0 with access and refresh tokens.
    The api_domain is returned during OAuth and varies per company.

    Rate limits are token-based with a daily budget and burst limits.
    """

    OAUTH_BASE_URL = "https://oauth.pipedrive.com"

    def __init__(self, access_token: str, api_domain: str):
        """Initialize the Pipedrive client.

        Args:
            access_token: OAuth access token
            api_domain: Company-specific API domain (e.g., https://company.pipedrive.com)
        """
        if not access_token:
            raise ValueError("Pipedrive access token is required and cannot be empty")
        if not api_domain:
            raise ValueError("Pipedrive API domain is required and cannot be empty")

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
        use_v2: bool = True,
    ) -> dict[str, Any]:
        """Make a request to the Pipedrive API.

        Args:
            endpoint: API endpoint path (e.g., "/deals")
            method: HTTP method (GET, POST)
            params: Optional query parameters
            json_body: Optional JSON body for POST requests
            resource_type: Optional resource type for 404 handling
            resource_id: Optional resource ID for 404 handling
            use_v2: Whether to use v2 API (default True for cursor pagination)

        Returns:
            API response as dict

        Raises:
            RateLimitedError: When rate limited by Pipedrive
            requests.exceptions.HTTPError: For other HTTP errors
        """
        api_version = "v2" if use_v2 else "v1"
        url = f"{self.api_domain}/api/{api_version}{endpoint}"

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
                retry_after: float | None = None
                if retry_after_str:
                    try:
                        # Pipedrive may return seconds or timestamp
                        retry_after = float(retry_after_str)
                    except ValueError:
                        try:
                            retry_time = parse_iso_timestamp(retry_after_str)
                            retry_after = max(0, (retry_time - datetime.now(UTC)).total_seconds())
                        except (ValueError, TypeError):
                            retry_after = 2.0  # Default to 2 seconds (burst window)
                logger.warning("Pipedrive API rate limit hit")
                raise RateLimitedError(
                    retry_after=retry_after, message="Pipedrive rate limit exceeded"
                )

            # Check for not found (404)
            if response.status_code == 404:
                if resource_type and resource_id:
                    logger.warning(f"Pipedrive {resource_type} {resource_id} not found")
                response.raise_for_status()

            # Check for unauthorized (401)
            if response.status_code == 401:
                logger.error("Pipedrive API unauthorized - invalid or expired access token")
                response.raise_for_status()

            response.raise_for_status()

            # Handle empty responses
            if not response.content:
                return {}

            return response.json()

        except RateLimitedError:
            raise
        except requests.exceptions.HTTPError:
            logger.error(f"Pipedrive API HTTP error: {response.status_code} - {response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Pipedrive API request error: {e}")
            raise

    # =========================================================================
    # Deals API (v2 with cursor pagination)
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_deals(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        cursor: str | None = None,
        updated_after: datetime | None = None,
        status: str | None = None,
    ) -> PipedriveSearchResult:
        """Get deals with cursor-based pagination.

        Args:
            limit: Maximum deals per page (default 100, max 500)
            cursor: Pagination cursor from previous response
            updated_after: Filter for deals updated after this time
            status: Filter by deal status (open, won, lost, deleted)

        Returns:
            PipedriveSearchResult with deals and next_cursor
        """
        params: dict[str, Any] = {"limit": min(limit, MAX_ALLOWED_LIMIT)}

        if cursor:
            params["cursor"] = cursor

        if updated_after:
            params["updated_since"] = updated_after.strftime("%Y-%m-%dT%H:%M:%SZ")

        if status:
            params["status"] = status

        response = self._make_request("/deals", params=params, use_v2=True)

        items = response.get("data") or []
        logger.debug(f"Retrieved {len(items)} deals")

        return PipedriveSearchResult(
            items=items,
            next_cursor=response.get("additional_data", {}).get("next_cursor"),
            additional_data=response.get("additional_data"),
        )

    def iterate_deals(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        start_cursor: str | None = None,
        updated_after: datetime | None = None,
        status: str | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all deals.

        Yields pages of deals until exhausted.

        Args:
            limit: Deals per page
            start_cursor: Optional cursor to resume from
            updated_after: Filter for deals updated after this time
            status: Filter by deal status

        Yields:
            Lists of deal dictionaries
        """
        cursor: str | None = start_cursor

        while True:
            result = self.get_deals(
                limit=limit,
                cursor=cursor,
                updated_after=updated_after,
                status=status,
            )

            if result.items:
                yield result.items

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    def iterate_deals_with_cursor(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        start_cursor: str | None = None,
        updated_after: datetime | None = None,
        status: str | None = None,
    ) -> Iterator[PipedriveSearchResult]:
        """Iterate through all deals, yielding full results with cursors.

        Similar to iterate_deals but yields PipedriveSearchResult objects that include
        the next_cursor, allowing callers to save progress for resumable backfills.
        """
        cursor: str | None = start_cursor

        while True:
            result = self.get_deals(
                limit=limit,
                cursor=cursor,
                updated_after=updated_after,
                status=status,
            )

            if result.items:
                yield result

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    @rate_limited(max_retries=5, base_delay=2)
    def get_deal(self, deal_id: int) -> dict[str, Any] | None:
        """Get a single deal by ID.

        Args:
            deal_id: The deal ID

        Returns:
            Deal data dictionary or None if not found
        """
        # Use v2 API with ids filter for consistent field names
        response = self._make_request(
            "/deals",
            params={"ids": str(deal_id), "limit": 1},
            use_v2=True,
            resource_type="deal",
            resource_id=str(deal_id),
        )

        data = response.get("data") or []
        return data[0] if data else None

    # =========================================================================
    # Persons API (v2 with cursor pagination)
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_persons(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        cursor: str | None = None,
        updated_after: datetime | None = None,
    ) -> PipedriveSearchResult:
        """Get persons with cursor-based pagination.

        Args:
            limit: Maximum persons per page (default 100, max 500)
            cursor: Pagination cursor from previous response
            updated_after: Filter for persons updated after this time

        Returns:
            PipedriveSearchResult with persons and next_cursor
        """
        params: dict[str, Any] = {"limit": min(limit, MAX_ALLOWED_LIMIT)}

        if cursor:
            params["cursor"] = cursor

        if updated_after:
            params["updated_since"] = updated_after.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = self._make_request("/persons", params=params, use_v2=True)

        items = response.get("data") or []
        logger.debug(f"Retrieved {len(items)} persons")

        return PipedriveSearchResult(
            items=items,
            next_cursor=response.get("additional_data", {}).get("next_cursor"),
            additional_data=response.get("additional_data"),
        )

    def iterate_persons(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        start_cursor: str | None = None,
        updated_after: datetime | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all persons."""
        cursor: str | None = start_cursor

        while True:
            result = self.get_persons(
                limit=limit,
                cursor=cursor,
                updated_after=updated_after,
            )

            if result.items:
                yield result.items

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    def iterate_persons_with_cursor(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        start_cursor: str | None = None,
        updated_after: datetime | None = None,
    ) -> Iterator[PipedriveSearchResult]:
        """Iterate through all persons, yielding full results with cursors."""
        cursor: str | None = start_cursor

        while True:
            result = self.get_persons(
                limit=limit,
                cursor=cursor,
                updated_after=updated_after,
            )

            if result.items:
                yield result

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    @rate_limited(max_retries=5, base_delay=2)
    def get_person(self, person_id: int) -> dict[str, Any] | None:
        """Get a single person by ID.

        Returns:
            Person data dictionary or None if not found
        """
        # Use v2 API with ids filter for consistent field names (emails/phones)
        response = self._make_request(
            "/persons",
            params={"ids": str(person_id), "limit": 1},
            use_v2=True,
            resource_type="person",
            resource_id=str(person_id),
        )

        data = response.get("data") or []
        return data[0] if data else None

    # =========================================================================
    # Organizations API (v2 with cursor pagination)
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_organizations(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        cursor: str | None = None,
        updated_after: datetime | None = None,
    ) -> PipedriveSearchResult:
        """Get organizations with cursor-based pagination.

        Args:
            limit: Maximum organizations per page (default 100, max 500)
            cursor: Pagination cursor from previous response
            updated_after: Filter for organizations updated after this time

        Returns:
            PipedriveSearchResult with organizations and next_cursor
        """
        params: dict[str, Any] = {"limit": min(limit, MAX_ALLOWED_LIMIT)}

        if cursor:
            params["cursor"] = cursor

        if updated_after:
            params["updated_since"] = updated_after.strftime("%Y-%m-%dT%H:%M:%SZ")

        response = self._make_request("/organizations", params=params, use_v2=True)

        items = response.get("data") or []
        logger.debug(f"Retrieved {len(items)} organizations")

        return PipedriveSearchResult(
            items=items,
            next_cursor=response.get("additional_data", {}).get("next_cursor"),
            additional_data=response.get("additional_data"),
        )

    def iterate_organizations(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        start_cursor: str | None = None,
        updated_after: datetime | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all organizations."""
        cursor: str | None = start_cursor

        while True:
            result = self.get_organizations(
                limit=limit,
                cursor=cursor,
                updated_after=updated_after,
            )

            if result.items:
                yield result.items

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    def iterate_organizations_with_cursor(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        start_cursor: str | None = None,
        updated_after: datetime | None = None,
    ) -> Iterator[PipedriveSearchResult]:
        """Iterate through all organizations, yielding full results with cursors."""
        cursor: str | None = start_cursor

        while True:
            result = self.get_organizations(
                limit=limit,
                cursor=cursor,
                updated_after=updated_after,
            )

            if result.items:
                yield result

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    @rate_limited(max_retries=5, base_delay=2)
    def get_organization(self, org_id: int) -> dict[str, Any] | None:
        """Get a single organization by ID.

        Returns:
            Organization data dictionary or None if not found
        """
        # Use v2 API with ids filter for consistent field names
        response = self._make_request(
            "/organizations",
            params={"ids": str(org_id), "limit": 1},
            use_v2=True,
            resource_type="organization",
            resource_id=str(org_id),
        )

        data = response.get("data") or []
        return data[0] if data else None

    # =========================================================================
    # Products API (v1 with offset pagination)
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_products(
        self,
        start: int = 0,
        limit: int = MAX_RECORDS_PER_PAGE,
        updated_after: datetime | None = None,
    ) -> PipedriveSearchResult:
        """Get products with offset-based pagination.

        Args:
            start: Offset for pagination
            limit: Maximum products per page (default 100, max 500)
            updated_after: Filter for products updated after this time (client-side filtering)

        Returns:
            PipedriveSearchResult with products and pagination info
        """
        params: dict[str, Any] = {
            "start": start,
            "limit": min(limit, MAX_ALLOWED_LIMIT),
        }

        response = self._make_request("/products", params=params, use_v2=False)

        additional_data = response.get("additional_data", {})
        pagination = additional_data.get("pagination", {})

        # For offset-based pagination, check if there are more items
        next_cursor = None
        if pagination.get("more_items_in_collection"):
            next_cursor = str(pagination.get("next_start", start + limit))

        items = response.get("data") or []

        # Client-side filtering for updated_after since v1 API doesn't support it
        if updated_after and items:
            filtered_items = []
            for item in items:
                update_time_str = item.get("update_time")
                if update_time_str:
                    try:
                        # Parse and ensure timezone-aware (Pipedrive returns "YYYY-MM-DD HH:MM:SS")
                        update_time = datetime.fromisoformat(
                            update_time_str.replace("Z", "+00:00").replace(" ", "T")
                        )
                        # If naive datetime, assume UTC
                        if update_time.tzinfo is None:
                            update_time = update_time.replace(tzinfo=UTC)
                        if update_time > updated_after:
                            filtered_items.append(item)
                    except (ValueError, TypeError):
                        # If we can't parse the date, include the item
                        filtered_items.append(item)
                else:
                    # No update_time, include the item
                    filtered_items.append(item)
            items = filtered_items

        logger.debug(f"Retrieved {len(items)} products")

        return PipedriveSearchResult(
            items=items,
            next_cursor=next_cursor,
            additional_data=additional_data,
        )

    def iterate_products(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        updated_after: datetime | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all products.

        Args:
            limit: Products per page
            updated_after: Filter for products updated after this time (client-side filtering)

        Yields:
            Lists of product dictionaries
        """
        start = 0

        while True:
            result = self.get_products(
                start=start,
                limit=limit,
                updated_after=updated_after,
            )

            if result.items:
                yield result.items

            if not result.next_cursor:
                break

            start = int(result.next_cursor)

    @rate_limited(max_retries=5, base_delay=2)
    def get_product(self, product_id: int) -> dict[str, Any]:
        """Get a single product by ID."""
        response = self._make_request(
            f"/products/{product_id}",
            use_v2=False,
            resource_type="product",
            resource_id=str(product_id),
        )

        return response.get("data", {})

    # =========================================================================
    # Activities API (v2 with cursor pagination)
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_activities(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        cursor: str | None = None,
        updated_after: datetime | None = None,
        deal_id: int | None = None,
        person_id: int | None = None,
        org_id: int | None = None,
    ) -> PipedriveSearchResult:
        """Get activities with cursor-based pagination.

        Args:
            limit: Maximum activities per page (default 100, max 500)
            cursor: Pagination cursor from previous response
            updated_after: Filter for activities updated after this time
            deal_id: Filter by deal ID
            person_id: Filter by person ID
            org_id: Filter by organization ID

        Returns:
            PipedriveSearchResult with activities and next_cursor
        """
        params: dict[str, Any] = {"limit": min(limit, MAX_ALLOWED_LIMIT)}

        if cursor:
            params["cursor"] = cursor

        if updated_after:
            params["updated_since"] = updated_after.strftime("%Y-%m-%dT%H:%M:%SZ")

        if deal_id:
            params["deal_id"] = deal_id

        if person_id:
            params["person_id"] = person_id

        if org_id:
            params["org_id"] = org_id

        response = self._make_request("/activities", params=params, use_v2=True)

        items = response.get("data") or []
        logger.debug(f"Retrieved {len(items)} activities")

        return PipedriveSearchResult(
            items=items,
            next_cursor=response.get("additional_data", {}).get("next_cursor"),
            additional_data=response.get("additional_data"),
        )

    def iterate_activities(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        start_cursor: str | None = None,
        updated_after: datetime | None = None,
        deal_id: int | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all activities."""
        cursor: str | None = start_cursor

        while True:
            result = self.get_activities(
                limit=limit,
                cursor=cursor,
                updated_after=updated_after,
                deal_id=deal_id,
            )

            if result.items:
                yield result.items

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    def get_activities_for_deal(self, deal_id: int) -> list[dict[str, Any]]:
        """Get all activities attached to a specific deal."""
        all_activities: list[dict[str, Any]] = []
        for page in self.iterate_activities(deal_id=deal_id):
            all_activities.extend(page)
        return all_activities

    # =========================================================================
    # Notes API (v1 - no cursor pagination in v2)
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_notes(
        self,
        start: int = 0,
        limit: int = MAX_RECORDS_PER_PAGE,
        deal_id: int | None = None,
        person_id: int | None = None,
        org_id: int | None = None,
    ) -> PipedriveSearchResult:
        """Get notes with offset-based pagination (v1 API).

        Args:
            start: Offset for pagination
            limit: Maximum notes per page (default 100, max 500)
            deal_id: Filter by deal ID
            person_id: Filter by person ID
            org_id: Filter by organization ID

        Returns:
            PipedriveSearchResult with notes and pagination info
        """
        params: dict[str, Any] = {
            "start": start,
            "limit": min(limit, MAX_ALLOWED_LIMIT),
        }

        if deal_id:
            params["deal_id"] = deal_id

        if person_id:
            params["person_id"] = person_id

        if org_id:
            params["org_id"] = org_id

        response = self._make_request("/notes", params=params, use_v2=False)

        additional_data = response.get("additional_data", {})
        pagination = additional_data.get("pagination", {})

        # For offset-based pagination, we need to check if there are more items
        next_cursor = None
        if pagination.get("more_items_in_collection"):
            next_cursor = str(pagination.get("next_start", start + limit))

        items = response.get("data") or []
        logger.debug(f"Retrieved {len(items)} notes")

        return PipedriveSearchResult(
            items=items,
            next_cursor=next_cursor,
            additional_data=additional_data,
        )

    def iterate_notes(
        self,
        limit: int = MAX_RECORDS_PER_PAGE,
        deal_id: int | None = None,
        person_id: int | None = None,
        org_id: int | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all notes."""
        start = 0

        while True:
            result = self.get_notes(
                start=start,
                limit=limit,
                deal_id=deal_id,
                person_id=person_id,
                org_id=org_id,
            )

            if result.items:
                yield result.items

            if not result.next_cursor:
                break

            start = int(result.next_cursor)

    def get_notes_for_deal(self, deal_id: int) -> list[dict[str, Any]]:
        """Get all notes attached to a specific deal."""
        all_notes: list[dict[str, Any]] = []
        for page in self.iterate_notes(deal_id=deal_id):
            all_notes.extend(page)
        return all_notes

    # =========================================================================
    # Users API (v1)
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_users(self) -> list[dict[str, Any]]:
        """Get all users in the company.

        Returns:
            List of user dictionaries
        """
        response = self._make_request("/users", use_v2=False)

        users = response.get("data") or []
        logger.debug(f"Retrieved {len(users)} users")

        return users

    @rate_limited(max_retries=5, base_delay=2)
    def get_user(self, user_id: int) -> dict[str, Any]:
        """Get a single user by ID."""
        response = self._make_request(
            f"/users/{user_id}",
            use_v2=False,
            resource_type="user",
            resource_id=str(user_id),
        )

        return response.get("data", {})

    # =========================================================================
    # Fields API (for label definitions)
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_person_fields(self) -> list[dict[str, Any]]:
        """Get all person fields including label definitions.

        Returns:
            List of person field definitions
        """
        response = self._make_request("/personFields", use_v2=False)
        return response.get("data") or []

    def get_person_label_map(self) -> dict[int, str]:
        """Get a mapping of person label IDs to label names.

        Returns:
            Dictionary mapping label ID to label name
        """
        fields = self.get_person_fields()
        label_map: dict[int, str] = {}

        for field in fields:
            if field.get("key") == "label":
                options = field.get("options") or []
                for option in options:
                    label_id = option.get("id")
                    label_name = option.get("label")
                    if label_id is not None and label_name:
                        label_map[label_id] = label_name
                break

        return label_map

    # =========================================================================
    # Company Info
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def get_current_user(self) -> dict[str, Any]:
        """Get the current authenticated user (me).

        Returns:
            Current user data dictionary
        """
        response = self._make_request("/users/me", use_v2=False)
        return response.get("data", {})


# Retry delay for OAuth timeouts - >30s to trigger SQS visibility extension
# (see src/utils/rate_limiter.py - ExtendVisibilityException threshold is 30s)
OAUTH_TIMEOUT_RETRY_SECONDS = 35


@rate_limited(max_retries=3, base_delay=5)
async def _refresh_pipedrive_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    """Exchange refresh token for new access token.

    Uses @rate_limited decorator for retry logic on transient errors.

    Args:
        refresh_token: Pipedrive refresh token
        client_id: Pipedrive OAuth client ID
        client_secret: Pipedrive OAuth client secret

    Returns:
        Token response with access_token, refresh_token, expires_in, api_domain

    Raises:
        ValueError: If token refresh fails (non-retryable errors)
        RateLimitedError: For transient errors that should be retried
    """
    import base64

    # Pipedrive requires Basic auth with client_id:client_secret
    basic_auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    try:
        response = requests.post(
            PIPEDRIVE_OAUTH_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            headers={
                "Authorization": f"Basic {basic_auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=60.0,
        )
    except requests.exceptions.Timeout:
        logger.warning("Pipedrive OAuth token refresh timed out, will retry")
        raise RateLimitedError(
            retry_after=OAUTH_TIMEOUT_RETRY_SECONDS,
            message="Pipedrive OAuth timeout",
        )
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Pipedrive OAuth connection error: {e}, will retry")
        raise RateLimitedError(
            retry_after=OAUTH_TIMEOUT_RETRY_SECONDS,
            message=f"Pipedrive OAuth connection error: {e}",
        )

    if response.status_code == 200:
        return response.json()

    # Non-retryable auth errors
    if response.status_code in (400, 401, 403):
        logger.error(
            "Pipedrive token refresh failed (non-retryable)",
            status_code=response.status_code,
            response=response.text,
        )
        raise ValueError(
            f"Pipedrive token refresh failed: {response.status_code} - {response.text}"
        )

    # Retryable server errors (5xx, etc.)
    logger.warning(
        "Pipedrive token refresh server error, will retry",
        status_code=response.status_code,
    )
    raise RateLimitedError(
        retry_after=OAUTH_TIMEOUT_RETRY_SECONDS,
        message=f"Pipedrive OAuth server error: {response.status_code}",
    )


async def get_pipedrive_client_for_tenant(tenant_id: str, ssm_client: SSMClient) -> PipedriveClient:
    """Factory method to get Pipedrive client with fresh OAuth access token.

    This uses the refresh token flow to get a fresh access token on every call,
    similar to how Salesforce handles OAuth. This ensures tokens are always valid.

    Args:
        tenant_id: Tenant ID
        ssm_client: SSM client for retrieving and storing secrets

    Returns:
        PipedriveClient configured with valid access token

    Raises:
        ValueError: If credentials are not found for the tenant or refresh fails
    """
    # Get refresh token from SSM Parameter Store
    refresh_token = await ssm_client.get_api_key(tenant_id, "PIPEDRIVE_REFRESH_TOKEN")

    if not refresh_token:
        raise ValueError(f"No Pipedrive refresh token configured for tenant {tenant_id}")

    # Get API domain from database (non-sensitive config)
    api_domain = await get_tenant_config_value("PIPEDRIVE_API_DOMAIN", tenant_id)

    if not api_domain:
        raise ValueError(f"No Pipedrive API domain configured for tenant {tenant_id}")

    # Get OAuth client credentials from environment
    client_id = os.environ.get("PIPEDRIVE_CLIENT_ID")
    client_secret = os.environ.get("PIPEDRIVE_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise ValueError(
            "PIPEDRIVE_CLIENT_ID and PIPEDRIVE_CLIENT_SECRET environment variables are required"
        )

    # Exchange refresh token for fresh access token
    logger.info("Refreshing Pipedrive access token", tenant_id=tenant_id)
    token_response = await _refresh_pipedrive_token(refresh_token, client_id, client_secret)

    access_token = token_response["access_token"]
    new_refresh_token = token_response.get("refresh_token", refresh_token)
    response_api_domain = token_response.get("api_domain", api_domain)

    # Store the new tokens in SSM for future use
    await ssm_client.store_api_key(tenant_id, "PIPEDRIVE_ACCESS_TOKEN", access_token)
    if new_refresh_token != refresh_token:
        await ssm_client.store_api_key(tenant_id, "PIPEDRIVE_REFRESH_TOKEN", new_refresh_token)

    # Log credential source with token redaction
    redacted_token = (
        f"{access_token[:8]}...{access_token[-4:]}" if len(access_token) > 12 else "***"
    )

    logger.info(
        "Pipedrive client credentials loaded",
        tenant_id=tenant_id,
        token_source="Refresh token exchange",
        token_preview=redacted_token,
        api_domain=response_api_domain,
    )

    return PipedriveClient(access_token=access_token, api_domain=response_api_domain)
