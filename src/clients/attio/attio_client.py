"""
Attio API client for CRM data operations.

Based on Attio REST API v2: https://docs.attio.com/
Rate limits: 100 reads/sec, 25 writes/sec
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import requests
from pydantic import BaseModel

from connectors.base.utils import parse_iso_timestamp
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)

# Attio API configuration
ATTIO_API_BASE_URL = "https://api.attio.com/v2"
MAX_RECORDS_PER_PAGE = 100
MAX_NOTES_PER_PAGE = 50  # Notes endpoint has a lower limit than records
MAX_TASKS_PER_PAGE = 50  # Tasks endpoint also has a lower limit
OBJECT_CACHE_SIZE = 128  # LRU cache size for object metadata lookups


class AttioSearchResult(BaseModel):
    """Result from an Attio search/query operation."""

    records: list[dict[str, Any]]
    next_cursor: str | None


class AttioObject(BaseModel):
    """Attio object (standard or custom) metadata."""

    object_id: str
    workspace_id: str
    api_slug: str
    singular_noun: str
    plural_noun: str


class AttioWebhook(BaseModel):
    """Attio webhook configuration."""

    webhook_id: str
    workspace_id: str
    target_url: str
    status: str  # "active", "degraded", "inactive"
    created_at: str


class AttioClient:
    """A client for interacting with the Attio REST API.

    Attio uses Bearer token authentication (OAuth or API key).
    Rate limits: 100 reads/sec, 25 writes/sec.
    """

    API_BASE_URL = ATTIO_API_BASE_URL

    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Attio access token is required and cannot be empty")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
        )
        # LRU cache for object metadata lookups (reduces API calls during webhook processing)
        self._object_cache: dict[str, AttioObject] = {}
        self._object_cache_order: list[str] = []

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> dict[str, Any]:
        """Make a request to the Attio API.

        Args:
            endpoint: API endpoint path (e.g., "/objects/companies/records/query")
            method: HTTP method (GET, POST)
            params: Optional query parameters
            json_body: Optional JSON body for POST requests
            resource_type: Optional resource type for 404 handling
            resource_id: Optional resource ID for 404 handling

        Returns:
            API response as dict

        Raises:
            RateLimitedError: When rate limited by Attio
            requests.exceptions.HTTPError: For other HTTP errors
        """
        url = f"{self.API_BASE_URL}{endpoint}"

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
                        # Attio returns ISO 8601 timestamp
                        retry_time = parse_iso_timestamp(retry_after_str)
                        retry_after = max(0, (retry_time - datetime.now(UTC)).total_seconds())
                    except (ValueError, TypeError):
                        retry_after = 1.0
                logger.warning("Attio API rate limit hit")
                raise RateLimitedError(retry_after=retry_after, message="Attio rate limit exceeded")

            # Check for not found (404)
            if response.status_code == 404:
                if resource_type and resource_id:
                    logger.warning(f"Attio {resource_type} {resource_id} not found")
                response.raise_for_status()

            # Check for unauthorized (401)
            if response.status_code == 401:
                logger.error("Attio API unauthorized - invalid or expired access token")
                response.raise_for_status()

            response.raise_for_status()

            # Handle empty responses
            if not response.content:
                return {}

            return response.json()

        except RateLimitedError:
            raise
        except requests.exceptions.HTTPError:
            logger.error(f"Attio API HTTP error: {response.status_code} - {response.text}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Attio API request error: {e}")
            raise

    @rate_limited(max_retries=5, base_delay=2)
    def query_records(
        self,
        object_slug: str,
        limit: int = MAX_RECORDS_PER_PAGE,
        cursor: str | None = None,
        sorts: list[dict[str, Any]] | None = None,
        filter: dict[str, Any] | None = None,
    ) -> AttioSearchResult:
        """Query records for a given object type.

        Args:
            object_slug: The object type slug (e.g., "companies", "people", "deals")
            limit: Maximum records per page (default 100, max 100)
            cursor: Pagination cursor from previous response
            sorts: Optional sort configuration
            filter: Optional filter configuration (e.g., {"updated_at": {"$gte": "2024-01-01"}})

        Returns:
            AttioSearchResult with records and next_cursor
        """
        # Build request body
        body: dict[str, Any] = {"limit": min(limit, MAX_RECORDS_PER_PAGE)}

        if cursor:
            body["cursor"] = cursor

        if sorts:
            body["sorts"] = sorts
        else:
            # Default sort by created_at ascending for consistent pagination
            body["sorts"] = [{"attribute": "created_at", "direction": "asc"}]

        if filter:
            body["filter"] = filter

        response = self._make_request(
            f"/objects/{object_slug}/records/query",
            method="POST",
            json_body=body,
        )

        logger.debug(f"Retrieved {len(response.get('data', []))} {object_slug} records")

        return AttioSearchResult(
            records=response.get("data", []),
            next_cursor=response.get("pagination", {}).get("next_cursor"),
        )

    def iterate_records(
        self,
        object_slug: str,
        limit: int = MAX_RECORDS_PER_PAGE,
        sorts: list[dict[str, Any]] | None = None,
        start_cursor: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through all records for an object type.

        Yields pages of records until exhausted.

        Args:
            object_slug: The object type slug
            limit: Records per page
            sorts: Optional sort configuration
            start_cursor: Optional cursor to resume from (for resumable backfills)
            filter: Optional filter configuration

        Yields:
            Lists of record dictionaries
        """
        cursor: str | None = start_cursor

        while True:
            result = self.query_records(
                object_slug=object_slug,
                limit=limit,
                cursor=cursor,
                sorts=sorts,
                filter=filter,
            )

            if result.records:
                yield result.records

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    def iterate_records_with_cursor(
        self,
        object_slug: str,
        limit: int = MAX_RECORDS_PER_PAGE,
        sorts: list[dict[str, Any]] | None = None,
        start_cursor: str | None = None,
        filter: dict[str, Any] | None = None,
    ) -> Iterator[AttioSearchResult]:
        """Iterate through all records for an object type, yielding full results with cursors.

        Similar to iterate_records but yields AttioSearchResult objects that include
        the next_cursor, allowing callers to save progress for resumable backfills.

        Args:
            object_slug: The object type slug
            limit: Records per page
            sorts: Optional sort configuration
            start_cursor: Optional cursor to resume from
            filter: Optional filter configuration

        Yields:
            AttioSearchResult objects containing records and next_cursor
        """
        cursor: str | None = start_cursor

        while True:
            result = self.query_records(
                object_slug=object_slug,
                limit=limit,
                cursor=cursor,
                sorts=sorts,
                filter=filter,
            )

            if result.records:
                yield result

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    def collect_all_record_ids(
        self,
        object_slug: str,
        limit: int = MAX_RECORDS_PER_PAGE,
    ) -> list[str]:
        """Collect all record IDs for an object type without full record data.

        This is more efficient than fetching full records when you only need IDs
        for batch job splitting.

        Args:
            object_slug: The object type slug (e.g., "companies", "people", "deals")
            limit: Records per page (max 100)

        Returns:
            List of all record IDs
        """
        record_ids: list[str] = []

        for result in self.iterate_records_with_cursor(
            object_slug=object_slug,
            limit=limit,
        ):
            for record in result.records:
                # Extract record_id from the nested id structure
                record_id_data = record.get("id", {})
                if isinstance(record_id_data, dict):
                    record_id = record_id_data.get("record_id", "")
                else:
                    record_id = str(record_id_data) if record_id_data else ""

                if record_id:
                    record_ids.append(record_id)

        logger.info(f"Collected {len(record_ids)} {object_slug} record IDs")
        return record_ids

    @rate_limited(max_retries=5, base_delay=2)
    def get_record(
        self,
        object_slug: str,
        record_id: str,
    ) -> dict[str, Any]:
        """Get a single record by ID.

        Args:
            object_slug: The object type slug
            record_id: The record ID

        Returns:
            Record data dictionary
        """
        response = self._make_request(
            f"/objects/{object_slug}/records/{record_id}",
            method="GET",
            resource_type=object_slug,
            resource_id=record_id,
        )

        logger.debug(f"Retrieved {object_slug} record {record_id}")

        return response.get("data", {})

    def get_object(self, object_id_or_slug: str) -> AttioObject:
        """Get object metadata by ID (UUID) or slug.

        Uses an LRU cache to reduce API calls during webhook processing,
        where the same object may be looked up multiple times.

        Args:
            object_id_or_slug: The object UUID or slug (e.g., "companies", "people",
                              or "3723f7de-3313-4d89-b030-2ea167b0110a")

        Returns:
            AttioObject with metadata including api_slug
        """
        # Check cache first
        if object_id_or_slug in self._object_cache:
            logger.debug(f"Object cache hit for {object_id_or_slug}")
            return self._object_cache[object_id_or_slug]

        # Fetch from API
        attio_object = self._fetch_object(object_id_or_slug)

        # Add to cache with LRU eviction
        if object_id_or_slug not in self._object_cache:
            if len(self._object_cache) >= OBJECT_CACHE_SIZE:
                # Evict oldest entry
                oldest_key = self._object_cache_order.pop(0)
                del self._object_cache[oldest_key]
            self._object_cache_order.append(object_id_or_slug)
        self._object_cache[object_id_or_slug] = attio_object

        return attio_object

    @rate_limited(max_retries=5, base_delay=2)
    def _fetch_object(self, object_id_or_slug: str) -> AttioObject:
        """Fetch object metadata from API (internal, rate-limited).

        Args:
            object_id_or_slug: The object UUID or slug

        Returns:
            AttioObject with metadata including api_slug
        """
        response = self._make_request(
            f"/objects/{object_id_or_slug}",
            method="GET",
            resource_type="object",
            resource_id=object_id_or_slug,
        )

        data = response.get("data", {})
        id_obj = data.get("id", {})

        return AttioObject(
            object_id=id_obj.get("object_id", ""),
            workspace_id=id_obj.get("workspace_id", ""),
            api_slug=data.get("api_slug", ""),
            singular_noun=data.get("singular_noun", ""),
            plural_noun=data.get("plural_noun", ""),
        )

    def clear_object_cache(self) -> None:
        """Clear the object metadata cache."""
        self._object_cache.clear()
        self._object_cache_order.clear()
        logger.debug("Cleared object cache")

    @rate_limited(max_retries=5, base_delay=2)
    def get_notes(
        self,
        parent_object: str | None = None,
        parent_record_id: str | None = None,
        limit: int = MAX_NOTES_PER_PAGE,
        cursor: str | None = None,
    ) -> AttioSearchResult:
        """Get notes, optionally filtered by parent record.

        Args:
            parent_object: Optional parent object slug (e.g., "deals")
            parent_record_id: Optional parent record ID
            limit: Maximum notes per page (max 50)
            cursor: Pagination cursor

        Returns:
            AttioSearchResult with notes and next_cursor
        """
        params: dict[str, Any] = {"limit": min(limit, MAX_NOTES_PER_PAGE)}

        if cursor:
            params["cursor"] = cursor

        if parent_object and parent_record_id:
            params["parent_object"] = parent_object
            params["parent_record_id"] = parent_record_id

        response = self._make_request("/notes", method="GET", params=params)

        logger.debug(f"Retrieved {len(response.get('data', []))} notes")

        return AttioSearchResult(
            records=response.get("data", []),
            next_cursor=response.get("pagination", {}).get("next_cursor"),
        )

    def iterate_notes(
        self,
        parent_object: str | None = None,
        parent_record_id: str | None = None,
        limit: int = MAX_RECORDS_PER_PAGE,
    ) -> Iterator[list[dict[str, Any]]]:
        """Iterate through notes, optionally filtered by parent.

        Yields pages of notes until exhausted.
        """
        cursor: str | None = None

        while True:
            result = self.get_notes(
                parent_object=parent_object,
                parent_record_id=parent_record_id,
                limit=limit,
                cursor=cursor,
            )

            if result.records:
                yield result.records

            if not result.next_cursor:
                break

            cursor = result.next_cursor

    @rate_limited(max_retries=5, base_delay=2)
    def get_tasks(
        self,
        linked_object: str | None = None,
        linked_record_id: str | None = None,
        limit: int = MAX_TASKS_PER_PAGE,
        cursor: str | None = None,
    ) -> AttioSearchResult:
        """Get tasks, optionally filtered by linked record.

        Args:
            linked_object: Optional linked object slug
            linked_record_id: Optional linked record ID
            limit: Maximum tasks per page (max 50)
            cursor: Pagination cursor

        Returns:
            AttioSearchResult with tasks and next_cursor
        """
        params: dict[str, Any] = {"limit": min(limit, MAX_TASKS_PER_PAGE)}

        if cursor:
            params["cursor"] = cursor

        if linked_object and linked_record_id:
            params["linked_object"] = linked_object
            params["linked_record_id"] = linked_record_id

        response = self._make_request("/tasks", method="GET", params=params)

        logger.debug(f"Retrieved {len(response.get('data', []))} tasks")

        return AttioSearchResult(
            records=response.get("data", []),
            next_cursor=response.get("pagination", {}).get("next_cursor"),
        )

    def get_notes_for_record(
        self,
        object_slug: str,
        record_id: str,
    ) -> list[dict[str, Any]]:
        """Get all notes attached to a specific record.

        Args:
            object_slug: The object type slug
            record_id: The record ID

        Returns:
            List of note dictionaries
        """
        all_notes: list[dict[str, Any]] = []
        for page in self.iterate_notes(
            parent_object=object_slug,
            parent_record_id=record_id,
        ):
            all_notes.extend(page)
        return all_notes

    def get_tasks_for_record(
        self,
        object_slug: str,
        record_id: str,
    ) -> list[dict[str, Any]]:
        """Get all tasks linked to a specific record.

        Args:
            object_slug: The object type slug
            record_id: The record ID

        Returns:
            List of task dictionaries
        """
        all_tasks: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            result = self.get_tasks(
                linked_object=object_slug,
                linked_record_id=record_id,
                cursor=cursor,
            )

            if result.records:
                all_tasks.extend(result.records)

            if not result.next_cursor:
                break

            cursor = result.next_cursor

        return all_tasks

    @rate_limited(max_retries=5, base_delay=2)
    def get_workspace_members(self) -> list[dict[str, Any]]:
        """Get all workspace members.

        Returns:
            List of workspace member dictionaries
        """
        response = self._make_request("/workspace_members", method="GET")

        logger.debug(f"Retrieved {len(response.get('data', []))} workspace members")

        return response.get("data", [])

    # =========================================================================
    # Webhook Management Methods
    # =========================================================================

    @rate_limited(max_retries=5, base_delay=2)
    def create_webhook(
        self,
        target_url: str,
        event_types: list[str] | None = None,
    ) -> AttioWebhook:
        """Create a webhook subscription.

        Args:
            target_url: HTTPS URL where webhook events will be delivered
            event_types: List of event types to subscribe to. Defaults to record events.
                Available: record.created, record.updated, record.deleted, record.merged,
                note.created, note.updated, note.deleted, task.created, task.updated, task.deleted

        Returns:
            AttioWebhook with webhook_id and other metadata

        Raises:
            ValueError: If target_url is not HTTPS
        """
        if not target_url.startswith("https://"):
            raise ValueError("Attio webhook target_url must use HTTPS")

        # Default to record and note events for CRM sync
        if event_types is None:
            event_types = [
                "record.created",
                "record.updated",
                "record.deleted",
                "note.created",
                "note.updated",
                "note.deleted",
                "task.created",
                "task.updated",
                "task.deleted",
            ]

        # Build subscriptions array - filter is null to receive all events
        subscriptions = [{"event_type": et, "filter": None} for et in event_types]

        body = {
            "data": {
                "target_url": target_url,
                "subscriptions": subscriptions,
            }
        }

        response = self._make_request("/webhooks", method="POST", json_body=body)

        data = response.get("data", {})
        webhook_id_obj = data.get("id", {})

        webhook = AttioWebhook(
            webhook_id=webhook_id_obj.get("webhook_id", ""),
            workspace_id=webhook_id_obj.get("workspace_id", ""),
            target_url=data.get("target_url", ""),
            status=data.get("status", ""),
            created_at=data.get("created_at", ""),
        )

        logger.info(
            f"Created Attio webhook {webhook.webhook_id}",
            target_url=target_url,
            event_types=event_types,
        )

        return webhook

    @rate_limited(max_retries=5, base_delay=2)
    def list_webhooks(self) -> list[AttioWebhook]:
        """List all webhooks in the workspace.

        Returns:
            List of AttioWebhook objects
        """
        response = self._make_request("/webhooks", method="GET")

        webhooks = []
        for item in response.get("data", []):
            webhook_id_obj = item.get("id", {})
            webhooks.append(
                AttioWebhook(
                    webhook_id=webhook_id_obj.get("webhook_id", ""),
                    workspace_id=webhook_id_obj.get("workspace_id", ""),
                    target_url=item.get("target_url", ""),
                    status=item.get("status", ""),
                    created_at=item.get("created_at", ""),
                )
            )

        logger.debug(f"Listed {len(webhooks)} Attio webhooks")
        return webhooks

    @rate_limited(max_retries=5, base_delay=2)
    def delete_webhook(self, webhook_id: str) -> None:
        """Delete a webhook subscription.

        Args:
            webhook_id: The webhook ID to delete
        """
        self._make_request(
            f"/webhooks/{webhook_id}",
            method="DELETE",
            resource_type="webhook",
            resource_id=webhook_id,
        )

        logger.info(f"Deleted Attio webhook {webhook_id}")

    def find_webhook_by_url(self, target_url: str) -> AttioWebhook | None:
        """Find webhook by target URL.

        Args:
            target_url: The target URL to search for

        Returns:
            AttioWebhook if found, None otherwise
        """
        webhooks = self.list_webhooks()
        for webhook in webhooks:
            if webhook.target_url == target_url:
                return webhook
        return None

    def ensure_webhook(self, target_url: str, event_types: list[str] | None = None) -> AttioWebhook:
        """Ensure a webhook exists for the given target URL.

        If a webhook already exists for this URL, returns it.
        Otherwise, creates a new webhook.

        Args:
            target_url: HTTPS URL where webhook events will be delivered
            event_types: List of event types to subscribe to

        Returns:
            AttioWebhook (existing or newly created)
        """
        existing = self.find_webhook_by_url(target_url)
        if existing:
            logger.info(f"Found existing Attio webhook {existing.webhook_id} for {target_url}")
            return existing

        return self.create_webhook(target_url, event_types)


async def get_attio_client_for_tenant(tenant_id: str, ssm_client: SSMClient) -> AttioClient:
    """Factory method to get Attio client with proper OAuth authentication.

    Args:
        tenant_id: Tenant ID
        ssm_client: SSM client for retrieving secrets

    Returns:
        AttioClient configured with valid access token

    Raises:
        ValueError: If no access token is found for the tenant
    """
    # Get access token from SSM Parameter Store
    access_token = await ssm_client.get_api_key(tenant_id, "ATTIO_ACCESS_TOKEN")

    if not access_token:
        raise ValueError(f"No Attio access token configured for tenant {tenant_id}")

    # Log credential source with token redaction
    redacted_token = (
        f"{access_token[:8]}...{access_token[-4:]}" if len(access_token) > 12 else "***"
    )

    logger.info(
        "Attio client credentials loaded",
        tenant_id=tenant_id,
        token_source="SSM Parameter Store",
        token_preview=redacted_token,
    )

    return AttioClient(access_token=access_token)
