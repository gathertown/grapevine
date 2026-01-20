#!/usr/bin/env python
"""Create test Help Center articles in Intercom for development/testing purposes.

Usage:
    uv run python scripts/intercom/create_intercom_test_articles.py \\
        --access-token <token> --count 5

This script creates random test Help Center articles in Intercom.
Useful for testing the ingestion pipeline when you don't have real article data.

WARNING: This will create real articles in your Intercom workspace!
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx

INTERCOM_API_BASE = "https://api.intercom.io"

# Path to sample data JSON file
SCRIPT_DIR = Path(__file__).parent
SAMPLE_DATA_FILE = SCRIPT_DIR / "intercom_sample_data.json"


def load_sample_data() -> dict[str, Any]:
    """Load sample data from JSON file.

    Returns:
        Dictionary with 'topics', 'customer_messages', and 'support_responses' lists

    Raises:
        FileNotFoundError: If the sample data file doesn't exist
        json.JSONDecodeError: If the JSON file is invalid
    """
    if not SAMPLE_DATA_FILE.exists():
        raise FileNotFoundError(
            f"Sample data file not found: {SAMPLE_DATA_FILE}. "
            "Please ensure intercom_sample_data.json exists in the same directory."
        )

    with open(SAMPLE_DATA_FILE) as f:
        data = json.load(f)

    # Validate structure
    required_keys = ["topics", "customer_messages", "support_responses"]
    for key in required_keys:
        if key not in data:
            raise ValueError(f"Sample data file missing required key: {key}")

    if not isinstance(data["topics"], list) or len(data["topics"]) == 0:
        raise ValueError("Sample data 'topics' must be a non-empty list")
    if not isinstance(data["customer_messages"], list) or len(data["customer_messages"]) == 0:
        raise ValueError("Sample data 'customer_messages' must be a non-empty list")
    if not isinstance(data["support_responses"], list) or len(data["support_responses"]) == 0:
        raise ValueError("Sample data 'support_responses' must be a non-empty list")

    return data


class IntercomClassicClient:
    """Tiny helper around the Intercom REST API."""

    def __init__(self, access_token: str, timeout: float = 15.0) -> None:
        token = (access_token or "").strip()
        if not token:
            raise ValueError("Intercom access token is required")

        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "intercom-classic-scripts/0.1",
            "Intercom-Version": "2.10",
        }
        self._client = httpx.Client(timeout=timeout)
        self._cached_admin_id: str | None = None
        self._cached_collection_id: str | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> IntercomClassicClient:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.close()

    def get_me(self) -> dict[str, Any]:
        """Get current admin/app information."""
        return self._request("GET", "/me")

    def _get_admin_id(self) -> str:
        """Get the current admin ID, caching it."""
        if self._cached_admin_id:
            return self._cached_admin_id

        me = self.get_me()
        admin_id = me.get("id") or me.get("app", {}).get("id")
        if not admin_id:
            raise ValueError("Could not determine admin ID from /me endpoint")
        self._cached_admin_id = str(admin_id)
        return self._cached_admin_id

    def get_or_create_collection(self, name: str = "Test Articles Collection") -> str:
        """Get or create a collection for articles.

        Args:
            name: Collection name

        Returns:
            Collection ID
        """
        if self._cached_collection_id:
            return self._cached_collection_id

        # Try to find existing collection
        try:
            response = self._request("GET", "/help_center/collections")
            collections = response.get("data", [])
            for collection in collections:
                if collection.get("name") == name:
                    self._cached_collection_id = str(collection.get("id"))
                    print(
                        f"  ✅ Found existing collection: {name} (ID: {self._cached_collection_id})",
                        file=sys.stderr,
                    )
                    return self._cached_collection_id
        except Exception as e:
            print(f"  Debug: Could not list collections: {e}", file=sys.stderr)

        # Create new collection
        try:
            body = {
                "name": name,
                "description": "Test articles collection for development and testing",
            }
            response = self._request("POST", "/help_center/collections", json=body)
            collection_id = response.get("id")
            if collection_id:
                self._cached_collection_id = str(collection_id)
                print(
                    f"  ✅ Created collection: {name} (ID: {self._cached_collection_id})",
                    file=sys.stderr,
                )
                return self._cached_collection_id
        except Exception as e:
            print(f"  ⚠️  Failed to create collection: {e}", file=sys.stderr)
            # If collection creation fails, we can still create articles without a parent
            return ""

        return ""

    def create_article(
        self,
        *,
        title: str,
        description: str,
        body: str,
        author_id: str,
        collection_id: str | None = None,
        state: str = "draft",
    ) -> dict[str, Any]:
        """Create a new Help Center article.

        Args:
            title: Article title
            description: Article description/summary
            body: Article body content (HTML)
            author_id: Author/admin ID
            collection_id: Optional collection ID to assign article to
            state: Article state ("draft" or "published")

        Returns:
            Created article data
        """
        body_data: dict[str, Any] = {
            "title": title,
            "description": description,
            "body": body,
            "author_id": int(author_id) if author_id.isdigit() else author_id,
            "state": state,
        }

        if collection_id:
            body_data["parent_type"] = "collection"
            body_data["parent_id"] = (
                int(collection_id) if collection_id.isdigit() else collection_id
            )

        return self._request("POST", "/articles", json=body_data)

    def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        response = self._client.request(
            method,
            f"{INTERCOM_API_BASE}{path}",
            headers=self._headers,
            json=json,
            **kwargs,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            body = exc.response.text
            raise RuntimeError(
                f"Intercom API request failed: {exc.response.status_code} {body}"
            ) from exc

        # Handle empty responses
        if not response.content:
            return {}

        return response.json()


def generate_article_content(sample_data: dict[str, Any], index: int) -> dict[str, Any]:
    """Generate article content from sample data.

    Args:
        sample_data: Sample data dictionary
        index: Article index number

    Returns:
        Dictionary with title, description, and body (HTML)
    """
    topic = random.choice(sample_data["topics"])
    title = f"Test Article {index}: {topic}"

    # Generate description from a random support response
    description = random.choice(sample_data["support_responses"])[:200]
    if len(description) > 200:
        description = description[:197] + "..."

    # Generate body content - combine multiple support responses
    body_parts = []
    body_parts.append(f"<h1>{title}</h1>")
    body_parts.append(f"<p>This is a test article about <strong>{topic}</strong>.</p>")

    # Add a few paragraphs from support responses
    num_paragraphs = random.randint(2, 4)
    for _ in range(num_paragraphs):
        response = random.choice(sample_data["support_responses"])
        body_parts.append(f"<p>{response}</p>")

    # Add a list
    body_parts.append("<h2>Key Points</h2>")
    body_parts.append("<ul>")
    for _ in range(random.randint(3, 6)):
        point = random.choice(sample_data["support_responses"])[:100]
        body_parts.append(f"<li>{point}</li>")
    body_parts.append("</ul>")

    # Add a final paragraph
    body_parts.append("<h2>Conclusion</h2>")
    body_parts.append(f"<p>{random.choice(sample_data['support_responses'])}</p>")

    body_html = "\n".join(body_parts)

    return {
        "title": title,
        "description": description,
        "body": body_html,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create test Help Center articles in Intercom",
    )
    parser.add_argument(
        "--access-token",
        help="Intercom classic access token (falls back to INTERCOM_ACCESS_TOKEN env var)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of articles to create (default: 5)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between API calls in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--state",
        choices=["draft", "published"],
        default="draft",
        help="Article state (default: draft)",
    )
    parser.add_argument(
        "--collection-name",
        default="Test Articles Collection",
        help="Collection name to use (default: 'Test Articles Collection')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without actually creating articles",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    access_token = args.access_token or os.environ.get("INTERCOM_ACCESS_TOKEN", "")

    if not access_token:
        print(
            "Error: provide --access-token or set INTERCOM_ACCESS_TOKEN in the environment.",
            file=sys.stderr,
        )
        return 1

    try:
        sample_data = load_sample_data()
        print(
            f"✅ Loaded sample data: {len(sample_data['topics'])} topics, "
            f"{len(sample_data['customer_messages'])} customer messages, "
            f"{len(sample_data['support_responses'])} support responses\n",
            file=sys.stderr,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"Error loading sample data: {e}", file=sys.stderr)
        return 1

    try:
        with IntercomClassicClient(access_token, timeout=args.timeout) as client:
            # Get admin ID
            try:
                admin_id = client._get_admin_id()
                print(f"✅ Using admin ID: {admin_id}\n", file=sys.stderr)
            except Exception as e:
                print(f"Error getting admin info: {e}", file=sys.stderr)
                return 1

            # Get or create collection
            collection_id = None
            if not args.dry_run:
                try:
                    collection_id = client.get_or_create_collection(args.collection_name)
                    if collection_id:
                        print("", file=sys.stderr)
                except Exception as e:
                    print(f"⚠️  Warning: Could not get/create collection: {e}", file=sys.stderr)
                    print("  Articles will be created without a collection\n", file=sys.stderr)

            if args.dry_run:
                print(f"DRY RUN: Would create {args.count} article(s)\n", file=sys.stderr)
                for i in range(1, args.count + 1):
                    content = generate_article_content(sample_data, i)
                    print(f"Article {i}:", file=sys.stderr)
                    print(f"  Title: {content['title']}", file=sys.stderr)
                    print(f"  Description: {content['description'][:50]}...", file=sys.stderr)
                    print(f"  State: {args.state}", file=sys.stderr)
                    print(
                        f"  Collection: {args.collection_name if collection_id else 'None'}",
                        file=sys.stderr,
                    )
                    print("", file=sys.stderr)
                return 0

            created_articles = []

            for i in range(1, args.count + 1):
                try:
                    # Generate article content
                    content = generate_article_content(sample_data, i)

                    print(f"Creating article {i}/{args.count}...", file=sys.stderr)
                    print(f"  Title: {content['title']}", file=sys.stderr)

                    # Create article
                    article = client.create_article(
                        title=content["title"],
                        description=content["description"],
                        body=content["body"],
                        author_id=admin_id,
                        collection_id=collection_id,
                        state=args.state,
                    )

                    article_id = article.get("id")
                    if not article_id:
                        print("⚠️  Warning: Could not get article ID from response", file=sys.stderr)
                        print(f"   Response: {json.dumps(article, indent=2)}", file=sys.stderr)
                        continue

                    print(f"  ✅ Created article: {article_id}", file=sys.stderr)
                    created_articles.append(article_id)

                    # Rate limiting
                    if i < args.count:
                        time.sleep(args.delay)

                    print("", file=sys.stderr)

                except Exception as e:
                    print(f"⚠️  Failed to create article {i}: {e}", file=sys.stderr)
                    continue

            print(f"Successfully created {len(created_articles)} articles.", file=sys.stderr)
            if created_articles:
                print("Created article IDs:", file=sys.stderr)
                for article_id in created_articles:
                    print(f"- {article_id}", file=sys.stderr)
            return 0

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
