#!/usr/bin/env python
"""Simple Intercom Help Center articles fetcher for classic access tokens.

Usage:
    uv run python scripts/intercom/test_intercom_help_center.py \\
        --access-token <token> --per-page 5

The script intentionally avoids the OAuth flow and instead accepts the
"classic" (personal) Intercom access token so that customer success and support
folks can validate which articles are available before wiring the full
ingest pipeline.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import httpx

try:
    import markdownify
except ImportError:
    markdownify = None  # type: ignore[assignment]

INTERCOM_API_BASE = "https://api.intercom.io"


class IntercomClassicClient:
    """Tiny helper around the Intercom REST API."""

    def __init__(self, access_token: str, timeout: float = 15.0) -> None:
        token = (access_token or "").strip()
        if not token:
            raise ValueError("Intercom access token is required")

        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "intercom-classic-scripts/0.1",
            "Intercom-Version": "2.10",
        }
        self._client = httpx.Client(timeout=timeout)

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

    def list_articles(
        self,
        *,
        per_page: int = 5,
        starting_after: str | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"per_page": per_page, "order": order}
        if starting_after:
            params["starting_after"] = starting_after

        return self._request("GET", "/articles", params=params)

    def get_article(self, article_id: str) -> dict[str, Any]:
        """Get a specific article by ID."""
        return self._request("GET", f"/articles/{article_id}")

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.request(
            method,
            f"{INTERCOM_API_BASE}{path}",
            headers=self._headers,
            **kwargs,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - script only
            body = exc.response.text
            raise RuntimeError(
                f"Intercom API request failed: {exc.response.status_code} {body}"
            ) from exc

        return response.json()


def format_timestamp(ts: int | float | str | None) -> str | None:
    """Format timestamp to ISO format."""
    if ts is None:
        return None

    try:
        # If it's already a string, try to parse it
        if isinstance(ts, str):
            # Try Unix timestamp first
            if ts.isdigit():
                return datetime.fromtimestamp(int(ts), tz=UTC).isoformat()
            # Try ISO format
            try:
                datetime.fromisoformat(ts.replace("Z", "+00:00"))
                return ts
            except ValueError:
                pass
        # If it's a number, convert from Unix timestamp
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts, tz=UTC).isoformat()
    except (TypeError, ValueError):
        pass

    return None


def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown."""
    if not html:
        return ""

    # Use markdownify if available
    if markdownify:
        return markdownify.markdownify(html, heading_style="ATX")

    # Basic HTML tag removal as fallback
    import re

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", html)
    # Decode common HTML entities
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
    )
    return text.strip()


