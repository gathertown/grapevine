import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urljoin

import requests

from src.utils.logging import get_logger

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = get_logger(__name__)


class NotionPageSummary(TypedDict):
    id: str
    last_edited_time: str


class NotionClient:
    BASE_URL = "https://api.notion.com/v1/"
    API_VERSION = "2022-06-28"
    # Maximum page size as per Notion API limits. We always want to use the max page size
    # to avoid rate limits as much as possible.
    # https://developers.notion.com/reference/request-limits
    MAX_PAGE_SIZE = 100

    def __init__(self, token: str):
        if not token:
            raise ValueError("Notion token is required and cannot be empty")

        self.token = token
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Notion-Version": self.API_VERSION,
            }
        )

    def _make_request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        url = urljoin(self.BASE_URL, endpoint)

        if "timeout" not in kwargs:
            kwargs["timeout"] = 30

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            result = response.json()
            return result
        except requests.exceptions.Timeout:
            logger.error(f"Request to {url} timed out after {kwargs.get('timeout')} seconds")
            raise
        except requests.exceptions.HTTPError:
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 1))
                raise RateLimitedError(retry_after=retry_after)
            elif response.status_code == 401:
                raise ValueError("Invalid Notion token or insufficient permissions")
            else:
                logger.error(f"Notion API error: {response.status_code} - {response.text}")
                raise

    @rate_limited()
    def list_databases(self) -> dict[str, Any]:
        return self._make_request(
            "POST", "search", json={"filter": {"value": "database", "property": "object"}}
        )

    @rate_limited()
    def get_database(self, database_id: str) -> dict[str, Any]:
        return self._make_request("GET", f"databases/{database_id}")

    @rate_limited()
    def query_database(
        self,
        database_id: str,
        start_cursor: str | None = None,
        filter_obj: dict | None = None,
        sorts: list[dict] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"page_size": self.MAX_PAGE_SIZE}

        if start_cursor:
            payload["start_cursor"] = start_cursor
        if filter_obj:
            payload["filter"] = filter_obj
        if sorts:
            payload["sorts"] = sorts

        return self._make_request("POST", f"databases/{database_id}/query", json=payload)

    @rate_limited()
    def get_page(self, page_id: str) -> dict[str, Any]:
        return self._make_request("GET", f"pages/{page_id}")

    @rate_limited()
    def get_user(self, user_id: str) -> dict[str, Any]:
        return self._make_request("GET", f"users/{user_id}")

    @rate_limited()
    def get_bot_info(self) -> dict[str, Any]:
        """Get information about the authenticated bot/integration.

        Returns:
            Dictionary with bot user information including id (bot_user_id).
        """
        return self._make_request("GET", "users/me")

    @rate_limited()
    def list_users(self, start_cursor: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"page_size": self.MAX_PAGE_SIZE}
        if start_cursor:
            params["start_cursor"] = start_cursor
        return self._make_request("GET", "users", params=params)

    def get_all_users(self) -> Iterator[dict[str, Any]]:
        start_cursor = None

        while True:
            response = self.list_users(start_cursor=start_cursor)

            yield from response.get("results", [])

            if not response.get("has_more", False):
                break

            start_cursor = response.get("next_cursor")

    @rate_limited()
    def get_block(self, block_id: str) -> dict[str, Any]:
        """Get a single block by ID."""
        return self._make_request("GET", f"blocks/{block_id}")

    @rate_limited()
    def get_comments(self, block_id: str, start_cursor: str | None = None) -> dict[str, Any]:
        """Get comments for a block or page."""
        params: dict[str, Any] = {"block_id": block_id, "page_size": self.MAX_PAGE_SIZE}
        if start_cursor:
            params["start_cursor"] = start_cursor
        return self._make_request("GET", "comments", params=params)

    def get_all_comments(self, block_id: str) -> list[dict[str, Any]]:
        """Get all comments for a block or page (handles pagination)."""
        comments = []
        start_cursor = None

        while True:
            response = self.get_comments(block_id, start_cursor)
            comments.extend(response.get("results", []))

            if not response.get("has_more", False):
                break

            start_cursor = response.get("next_cursor")

        return comments

    @rate_limited()
    def get_page_blocks(self, page_id: str, start_cursor: str | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"page_size": self.MAX_PAGE_SIZE}
        if start_cursor:
            params["start_cursor"] = start_cursor

        return self._make_request("GET", f"blocks/{page_id}/children", params=params)

    @rate_limited()
    def search_pages(
        self,
        query: str | None = None,
        start_cursor: str | None = None,
        filter_obj: dict | None = None,
        sort: dict | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"page_size": self.MAX_PAGE_SIZE}

        if query:
            payload["query"] = query
        if start_cursor:
            payload["start_cursor"] = start_cursor
        if filter_obj:
            payload["filter"] = filter_obj
        if sort:
            payload["sort"] = sort

        return self._make_request("POST", "search", json=payload)

    def get_all_pages(
        self,
        database_id: str | None = None,
        filter_obj: dict | None = None,
        sorts: list[dict] | None = None,
    ) -> Iterator[NotionPageSummary]:
        start_cursor = None
        page_count = 0
        batch_count = 0

        logger.info("Starting to fetch all Notion pages...")

        while True:
            batch_count += 1
            logger.debug(
                f"Fetching page batch {batch_count} (cursor: {start_cursor[:20]}...)"
                if start_cursor
                else f"Fetching page batch {batch_count}"
            )

            if database_id:
                response = self.query_database(
                    database_id=database_id,
                    start_cursor=start_cursor,
                    filter_obj=filter_obj,
                    sorts=sorts,
                )
            else:
                response = self.search_pages(
                    start_cursor=start_cursor,
                    filter_obj=filter_obj or {"property": "object", "value": "page"},
                )

            batch_size = len(response.get("results", []))
            page_count += batch_size
            logger.info(f"Fetched batch {batch_count}: {batch_size} pages (total: {page_count})")

            for page_data in response.get("results", []):
                page_id: str | None = page_data.get("id")
                last_edited_time: str = str(page_data.get("last_edited_time", ""))

                if page_id:
                    yield NotionPageSummary(id=page_id, last_edited_time=last_edited_time)

            if not response.get("has_more", False):
                logger.info(
                    f"Finished fetching all pages. Total: {page_count} pages in {batch_count} batches"
                )
                break

            start_cursor = response.get("next_cursor")

    def get_page_content(self, page_id: str) -> list[dict[str, Any]]:
        blocks = []
        start_cursor = None

        while True:
            logger.info(f"Getting blocks for page {page_id} with start_cursor {start_cursor}")
            response = self.get_page_blocks(page_id, start_cursor=start_cursor)
            page_blocks = response.get("results", [])

            for block in page_blocks:
                block["nesting_level"] = 0
                blocks.append(block)

                if block.get("type") in ["child_page", "child_database"]:
                    block_title = block.get(block["type"], {}).get("title", "Untitled")
                    logger.debug(f"Skipping {block['type']} block: {block_title}")
                    continue

                if block.get("has_children", False):
                    children = self._get_block_children_recursive(block.get("id"), nesting_level=1)
                    logger.debug(f"Found {len(children)} children for block {block.get('id')}")
                    blocks.extend(children)

            if not response.get("has_more", False):
                logger.info(f"No more blocks for page {page_id}")
                break

            start_cursor = response.get("next_cursor")

        return blocks

    def _get_block_children_recursive(
        self, block_id: str, nesting_level: int = 1, depth: int = 0, max_depth: int = 10
    ) -> list[dict[str, Any]]:
        if depth >= max_depth:
            return []

        children = []
        start_cursor = None

        try:
            while True:
                response = self.get_page_blocks(block_id, start_cursor=start_cursor)
                child_blocks = response.get("results", [])

                for child in child_blocks:
                    child["nesting_level"] = nesting_level
                    children.append(child)

                    # Skip fetching children for child_page and child_database blocks to stay high level
                    if child.get("type") in ["child_page", "child_database"]:
                        block_title = child.get(child["type"], {}).get("title", "Untitled")
                        logger.debug(f"Skipping {child['type']} block in recursion: {block_title}")
                        continue

                    if child.get("has_children", False):
                        grandchildren = self._get_block_children_recursive(
                            child.get("id"), nesting_level + 1, depth + 1, max_depth
                        )
                        children.extend(grandchildren)

                if not response.get("has_more", False):
                    break

                start_cursor = response.get("next_cursor")

        except Exception as e:
            logger.warning(f"Failed to fetch children for block {block_id}: {e}")

        return children

    def add_nesting_levels(self, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        nesting_map = {}

        for block in blocks:
            block_id = block.get("id")
            parent = block.get("parent", {})

            if parent.get("type") == "page_id":
                nesting_map[block_id] = 0
            elif parent.get("type") == "block_id":
                parent_id = parent.get("block_id")
                parent_level = nesting_map.get(parent_id, 0)
                nesting_map[block_id] = parent_level + 1
            else:
                nesting_map[block_id] = 0

        enhanced_blocks = []
        for block in blocks:
            enhanced_block = block.copy()
            block_id = block.get("id")
            enhanced_block["nesting_level"] = nesting_map.get(block_id, 0)
            enhanced_blocks.append(enhanced_block)

        return enhanced_blocks

    def _extract_rich_text(self, rich_text_array: list[dict[str, Any]]) -> str:
        if not rich_text_array:
            return ""

        text_parts = []

        for text_obj in rich_text_array:
            if text_obj.get("type") == "text":
                content = text_obj["text"]["content"]

                annotations = text_obj.get("annotations", {})
                if annotations.get("bold"):
                    content = f"**{content}**"
                if annotations.get("italic"):
                    content = f"*{content}*"
                if annotations.get("strikethrough"):
                    content = f"~~{content}~~"
                if annotations.get("underline"):
                    content = f"<u>{content}</u>"
                if annotations.get("code"):
                    content = f"`{content}`"

                if text_obj["text"].get("link"):
                    url = text_obj["text"]["link"]["url"]
                    content = f"[{content}]({url})"

                text_parts.append(content)

            elif text_obj.get("type") == "mention":
                mention = text_obj.get("mention", {})
                mention_type = mention.get("type")

                if mention_type == "page":
                    content = text_obj.get("plain_text", "@page")
                elif mention_type == "user":
                    content = text_obj.get("plain_text", "@user")
                elif mention_type == "date":
                    content = text_obj.get("plain_text", "@date")
                else:
                    content = text_obj.get("plain_text", "@mention")

                text_parts.append(content)

            elif text_obj.get("type") == "equation":
                expression = text_obj.get("equation", {}).get("expression", "")
                text_parts.append(f"${expression}$")

        return "".join(text_parts)
