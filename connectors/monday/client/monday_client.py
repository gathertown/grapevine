"""
Monday.com GraphQL API client.

Based on Monday.com API v2: https://developer.monday.com/api-reference/docs/introduction-to-graphql
Rate limits: Complexity-based (5M points/minute for app tokens)
"""

from collections.abc import Iterator
from http import HTTPStatus
from typing import Any

import requests

from connectors.monday.client.monday_models import MondayBoard
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError

logger = get_logger(__name__)

# Monday.com API configuration
MONDAY_API_URL = "https://api.monday.com/v2"
MONDAY_API_VERSION = "2024-01"
MAX_ITEMS_PER_PAGE = 100
MAX_UPDATES_PER_ITEM = 25  # Keep updates manageable per item
MAX_BOARDS_LIMIT = 500  # Max boards to fetch in one request
MAX_ACTIVITY_LOG_PAGES = 100  # Safety limit for pagination
DEFAULT_RETRY_AFTER_SECONDS = 60.0

# Document ID prefix for Monday items
MONDAY_ITEM_DOC_ID_PREFIX = "monday_item_"


class MondayClient:
    """A client for interacting with the Monday.com GraphQL API.

    Monday.com uses a complexity-based rate limiting system:
    - App tokens: 5,000,000 complexity points per minute
    - Each query has a complexity cost based on the fields requested

    Tokens do NOT expire and are valid until app uninstall.
    """

    API_URL = MONDAY_API_URL

    def __init__(self, access_token: str):
        if not access_token:
            raise ValueError("Monday.com access token is required and cannot be empty")

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": access_token,  # Monday uses token directly, no Bearer prefix
                "Content-Type": "application/json",
                "API-Version": MONDAY_API_VERSION,
            }
        )

    def _execute_query(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query against the Monday.com API.

        Args:
            query: GraphQL query string
            variables: Optional query variables

        Returns:
            Query response data

        Raises:
            RateLimitedError: When rate limited by Monday.com
            requests.exceptions.HTTPError: For other HTTP errors
        """
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        try:
            response = self.session.post(self.API_URL, json=payload, timeout=60.0)

            # Check for rate limiting
            if response.status_code == HTTPStatus.TOO_MANY_REQUESTS:
                retry_after_str = response.headers.get(
                    "Retry-After", str(DEFAULT_RETRY_AFTER_SECONDS)
                )
                try:
                    retry_after = float(retry_after_str)
                except ValueError:
                    retry_after = DEFAULT_RETRY_AFTER_SECONDS
                logger.warning("Monday.com API rate limit hit")
                raise RateLimitedError(
                    retry_after=retry_after, message="Monday.com rate limit exceeded"
                )

            # Check for unauthorized
            if response.status_code == HTTPStatus.UNAUTHORIZED:
                logger.error("Monday.com API unauthorized - invalid or expired access token")
                response.raise_for_status()

            response.raise_for_status()

            result = response.json()

            # Check for GraphQL errors
            if "errors" in result:
                errors = result["errors"]
                error_messages = [e.get("message", str(e)) for e in errors]

                # Check for complexity limit error
                if any("complexity" in msg.lower() for msg in error_messages):
                    logger.warning("Monday.com complexity limit hit")
                    raise RateLimitedError(
                        retry_after=60.0, message="Monday.com complexity limit exceeded"
                    )

                logger.error(f"Monday.com GraphQL errors: {error_messages}")
                raise ValueError(f"Monday.com API errors: {', '.join(error_messages)}")

            return result.get("data", {})

        except requests.exceptions.Timeout:
            logger.error("Monday.com API request timed out")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Monday.com API request failed: {e}")
            raise

    def get_boards(self, limit: int = MAX_BOARDS_LIMIT) -> list[MondayBoard]:
        """Get all boards accessible to the authenticated user.

        Args:
            limit: Maximum number of boards to return (default 100)

        Returns:
            List of MondayBoard objects
        """
        query = """
        query GetBoards($limit: Int!) {
            boards(limit: $limit) {
                id
                name
                description
                board_kind
                items_count
                workspace {
                    id
                    name
                }
            }
        }
        """

        result = self._execute_query(query, {"limit": limit})
        boards = []

        for board_data in result.get("boards", []):
            workspace = board_data.get("workspace")
            boards.append(
                MondayBoard(
                    id=int(board_data["id"]),
                    name=board_data.get("name", ""),
                    description=board_data.get("description"),
                    board_kind=board_data.get("board_kind", "public"),
                    workspace_id=int(workspace["id"]) if workspace else None,
                    workspace_name=workspace.get("name") if workspace else None,
                    item_count=board_data.get("items_count", 0),
                )
            )

        return boards

    def get_board_item_ids(self, board_id: int) -> list[int]:
        """Get all item IDs for a board.

        Uses cursor-based pagination for efficient querying.

        Args:
            board_id: Board ID to get items from

        Returns:
            List of item IDs
        """
        query = """
        query GetBoardItems($board_id: ID!, $cursor: String) {
            boards(ids: [$board_id]) {
                items_page(limit: 500, cursor: $cursor) {
                    cursor
                    items {
                        id
                    }
                }
            }
        }
        """

        all_item_ids: list[int] = []
        cursor: str | None = None

        while True:
            variables: dict[str, Any] = {"board_id": str(board_id)}
            if cursor:
                variables["cursor"] = cursor

            result = self._execute_query(query, variables)
            boards = result.get("boards", [])
            if not boards:
                break

            items_page = boards[0].get("items_page", {})
            items = items_page.get("items", [])

            for item in items:
                all_item_ids.append(int(item["id"]))

            cursor = items_page.get("cursor")
            if not cursor:
                break

            logger.debug(f"Fetched {len(all_item_ids)} items from board {board_id}")

        return all_item_ids

    def get_items_batch(self, item_ids: list[int]) -> list[dict[str, Any]]:
        """Get detailed item data for a batch of item IDs.

        Includes column values, updates, and metadata.

        Args:
            item_ids: List of item IDs to fetch (max 100 recommended)

        Returns:
            List of raw item data dicts
        """
        if not item_ids:
            return []

        query = """
        query GetItems($item_ids: [ID!]!) {
            items(ids: $item_ids) {
                id
                name
                state
                created_at
                updated_at
                relative_link
                board {
                    id
                    name
                    description
                    board_kind
                    workspace {
                        id
                        name
                        description
                    }
                }
                group {
                    id
                    title
                    color
                }
                column_values {
                    id
                    type
                    text
                    value
                    column {
                        title
                    }
                }
                updates(limit: 25) {
                    id
                    body
                    text_body
                    created_at
                    updated_at
                    creator {
                        id
                        name
                        email
                    }
                }
                creator {
                    id
                    name
                    email
                }
                subscribers {
                    id
                    name
                    email
                }
            }
        }
        """

        result = self._execute_query(query, {"item_ids": [str(id) for id in item_ids]})
        return result.get("items", [])

    def iterate_all_items(self, board_ids: list[int] | None = None) -> Iterator[dict[str, Any]]:
        """Iterate over all items, optionally filtered by board IDs.

        Yields items one at a time with full detail.

        Args:
            board_ids: Optional list of board IDs to filter by. If None, gets all boards.

        Yields:
            Raw item data dicts
        """
        if board_ids is None:
            boards = self.get_boards()
            board_ids = [b.id for b in boards]

        for board_id in board_ids:
            logger.info(f"Processing board {board_id}")
            item_ids = self.get_board_item_ids(board_id)
            logger.info(f"Found {len(item_ids)} items in board {board_id}")

            # Process in batches
            batch_size = MAX_ITEMS_PER_PAGE
            for i in range(0, len(item_ids), batch_size):
                batch_ids = item_ids[i : i + batch_size]
                items = self.get_items_batch(batch_ids)

                yield from items

    def collect_all_board_ids(self) -> list[int]:
        """Collect all board IDs accessible to the user.

        Returns:
            List of board IDs
        """
        boards = self.get_boards(limit=MAX_BOARDS_LIMIT)
        return [b.id for b in boards]

    def get_me(self) -> dict[str, Any]:
        """Get the current authenticated user info.

        Returns:
            User and account information
        """
        query = """
        query {
            me {
                id
                name
                email
                account {
                    id
                    name
                    slug
                }
            }
        }
        """
        result = self._execute_query(query)
        return result.get("me", {})

    # ========== Activity Logs ==========

    def get_activity_logs(
        self,
        board_id: int,
        from_time: str | None = None,
        to_time: str | None = None,
        limit: int = 1000,
        page: int = 1,
    ) -> list[dict[str, Any]]:
        """Get activity logs for a board.

        Activity logs provide a record of all changes made to a board,
        with native date filtering support.

        Args:
            board_id: Board ID to get activity logs for
            from_time: ISO8601 start time (e.g., "2025-01-01T00:00:00Z")
            to_time: ISO8601 end time (e.g., "2025-01-02T00:00:00Z")
            limit: Max logs to return (max 10000, default 1000)
            page: Page number for pagination (starts at 1)

        Returns:
            List of activity log entries with event, entity, user_id, etc.
        """
        # Build query with optional time filters
        query_parts = ["$board_id: ID!", "$limit: Int!", "$page: Int!"]
        var_parts = ["limit: $limit", "page: $page"]
        variables: dict[str, Any] = {
            "board_id": str(board_id),
            "limit": min(limit, 10000),
            "page": page,
        }

        if from_time:
            query_parts.append("$from: ISO8601DateTime")
            var_parts.append("from: $from")
            variables["from"] = from_time

        if to_time:
            query_parts.append("$to: ISO8601DateTime")
            var_parts.append("to: $to")
            variables["to"] = to_time

        query = f"""
        query GetActivityLogs({", ".join(query_parts)}) {{
            boards(ids: [$board_id]) {{
                activity_logs({", ".join(var_parts)}) {{
                    id
                    event
                    data
                    entity
                    user_id
                    account_id
                    created_at
                }}
            }}
        }}
        """

        result = self._execute_query(query, variables)
        boards = result.get("boards", [])

        if not boards:
            return []

        return boards[0].get("activity_logs", [])

    def get_all_activity_logs_since(
        self,
        board_id: int,
        from_time: str,
        to_time: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all activity logs for a board since a given time, handling pagination.

        Args:
            board_id: Board ID to get activity logs for
            from_time: ISO8601 start time
            to_time: Optional ISO8601 end time (defaults to now)

        Returns:
            All activity log entries in the time range
        """
        all_logs: list[dict[str, Any]] = []
        page = 1
        page_size = 1000

        while True:
            logs = self.get_activity_logs(
                board_id=board_id,
                from_time=from_time,
                to_time=to_time,
                limit=page_size,
                page=page,
            )

            if not logs:
                break

            all_logs.extend(logs)

            # If we got fewer than page_size, we've reached the end
            if len(logs) < page_size:
                break

            page += 1

            # Safety limit to prevent infinite loops
            if page > MAX_ACTIVITY_LOG_PAGES:
                logger.warning(f"Hit pagination limit for board {board_id} activity logs")
                break

        return all_logs

    def extract_item_ids_from_activity_logs(self, activity_logs: list[dict[str, Any]]) -> set[int]:
        """Extract unique item IDs from activity logs.

        Args:
            activity_logs: List of activity log entries

        Returns:
            Set of unique item IDs that were affected
        """
        item_ids: set[int] = set()

        for log in activity_logs:
            # entity is "pulse" for items, "board" for board-level events
            if log.get("entity") == "pulse":
                # The data field contains item info as JSON string
                data_str = log.get("data")
                if data_str:
                    try:
                        import json

                        data = json.loads(data_str) if isinstance(data_str, str) else data_str
                        # Item ID is typically in pulse_id or board_id depending on event
                        pulse_id = data.get("pulse_id") or data.get("item_id")
                        if pulse_id:
                            item_ids.add(int(pulse_id))
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue

        return item_ids

    # ========== Webhook Management ==========

    def create_webhook(
        self,
        board_id: int,
        url: str,
        event: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a webhook for a board.

        Args:
            board_id: Board ID to attach webhook to
            url: Callback URL for webhook events
            event: Event type to subscribe to (e.g., "change_column_value")
            config: Optional configuration for the webhook

        Returns:
            Created webhook data including webhook ID
        """
        # Build mutation with optional config
        if config:
            mutation = """
            mutation CreateWebhook($board_id: ID!, $url: String!, $event: WebhookEventType!, $config: JSON!) {
                create_webhook(board_id: $board_id, url: $url, event: $event, config: $config) {
                    id
                    board_id
                }
            }
            """
            variables = {
                "board_id": str(board_id),
                "url": url,
                "event": event,
                "config": config,
            }
        else:
            mutation = """
            mutation CreateWebhook($board_id: ID!, $url: String!, $event: WebhookEventType!) {
                create_webhook(board_id: $board_id, url: $url, event: $event) {
                    id
                    board_id
                }
            }
            """
            variables = {
                "board_id": str(board_id),
                "url": url,
                "event": event,
            }

        result = self._execute_query(mutation, variables)
        webhook = result.get("create_webhook", {})
        logger.info(f"Created Monday.com webhook {webhook.get('id')} for board {board_id}")
        return webhook

    def delete_webhook(self, webhook_id: int) -> bool:
        """Delete a webhook by ID.

        Args:
            webhook_id: Webhook ID to delete

        Returns:
            True if deletion was successful
        """
        mutation = """
        mutation DeleteWebhook($id: ID!) {
            delete_webhook(id: $id) {
                id
            }
        }
        """

        try:
            result = self._execute_query(mutation, {"id": str(webhook_id)})
            deleted = result.get("delete_webhook", {})
            if deleted.get("id"):
                logger.info(f"Deleted Monday.com webhook {webhook_id}")
                return True
            return False
        except Exception as e:
            logger.warning(f"Failed to delete webhook {webhook_id}: {e}")
            return False

    def list_webhooks(self, board_id: int) -> list[dict[str, Any]]:
        """List all webhooks for a board.

        Args:
            board_id: Board ID to list webhooks for

        Returns:
            List of webhook data dicts
        """
        query = """
        query GetWebhooks($board_id: ID!) {
            webhooks(board_id: $board_id) {
                id
                event
                config
            }
        }
        """

        result = self._execute_query(query, {"board_id": str(board_id)})
        return result.get("webhooks", [])