def format_article_markdown(
    article: dict[str, Any],
    article_detail: dict[str, Any] | None,
    index: int,
    total: int,
) -> str:
    """Format an article as markdown."""
    article_id = article.get("id", "unknown")
    title = article.get("title", "Untitled Article")
    state = article.get("state", "unknown")
    url = article.get("url")
    created_at = format_timestamp(article.get("created_at"))
    updated_at = format_timestamp(article.get("updated_at"))

    # Use detail if available, otherwise use summary
    article_data = article_detail if article_detail else article

    # Extract body content
    body = article_data.get("body", "")
    if isinstance(body, dict):
        body_html = body.get("text") or body.get("html") or body.get("plaintext") or ""
    elif isinstance(body, str):
        body_html = body
    else:
        body_html = ""

    # Convert HTML to markdown
    body_markdown = html_to_markdown(body_html) if body_html else ""

    # Extract author information
    author = article_data.get("author", {})
    author_id = None
    author_name = None
    author_email = None
    if isinstance(author, dict):
        author_id = author.get("id")
        author_name = author.get("name")
        author_email = author.get("email")

    # Extract parent (collection or section)
    parent = article_data.get("parent", {})
    parent_type = None
    parent_id = None
    parent_name = None
    if isinstance(parent, dict):
        parent_type = parent.get("type")
        parent_id = parent.get("id")
        parent_name = parent.get("name")

    lines = []
    lines.append(f"## Article {index}/{total}: {title}")
    lines.append("")
    lines.append("**Article summary:**")
    lines.append("")

    def append_summary(text: str) -> None:
        lines.append(f"- {text}")

    append_summary(f"**ID:** `{article_id}`")
    append_summary(f"**Title:** {title}")
    append_summary(f"**State:** {state}")
    if url:
        append_summary(f"**URL:** {url}")
    if author_name:
        author_line = f"**Author:** {author_name}"
        if author_email:
            author_line += f" ({author_email})"
        if author_id:
            author_line += f" [`{author_id}`]"
        append_summary(author_line)
    if parent_type and parent_id:
        parent_line = f"**Parent {parent_type.title()}:**"
        if parent_name:
            parent_line += f" {parent_name}"
        parent_line += f" [`{parent_id}`]"
        append_summary(parent_line)
    if created_at:
        append_summary(f"**Created (UTC):** {created_at}")
    if updated_at:
        append_summary(f"**Updated (UTC):** {updated_at}")

    # Extract additional metadata
    description = article_data.get("description")
    if description:
        append_summary(f"**Description:** {description}")

    # Extract statistics if available
    statistics = article_data.get("statistics", {})
    if isinstance(statistics, dict):
        view_count = statistics.get("views")
        if view_count is not None:
            append_summary(f"**Views:** {view_count}")

    lines.append("")
    lines.append("### Article Body")
    lines.append("")

    if body_markdown:
        lines.append(body_markdown)
    else:
        lines.append("*No body content available*")

    lines.append("")
    lines.append("<details><summary>Article metadata snapshot</summary>")
    lines.append("")

    metadata = {
        "ID": article_id,
        "Title": title,
        "State": state,
        "URL": url or "None",
        "Author ID": author_id or "None",
        "Author Name": author_name or "None",
        "Author Email": author_email or "None",
        "Parent Type": parent_type or "None",
        "Parent ID": parent_id or "None",
        "Parent Name": parent_name or "None",
        "Created": created_at or "None",
        "Updated": updated_at or "None",
        "Description": description or "None",
    }

    for label, value in metadata.items():
        lines.append(f"- **{label}:** {value}")

    lines.append("")
    lines.append("</details>")

    lines.append("---")  # Separator between articles
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Intercom Help Center articles using a classic access token",
    )
    parser.add_argument(
        "--access-token",
        help="Intercom classic access token (falls back to INTERCOM_ACCESS_TOKEN env var)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=5,
        help="Number of articles to fetch (default: 5)",
    )
    parser.add_argument(
        "--starting-after",
        help="Pagination cursor from previous run (optional)",
    )
    parser.add_argument(
        "--order",
        choices=("asc", "desc"),
        default="desc",
        help="Article order (default: desc)",
    )
    parser.add_argument(
        "--show-raw",
        action="store_true",
        help="Print the raw JSON response after the summary",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--create-markdown",
        action="store_true",
        help="Output articles in markdown format (automatically fetches full article details)",
    )
    parser.add_argument(
        "--article-id",
        help="Fetch a specific article by ID instead of listing articles",
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
        with IntercomClassicClient(access_token, timeout=args.timeout) as client:
            # If article-id is provided, fetch just that article
            if args.article_id:
                try:
                    article_detail = client.get_article(args.article_id)
                    article = article_detail.get("data", article_detail)
                    if args.create_markdown:
                        print(format_article_markdown(article, article_detail, 1, 1))
                    else:
                        print(f"✅ Retrieved article {args.article_id}")
                        print(json.dumps(article, indent=2))
                except Exception as e:
                    print(f"Failed to fetch article {args.article_id}: {e}", file=sys.stderr)
                    return 1
                return 0

            # Otherwise, list articles
            response = client.list_articles(
                per_page=args.per_page,
                starting_after=args.starting_after,
                order=args.order,
            )

            articles = response.get("data", [])

            article_details: list[tuple[dict[str, Any], dict[str, Any] | None]] = []

            if args.create_markdown:
                print(f"Fetching {len(articles)} article(s) and details...", file=sys.stderr)
            else:
                print(f"✅ Retrieved {len(articles)} article(s).\n")

            for idx, article in enumerate(articles, 1):
                article_id = article.get("id")
                article_detail: dict[str, Any] | None = None

                if not args.create_markdown:
                    title = article.get("title", "Untitled")
                    state = article.get("state", "unknown")
                    created_at = format_timestamp(article.get("created_at"))
                    updated_at = format_timestamp(article.get("updated_at"))
                    print(
                        f"[{idx}/{len(articles)}] id={article_id} state={state} "
                        f"created_at={created_at or article.get('created_at')} "
                        f"updated_at={updated_at or article.get('updated_at')} "
                        f"title={title!r}"
                    )
                    print()

                if args.create_markdown:
                    try:
                        print(
                            f"  Fetching full article details for {article_id}...",
                            file=sys.stderr,
                        )
                        article_detail = client.get_article(article_id)
                    except Exception as e:
                        print(f"⚠️  Failed to fetch article {article_id}: {e}", file=sys.stderr)
                        article_detail = None

                    article_details.append((article, article_detail))

            next_cursor = response.get("pages", {}).get("next", {}).get("starting_after")
            if not args.create_markdown:
                if next_cursor:
                    print(f"\nNext starting_after cursor: {next_cursor}")
                else:
                    print("\nNo additional pages reported.")

                if args.show_raw:
                    print("\nRaw response:\n")
                    print(json.dumps(response, indent=2))
            else:
                print("# Intercom Help Center Articles", file=sys.stderr)
                print("", file=sys.stderr)
                print(f"**Retrieved:** {len(articles)} article(s)", file=sys.stderr)
                print(
                    f"**Fetched:** {sum(1 for _, detail in article_details if detail is not None)} with full details",
                    file=sys.stderr,
                )
                print("", file=sys.stderr)
                print("---", file=sys.stderr)
                print("", file=sys.stderr)

                for idx, (article, article_detail) in enumerate(article_details, 1):
                    print(format_article_markdown(article, article_detail, idx, len(articles)))

                if next_cursor:
                    print("", file=sys.stderr)
                    print(f"**Next cursor:** `{next_cursor}`", file=sys.stderr)

    except Exception as exc:  # pragma: no cover - script only
        print(f"Failed to fetch articles: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
