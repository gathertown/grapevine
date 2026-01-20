"""
Utilities for rendering Intercom conversations into Markdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_conversation_document import (
    IntercomConversationDocumentMetadata,
)


@dataclass(frozen=True)
class IntercomMarkdownResult:
    """Rendered Markdown plus metadata for an Intercom conversation."""

    markdown: str
    metadata: IntercomConversationDocumentMetadata
    sections: list[IntercomMarkdownSection]


@dataclass(frozen=True)
class IntercomMarkdownSection:
    """Represents a logical section of the markdown document."""

    section_type: str
    markdown: str
    part_index: int | None = None
    author_name: str | None = None
    author_email: str | None = None
    created_at: str | None = None
    ai_flags: dict[str, bool | None] = field(default_factory=dict)


def build_conversation_markdown(conversation_data: dict[str, Any]) -> IntercomMarkdownResult:
    """Convert raw Intercom conversation JSON into Markdown + metadata."""

    conversation_id = str(conversation_data.get("id") or "unknown")
    title = (
        conversation_data.get("title")
        or conversation_data.get("source", {}).get("subject")
        or f"Conversation {conversation_id}"
    )
    state = conversation_data.get("state") or conversation_data.get("status")
    priority = conversation_data.get("priority") or "not_priority"
    created_at = _format_timestamp(conversation_data.get("created_at"))
    updated_at = _format_timestamp(conversation_data.get("updated_at"))
    waiting_since = _format_timestamp(conversation_data.get("waiting_since"))
    snoozed_until = _format_timestamp(conversation_data.get("snoozed_until"))
    open_flag = conversation_data.get("open")
    read_flag = conversation_data.get("read")
    admin_assignee = conversation_data.get("admin_assignee_id")
    team_assignee = conversation_data.get("team_assignee_id")
    company_id = conversation_data.get("company_id")
    source_summary = conversation_data.get("source", {}).get("delivered_as")

    tags = _extract_names(conversation_data.get("tags", {}), list_key="tags")
    contacts = _extract_ids(conversation_data.get("contacts", {}), list_key="contacts")
    teammates = _extract_ids(conversation_data.get("teammates", {}), list_key="teammates")
    topics = _extract_names(conversation_data.get("topics", {}), list_key="topics")
    linked_objects = _extract_ids(
        conversation_data.get("linked_objects", {}), list_key="data", id_key="id"
    )

    summary_lines = [
        _format_summary_line("ID", f"`{conversation_id}`"),
        _format_summary_line("State", state or "unknown"),
        _format_summary_line("Open", open_flag),
        _format_summary_line("Read", read_flag),
        _format_summary_line("Waiting Since (UTC)", waiting_since),
        _format_summary_line("Snoozed Until (UTC)", snoozed_until),
        _format_summary_line("Priority", priority or "not_priority"),
        _format_summary_line("Assigned Admin", admin_assignee),
        _format_summary_line("Assigned Team", team_assignee),
        _format_summary_line("Primary Company", company_id),
        _format_summary_line("Source Type", source_summary),
        _format_summary_line("Created", created_at),
        _format_summary_line("Updated", updated_at),
        _format_summary_line("Tags", ", ".join(tags) or "None provided"),
        _format_summary_line("Contacts", ", ".join(contacts) or "None provided"),
        _format_summary_line("Teammates", ", ".join(teammates) or "None provided"),
        _format_summary_line(
            "Topics",
            ", ".join(topics) or "None provided",
        ),
        _format_summary_line(
            "Linked Objects",
            ", ".join(linked_objects) or "None provided",
        ),
        _format_summary_line(
            "Custom Attributes",
            _format_custom_attributes(conversation_data.get("custom_attributes")),
        ),
        _format_summary_line(
            "First Contact Reply",
            _format_timestamp(conversation_data.get("first_contact_reply", {}).get("created_at")),
        ),
    ]

    metadata: IntercomConversationDocumentMetadata = {
        "conversation_id": conversation_id,
        "title": title,
        "state": state,
        "priority": priority,
        "tags": tags,
        "contacts": contacts,
        "teammates": teammates,
        "participants": _extract_participants(conversation_data),
        "topics": topics,
        "linked_objects": linked_objects,
        "source_created_at": created_at,
        "source": DocumentSource.INTERCOM.value,
        "type": "conversation",
    }

    lines: list[str] = []
    sections: list[IntercomMarkdownSection] = []

    summary_section = IntercomMarkdownSection(
        section_type="summary",
        markdown="\n".join(
            ["# " + title, ""] + ["**Conversation summary:**"] + summary_lines
        ).strip(),
    )
    sections.append(summary_section)
    lines.append(summary_section.markdown)
    lines.append("")

    body_section = _build_conversation_body_section(conversation_data)
    if body_section:
        sections.append(body_section)
        lines.append(body_section.markdown)
        lines.append("")

    part_sections = _build_part_sections(conversation_data)
    for section in part_sections:
        sections.append(section)
        lines.append(section.markdown)
        lines.append("")

    return IntercomMarkdownResult(
        markdown="\n".join(lines).strip(),
        metadata=metadata,
        sections=sections,
    )


def _format_summary_line(label: str, value: Any) -> str:
    if value is None or value == "":
        return f"- **{label}:** None provided"
    return f"- **{label}:** {value}"


def _build_conversation_body_section(
    conversation_data: dict[str, Any],
) -> IntercomMarkdownSection | None:
    source = conversation_data.get("source", {})
    if not isinstance(source, dict):
        return None

    body_lines = ["### Conversation Body", ""]
    author_bits: list[str] = []
    author = source.get("author", {})
    author_name = None
    author_email = None
    if isinstance(author, dict):
        author_name = author.get("name") or author.get("email")
        author_email = author.get("email")
        if author_name:
            author_bits.append(author_name)
        if author.get("id"):
            author_bits.append(f"`{author['id']}`")
        if author_email and author_email not in author_bits:
            author_bits.append(author_email)
    if author_bits:
        body_lines.append(f"**Source Author:** {', '.join(author_bits)}")
    attachments = source.get("attachments", [])
    if isinstance(attachments, list) and attachments:
        body_lines.append(f"**Source Attachments:** {len(attachments)} file(s)")

    body_text = source.get("body") or ""
    cleaned_body = _clean_html(body_text)
    if cleaned_body.strip():
        body_lines.append("**Body:**")
        body_lines.append("```")
        body_lines.append(cleaned_body.strip())
        body_lines.append("```")
    else:
        body_lines.append("**Body:** _None provided_")

    return IntercomMarkdownSection(
        section_type="conversation_body",
        markdown="\n".join(body_lines).strip(),
        author_name=author_name,
        author_email=author_email,
    )


def _build_part_sections(conversation_data: dict[str, Any]) -> list[IntercomMarkdownSection]:
    parts = conversation_data.get("conversation_parts", {})
    if isinstance(parts, dict):
        conversation_parts = parts.get("conversation_parts", [])
    elif isinstance(parts, list):
        conversation_parts = parts
    else:
        conversation_parts = []

    if not conversation_parts:
        return []

    sections: list[IntercomMarkdownSection] = []
    for idx, part in enumerate(conversation_parts, start=1):
        sections.append(_format_conversation_part_section(part, idx))
    return sections


def _format_conversation_part_section(part: dict[str, Any], index: int) -> IntercomMarkdownSection:
    part_type = part.get("part_type", "unknown")
    author = part.get("author", {})
    author_type = author.get("type", "unknown")
    author_name = author.get("name") or author.get("email") or "Unknown"
    author_email = author.get("email")
    created_at = _format_timestamp(part.get("created_at"))
    from_ai_agent = part.get("from_ai_agent") or author.get("from_ai_agent")
    is_ai_answer = part.get("is_ai_answer")
    body = part.get("body", "")
    body_text = _clean_html(body)

    section_lines = [f"#### Part {index}: {part_type.title()}"]
    author_line = f"**Author:** {author_type.title()}: {author_name}"
    if author_email:
        author_line += f" ({author_email})"
    section_lines.append(author_line)
    if created_at:
        section_lines.append(f"**Created (UTC):** {created_at}")
    if from_ai_agent is not None or is_ai_answer is not None:
        ai_bits = []
        if from_ai_agent is not None:
            ai_bits.append(f"from_ai_agent={from_ai_agent}")
        if is_ai_answer is not None:
            ai_bits.append(f"is_ai_answer={is_ai_answer}")
        section_lines.append(f"**AI Flags:** {', '.join(ai_bits)}")

    attachments = part.get("attachments", [])
    if isinstance(attachments, list) and attachments:
        section_lines.append(f"**Attachments:** {len(attachments)}")

    tags = part.get("tags", [])
    if isinstance(tags, list) and tags:
        tag_names = ", ".join(
            tag.get("name", "") for tag in tags if isinstance(tag, dict) and tag.get("name")
        )
        if tag_names:
            section_lines.append(f"**Tags:** {tag_names}")

    if body_text.strip():
        section_lines.append("**Body:**")
        section_lines.append("```")
        section_lines.append(body_text.strip())
        section_lines.append("```")
    else:
        section_lines.append("**Body:** _None provided_")

    return IntercomMarkdownSection(
        section_type="conversation_part",
        markdown="\n".join(section_lines).strip(),
        part_index=index,
        author_name=author_name,
        author_email=author_email,
        created_at=created_at,
        ai_flags={"from_ai_agent": from_ai_agent, "is_ai_answer": is_ai_answer},
    )


def _clean_html(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = re.sub(r"<[^>]+>", "", value)
    replacements = {
        "&nbsp;": " ",
        "&amp;": "&",
        "&lt;": "<",
        "&gt;": ">",
        "&quot;": '"',
        "&#39;": "'",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _format_timestamp(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=UTC).isoformat()
        if isinstance(value, str):
            if value.isdigit():
                return datetime.fromtimestamp(int(value), tz=UTC).isoformat()
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except (ValueError, TypeError, OSError):
        return None
    return None


def _extract_names(container: Any, *, list_key: str) -> list[str]:
    if not isinstance(container, dict):
        return []
    values = container.get(list_key, [])
    return [item.get("name", "") for item in values if isinstance(item, dict) and item.get("name")]


def _extract_ids(container: Any, *, list_key: str, id_key: str = "id") -> list[str]:
    if not isinstance(container, dict):
        return []
    values = container.get(list_key, [])
    return [item.get(id_key, "") for item in values if isinstance(item, dict) and item.get(id_key)]


def _extract_participants(conversation_data: dict[str, Any]) -> list[str]:
    participants: list[str] = []
    contacts = conversation_data.get("contacts", {})
    if isinstance(contacts, dict):
        for contact in contacts.get("contacts", []):
            if not isinstance(contact, dict):
                continue
            name = contact.get("name") or contact.get("email") or contact.get("external_id")
            if name:
                participants.append(str(name))
    return participants


def _format_custom_attributes(custom_attrs: Any) -> str:
    if not isinstance(custom_attrs, dict) or not custom_attrs:
        return "None provided"
    return ", ".join(f"{key}={value!r}" for key, value in custom_attrs.items())
