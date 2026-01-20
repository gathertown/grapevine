#!/usr/bin/env python
"""Simple Intercom conversations fetcher for classic access tokens.

Usage:
    uv run python scripts/intercom/test_intercom_conversations.py \\
        --access-token <token> --per-page 5 --show-parts

The script intentionally avoids the OAuth flow and instead accepts the
"classic" (personal) Intercom access token so that customer success and support
folks can validate which conversations are available before wiring the full
ingest pipeline.

Use --show-parts to fetch and display conversation parts (messages/threads) for
each conversation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

import httpx

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

    def list_conversations(
        self,
        *,
        per_page: int = 5,
        starting_after: str | None = None,
        order: str = "desc",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"per_page": per_page, "order": order}
        if starting_after:
            params["starting_after"] = starting_after

        return self._request("GET", "/conversations", params=params)

    def get_conversation(self, conversation_id: str) -> dict[str, Any]:
        """Get a specific conversation by ID, including conversation parts."""
        return self._request("GET", f"/conversations/{conversation_id}")

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


def format_conversation_part(part: dict[str, Any]) -> str:
    """Format a conversation part (message) for display according to Intercom schema."""
    part_id = part.get("id", "unknown")
    part_type = part.get("part_type", "unknown")
    author = part.get("author", {})
    author_type = author.get("type", "unknown")
    author_name = author.get("name") or author.get("email") or "Unknown"
    created_at = part.get("created_at")
    body = part.get("body", "")

    # Extract text from body - Intercom returns HTML
    if isinstance(body, dict):
        text = body.get("text") or body.get("plaintext") or body.get("html", "")
        if isinstance(text, str) and len(text) > 200:
            text = text[:200] + "..."
        body = text
    elif isinstance(body, str):
        # Truncate long HTML/text content
        if len(body) > 200:
            body = body[:200] + "..."

    # Check for attachments
    attachments = part.get("attachments", [])
    attachment_info = ""
    if attachments:
        attachment_info = f" [{len(attachments)} attachment(s)]"

    # Check for tags
    tags = part.get("tags", [])
    tag_info = ""
    if tags:
        tag_names = [tag.get("name", "") for tag in tags if isinstance(tag, dict)]
        if tag_names:
            tag_info = f" [tags: {', '.join(tag_names)}]"

    # Check if from AI agent
    ai_info = ""
    if author.get("from_ai_agent") or part.get("is_ai_answer"):
        ai_info = " [AI]"

    return (
        f"  [{part_type}] id={part_id} | {author_type}:{author_name} @ {created_at}"
        f"{ai_info}{attachment_info}{tag_info}\n    {body}"
    )


def format_timestamp(ts: int | float | None) -> str | None:
    if ts is None:
        return None

    try:
        return datetime.fromtimestamp(ts, UTC).isoformat()
    except (TypeError, ValueError):
        return None


def format_entity_list(entities: list[dict[str, Any]] | None, label: str) -> str | None:
    if not entities:
        return None

    def _format(entity: dict[str, Any]) -> str:
        entity_id = entity.get("id") or entity.get("uuid") or entity.get("email") or "unknown"
        name = entity.get("name") or entity.get("email")
        if name and name != entity_id:
            return f"{name} (`{entity_id}`)"
        return f"`{entity_id}`"

    formatted = ", ".join(_format(e) for e in entities if isinstance(e, dict))
    return f"**{label}:** {formatted}" if formatted else None


def format_conversation_part_markdown(part: dict[str, Any], part_index: int) -> str:
    """Format a conversation part as markdown."""
    part_id = part.get("id", "unknown")
    part_type = part.get("part_type", "unknown")
    author = part.get("author", {})
    author_type = author.get("type", "unknown")
    author_name = author.get("name") or author.get("email") or "Unknown"
    author_email = author.get("email")
    created_at = format_timestamp(part.get("created_at"))
    body = part.get("body", "")

    # Extract text from body - Intercom returns HTML
    if isinstance(body, dict):
        body_text = body.get("text") or body.get("plaintext") or body.get("html", "")
    elif isinstance(body, str):
        body_text = body
    else:
        body_text = ""

    # Clean HTML tags for markdown (basic)
    if "<" in body_text and ">" in body_text:
        # Simple HTML tag removal - could be enhanced with html.parser
        body_text = re.sub(r"<[^>]+>", "", body_text)
        body_text = (
            body_text.replace("&nbsp;", " ")
            .replace("&amp;", "&")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
        )

    # Build the markdown
    lines = []
    lines.append(f"#### Part {part_index}: {part_type.title()}")

    # Author info
    ai_badge = " 🤖" if author.get("from_ai_agent") or part.get("is_ai_answer") else ""
    from_ai_agent = part.get("from_ai_agent") or author.get("from_ai_agent")
    is_ai_answer = part.get("is_ai_answer")
    author_line = f"**Author:** {author_type.title()}: {author_name}{ai_badge}"
    if author_email:
        author_line += f" ({author_email})"
    lines.append(author_line)
    if from_ai_agent is not None or is_ai_answer is not None:
        ai_fields = []
        if from_ai_agent is not None:
            ai_fields.append(f"from_ai_agent={from_ai_agent}")
        if is_ai_answer is not None:
            ai_fields.append(f"is_ai_answer={is_ai_answer}")
        lines.append(f"**AI Flags:** {', '.join(ai_fields)}")
    lines.append(f"**ID:** `{part_id}`")
    if created_at:
        lines.append(f"**Created (UTC):** {created_at}")

    # Attachments
    attachments = part.get("attachments", [])
    if attachments:
        lines.append(f"**Attachments:** {len(attachments)}")
        for att in attachments:
            att_name = att.get("name", "Unknown")
            att_url = att.get("url", "")
            if att_url:
                lines.append(f"  - [{att_name}]({att_url})")
            else:
                lines.append(f"  - {att_name}")

    # Tags
    tags = part.get("tags", [])
    if tags:
        tag_names = [tag.get("name", "") for tag in tags if isinstance(tag, dict)]
        if tag_names:
            lines.append(f"**Tags:** {', '.join(tag_names)}")

    # Body content
    cleaned_body = body_text.strip()
    if cleaned_body:
        lines.append("**Body:**")
        lines.append("```")
        lines.append(cleaned_body)
        lines.append("```")
    else:
        lines.append("**Body:** _None provided_")

    lines.append("")  # Blank line after each part
    return "\n".join(lines)


def format_conversation_markdown(
    conversation: dict[str, Any],
    conversation_detail: dict[str, Any] | None,
    index: int,
    total: int,
) -> str:
    """Format a conversation as markdown."""
    conv_id = conversation.get("id", "unknown")
    state = conversation.get("state") or conversation.get("status", "unknown")
    subject = conversation.get("title") or conversation.get("source", {}).get(
        "subject", "No subject"
    )
    created_at = format_timestamp(conversation.get("created_at"))
    updated_at = format_timestamp(conversation.get("updated_at"))
    waiting_since = format_timestamp(conversation.get("waiting_since"))
    snoozed_until = format_timestamp(conversation.get("snoozed_until"))
    open_flag = conversation.get("open")
    read_flag = conversation.get("read")
    priority = conversation.get("priority")
    admin_assignee_id = conversation.get("admin_assignee_id")
    team_assignee_id = conversation.get("team_assignee_id")
    source_summary = conversation.get("source", {}).get("delivered_as")

    conv_data = None
    if conversation_detail:
        conv_data = (
            conversation_detail.get("conversation", conversation_detail)
            if isinstance(conversation_detail, dict)
            else conversation_detail
        )

    statistics = conv_data.get("statistics") if conv_data else {}

    lines = []
    lines.append(f"## Conversation {index}/{total}: {subject}")
    lines.append("")
    lines.append("**Conversation summary:**")
    lines.append("")

    def append_summary(text: str) -> None:
        lines.append(f"- {text}")

    append_summary(f"**ID:** `{conv_id}`")
    append_summary(f"**State:** {state}")
    if isinstance(open_flag, bool):
        append_summary(f"**Open:** {open_flag}")
    if isinstance(read_flag, bool):
        append_summary(f"**Read:** {read_flag}")
    if waiting_since:
        append_summary(f"**Waiting Since (UTC):** {waiting_since}")
    if snoozed_until:
        append_summary(f"**Snoozed Until (UTC):** {snoozed_until}")
    append_summary(f"**Priority:** {priority or 'not_priority'}")
    if admin_assignee_id:
        append_summary(f"**Assigned Admin:** `{admin_assignee_id}`")
    if team_assignee_id:
        append_summary(f"**Assigned Team:** `{team_assignee_id}`")
    company_id = conversation.get("company_id")
    if company_id:
        append_summary(f"**Primary Company:** `{company_id}`")
    if source_summary:
        append_summary(f"**Source Type:** {source_summary}")
    if created_at:
        append_summary(f"**Created:** {created_at}")
    if updated_at:
        append_summary(f"**Updated:** {updated_at}")
    append_metadata = [
        (
            "Tags",
            ", ".join(
                tag.get("name", "")
                for tag in (conv_data or {}).get("tags", {}).get("tags", [])
                if isinstance(tag, dict) and tag.get("name")
            ),
        ),
        (
            "Custom attributes",
            ", ".join(
                f"{k}={v!r}" for k, v in ((conv_data or {}).get("custom_attributes") or {}).items()
            ),
        ),
        (
            "Topics",
            ", ".join(
                topic.get("name", "")
                for topic in ((conv_data or {}).get("topics", {}).get("topics", []))
                if isinstance(topic, dict)
            ),
        ),
        (
            "Linked objects",
            ", ".join(
                obj.get("id", "")
                for obj in ((conv_data or {}).get("linked_objects", {}).get("data", []))
                if isinstance(obj, dict) and obj.get("id")
            ),
        ),
        (
            "SLA",
            (conv_data or {}).get("sla_applied", {}).get("sla_status")
            if isinstance((conv_data or {}).get("sla_applied"), dict)
            else None,
        ),
        (
            "First contact reply",
            statistics.get("first_contact_reply_at") if isinstance(statistics, dict) else None,
        ),
    ]
    for label, value in append_metadata:
        human_value = value if value else "None provided"
        append_summary(f"**{label}:** {human_value}")
    lines.append("")

    # Extract conv_data once for reuse
    conv_data = None
    if conversation_detail:
        conv_data = (
            conversation_detail.get("conversation", conversation_detail)
            if isinstance(conversation_detail, dict)
            else conversation_detail
        )

    # Additional metadata from detail if available
    if conv_data:
        tags_obj = conv_data.get("tags", {})
        tags_markdown = None
        if isinstance(tags_obj, dict):
            tag_list = tags_obj.get("tags", [])
            if tag_list:
                tag_names = [tag.get("name", "") for tag in tag_list if isinstance(tag, dict)]
                if tag_names:
                    tags_markdown = f"**Tags:** {', '.join(tag_names)}"
        elif isinstance(tags_obj, list):
            tags_markdown = format_entity_list(tags_obj, "Tags")

        if tags_markdown:
            lines.append(tags_markdown)

        # Priority
        priority = conv_data.get("priority")
        if priority:
            lines.append(f"**Priority:** {priority}")

        # Contacts
        contacts_obj = conv_data.get("contacts", {})
        if isinstance(contacts_obj, dict):
            contact_list = contacts_obj.get("contacts", [])
            contacts_md = format_entity_list(contact_list, "Contacts")
            if contacts_md:
                lines.append(contacts_md)

        teammates_obj = conv_data.get("teammates")
        if isinstance(teammates_obj, dict):
            teammates_list = teammates_obj.get("teammates", [])
            teammates_md = format_entity_list(teammates_list, "Teammates")
            if teammates_md:
                lines.append(teammates_md)

        linked_objects = conv_data.get("linked_objects")
        if isinstance(linked_objects, dict):
            linked_list = linked_objects.get("data", [])
            linked_md = format_entity_list(linked_list, "Linked Objects")
            if linked_md:
                lines.append(linked_md)

        rating_obj = conv_data.get("conversation_rating")
        if isinstance(rating_obj, dict):
            rating = rating_obj.get("rating")
            remark = rating_obj.get("remark")
            rated_at = format_timestamp(rating_obj.get("updated_at"))
            if rating is not None:
                rating_line = f"**Conversation Rating:** {rating}"
                if remark:
                    rating_line += f" ({remark})"
                if rated_at:
                    rating_line += f" at {rated_at}"
                lines.append(rating_line)
            teammate = rating_obj.get("teammate")
            if isinstance(teammate, dict):
                lines.append(
                    f"**Rated By:** {teammate.get('type', 'contact').title()} `{teammate.get('id', 'unknown')}`"
                )

        custom_attrs = conv_data.get("custom_attributes")
        if isinstance(custom_attrs, dict) and custom_attrs:
            attr_entries = ", ".join(f"{k}={v!r}" for k, v in custom_attrs.items())
            lines.append(f"**Custom Attributes:** {attr_entries}")

    statistics = conv_data.get("statistics") if conv_data else {}
    if isinstance(statistics, dict):
        counts = statistics.get("count_conversation_parts")
        if counts is not None:
            lines.append(f"**Conversation Parts (reported):** {counts}")
        for stat_key in [
            "time_to_assignment",
            "time_to_admin_reply",
            "time_to_first_close",
            "median_time_to_reply",
            "handling_time",
            "adjusted_handling_time",
        ]:
            stat_val = statistics.get(stat_key)
            if stat_val:
                pretty_name = stat_key.replace("_", " ").title()
                lines.append(f"**{pretty_name}:** {stat_val}s")
        reopen_count = statistics.get("count_reopens")
        if reopen_count is not None:
            lines.append(f"**Reopen Count:** {reopen_count}")

    sla_obj = conv_data.get("sla_applied") if conv_data else {}
    if isinstance(sla_obj, dict):
        sla_name = sla_obj.get("sla_name") or "SLA"
        sla_status = sla_obj.get("sla_status")
        lines.append(f"**SLA:** {sla_name} ({sla_status})")

    ai_agent = conv_data.get("ai_agent") if conv_data else {}
    if isinstance(ai_agent, dict):
        ai_state = ai_agent.get("resolution_state")
        ai_rating = ai_agent.get("rating")
        ai_line = f"**AI Agent:** state={ai_state or 'unknown'}"
        if ai_rating:
            ai_line += f", rating={ai_rating}"
        lines.append(ai_line)

    # Conversation body (from source field)
    source_body = None
    source = None
    if conv_data and isinstance(conv_data.get("source"), dict):
        source = conv_data.get("source")
    elif isinstance(conversation.get("source"), dict):
        source = conversation.get("source")

    if isinstance(source, dict):
        source_body = source.get("body")
        author = source.get("author", {})
        author_components: list[str] = []
        if isinstance(author, dict):
            author_name = author.get("name") or author.get("email")
            author_id = author.get("id")
            author_email = author.get("email")
            if author_name:
                author_components.append(author_name)
            if author_id:
                author_components.append(f"`{author_id}`")
            if author_email:
                author_components.append(author_email)
        if author_components:
            lines.append(f"**Source Author:** {', '.join(author_components)}")
        attachments = source.get("attachments", [])
        if isinstance(attachments, list) and attachments:
            lines.append(f"**Source Attachments:** {len(attachments)} file(s)")

    if source_body:
        lines.append("### Conversation Body")
        lines.append("")
        # Clean HTML tags
        body_text = str(source_body)
        if "<" in body_text and ">" in body_text:
            body_text = re.sub(r"<[^>]+>", "", body_text)
            body_text = (
                body_text.replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&lt;", "<")
                .replace("&gt;", ">")
                .replace("&quot;", '"')
                .replace("&#39;", "'")
            )
        lines.append("```")
        lines.append(body_text.strip())
        lines.append("```")
        lines.append("")

    lines.append("")  # Blank line before parts

    # Conversation parts
    if conv_data:
        conversation_parts_obj = conv_data.get("conversation_parts", {})
        parts = []
        if isinstance(conversation_parts_obj, dict):
            parts = conversation_parts_obj.get("conversation_parts", [])
        elif isinstance(conversation_parts_obj, list):
            parts = conversation_parts_obj

        if parts:
            lines.append("### Conversation Parts")
            lines.append("")
            for idx, part in enumerate(parts, 1):
                lines.append(format_conversation_part_markdown(part, idx))
        else:
            lines.append("*No conversation parts available*")
            lines.append("")

    lines.append("")
    lines.append("<details><summary>Conversation metadata snapshot</summary>")
    lines.append("")

    def _md_field(label: str, value: Any) -> None:
        if value is None:
            return
        lines.append(f"- **{label}:** {value}")

    metadata = {
        "Tags": ", ".join(
            tag.get("name", "")
            for tag in (conv_data or {}).get("tags", {}).get("tags", [])
            if isinstance(tag, dict) and tag.get("name")
        ),
        "Priority": conv_data.get("priority") if conv_data else conversation.get("priority"),
        "SLA": (conv_data or {}).get("sla_applied", {}).get("sla_status")
        if isinstance((conv_data or {}).get("sla_applied"), dict)
        else None,
        "First contact reply": statistics.get("first_contact_reply_at")
        if isinstance(statistics, dict)
        else None,
        "Custom attributes": ", ".join(
            f"{k}={v!r}" for k, v in ((conv_data or {}).get("custom_attributes") or {}).items()
        ),
        "Topics": ", ".join(
            topic.get("name", "")
            for topic in ((conv_data or {}).get("topics", {}).get("topics", []))
            if isinstance(topic, dict)
        ),
        "Linked objects": ", ".join(
            obj.get("id", "")
            for obj in ((conv_data or {}).get("linked_objects", {}).get("data", []))
            if isinstance(obj, dict) and obj.get("id")
        ),
    }
    for label, value in metadata.items():
        human_value = value or "None"
        lines.append(f"- **{label}:** {human_value}")
    lines.append("")
    lines.append("</details>")

    lines.append("---")  # Separator between conversations
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch Intercom conversations using a classic access token",
    )
    parser.add_argument(
        "--access-token",
        help="Intercom classic access token (falls back to INTERCOM_ACCESS_TOKEN env var)",
    )
    parser.add_argument(
        "--per-page",
        type=int,
        default=5,
        help="Number of conversations to fetch (default: 5)",
    )
    parser.add_argument(
        "--starting-after",
        help="Pagination cursor from previous run (optional)",
    )
    parser.add_argument(
        "--order",
        choices=("asc", "desc"),
        default="desc",
        help="Conversation order (default: desc)",
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
        help="Output conversations in markdown format (automatically fetches conversation parts)",
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
            response = client.list_conversations(
                per_page=args.per_page,
                starting_after=args.starting_after,
                order=args.order,
            )

            conversations = response.get("conversations", [])

            conversation_details: list[tuple[dict[str, Any], dict[str, Any] | None]] = []

            if args.create_markdown:
                print(
                    f"Fetching {len(conversations)} conversation(s) and details...", file=sys.stderr
                )
            else:
                print(f"✅ Retrieved {len(conversations)} conversation(s).\n")

            for idx, conversation in enumerate(conversations, 1):
                conv_id = conversation.get("id")
                conv_detail: dict[str, Any] | None = None

                if not args.create_markdown:
                    state = conversation.get("state") or conversation.get("status")
                    subject = conversation.get("title") or conversation.get("source", {}).get(
                        "subject"
                    )
                    created_at = format_timestamp(conversation.get("created_at"))
                    updated_at = format_timestamp(conversation.get("updated_at"))
                    print(
                        f"[{idx}/{len(conversations)}] id={conv_id} state={state} "
                        f"created_at={created_at or conversation.get('created_at')} "
                        f"updated_at={updated_at or conversation.get('updated_at')} "
                        f"subject={subject!r}"
                    )
                    print()

                if args.create_markdown:
                    try:
                        print(
                            f"  Fetching full conversation details for {conv_id}...",
                            file=sys.stderr,
                        )
                        conv_detail = client.get_conversation(conv_id)
                    except Exception as e:
                        print(f"⚠️  Failed to fetch conversation {conv_id}: {e}", file=sys.stderr)
                        conv_detail = None

                    conversation_details.append((conversation, conv_detail))

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
                print("# Intercom Conversations", file=sys.stderr)
                print("", file=sys.stderr)
                print(f"**Retrieved:** {len(conversations)} conversation(s)", file=sys.stderr)
                print(
                    f"**Fetched:** {sum(1 for _, detail in conversation_details if detail is not None)} with full details",
                    file=sys.stderr,
                )
                print("", file=sys.stderr)
                print("---", file=sys.stderr)
                print("", file=sys.stderr)

                for idx, (conversation, conv_detail) in enumerate(conversation_details, 1):
                    print(
                        format_conversation_markdown(
                            conversation, conv_detail, idx, len(conversations)
                        )
                    )

                if next_cursor:
                    print("", file=sys.stderr)
                    print(f"**Next cursor:** `{next_cursor}`", file=sys.stderr)

    except Exception as exc:  # pragma: no cover - script only
        print(f"Failed to fetch conversations: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
