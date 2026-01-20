"""
Linear document classes for structured issue and activity representation.
"""

import html
import re
from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from src.ingest.references.reference_ids import get_linear_issue_reference_id

MIN_MEANINGFUL_CONTENT_LENGTH = 2
COMMENT_SUFFIX = "commented:"

USER_MENTION_PATTERN = r"<@[^|]*\|@[^>]*>"
TIMESTAMP_PATTERN = r"\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}(?::\d{2})?"
COMMON_WORDS_PATTERN = r"\b(created|updated|changed|assigned|removed|added|to|from|issue|commented:|status|priority|label)\b"


class LinearIssueChunkMetadata(TypedDict):
    """Metadata for Linear issue chunks."""

    activity_type: str | None
    actor: str | None
    actor_id: str | None
    timestamp: str | None
    formatted_time: str | None
    issue_id: str | None
    issue_title: str | None
    team_id: str | None
    team_name: str | None
    activity_id: str | None
    parent_id: str | None
    comment_body: str | None
    comment_id: str | None
    old_status: str | None
    new_status: str | None
    assignee: str | None
    priority: str | None
    label: str | None


class LinearIssueDocumentMetadata(TypedDict):
    """Metadata for Linear issue documents."""

    issue_id: str | None
    issue_title: str | None
    issue_url: str | None
    team_name: str | None
    team_id: str | None
    status: str | None
    priority: str | None
    assignee: str | None
    labels: list[str] | None
    source: str
    type: str
    activity_count: int
    source_created_at: str | None


@dataclass
class LinearIssueChunk(BaseChunk[LinearIssueChunkMetadata]):
    """Represents a single Linear issue activity chunk."""

    def get_content(self) -> str:
        """Get the formatted activity content."""
        activity_type = self.raw_data.get("activity_type", "")
        formatted_time = self.raw_data.get("formatted_time", "")
        actor = self.raw_data.get("actor", "")
        actor_id = self.raw_data.get("actor_id", "")

        if activity_type == "issue_created":
            return f"{formatted_time} <@{actor_id}|@{actor}> created issue"
        elif activity_type == "issue_updated":
            update_summary = self.raw_data.get("update_summary", "issue")
            return f"{formatted_time} <@{actor_id}|@{actor}> updated {update_summary}"
        elif activity_type == "comment":
            comment_body = self.raw_data.get("comment_body", "")
            cleaned_comment = self._clean_linear_text(comment_body)
            single_line_comment = cleaned_comment.replace("\n", " ").replace("\r", " ")
            single_line_comment = " ".join(single_line_comment.split())
            return f"{formatted_time} <@{actor_id}|@{actor}> commented: {single_line_comment}"
        elif activity_type == "status_changed":
            old_status = self.raw_data.get("old_status", "")
            new_status = self.raw_data.get("new_status", "")
            return f"{formatted_time} <@{actor_id}|@{actor}> changed status from {old_status} to {new_status}"
        elif activity_type == "assignee_changed":
            assignee = self.raw_data.get("assignee", "")
            return f"{formatted_time} <@{actor_id}|@{actor}> assigned to {assignee}"
        elif activity_type == "priority_changed":
            priority = self.raw_data.get("priority", "")
            return f"{formatted_time} <@{actor_id}|@{actor}> changed priority to {priority}"
        elif activity_type == "label_added":
            label = self.raw_data.get("label", "")
            return f"{formatted_time} <@{actor_id}|@{actor}> added label {label}"
        elif activity_type == "label_removed":
            label = self.raw_data.get("label", "")
            return f"{formatted_time} <@{actor_id}|@{actor}> removed label {label}"
        else:
            return f"{formatted_time} <@{actor_id}|@{actor}> {activity_type}"

    def _clean_linear_text(self, text: str) -> str:
        """Clean up common Linear text formatting issues."""
        if not text:
            return text

        text = html.unescape(text)

        try:
            if any(char in text for char in ["â€", "Â"]):
                text = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        return text

    def has_meaningful_content(self) -> bool:
        """Check if this chunk has meaningful content worth indexing.

        Filters out chunks that are essentially empty or contain only user mention syntax.
        """
        content = self.get_content()

        if not content or not content.strip():
            return False

        if COMMENT_SUFFIX in content and content.strip().endswith(COMMENT_SUFFIX):
            return False

        cleaned = re.sub(USER_MENTION_PATTERN, "", content)
        cleaned = re.sub(TIMESTAMP_PATTERN, "", cleaned)
        cleaned = re.sub(
            COMMON_WORDS_PATTERN,
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = cleaned.strip()
        return len(cleaned) >= MIN_MEANINGFUL_CONTENT_LENGTH

    def get_metadata(self) -> LinearIssueChunkMetadata:
        """Get chunk-specific metadata."""
        metadata: LinearIssueChunkMetadata = {
            "activity_type": self.raw_data.get("activity_type"),
            "actor": self.raw_data.get("actor"),
            "actor_id": self.raw_data.get("actor_id"),
            "timestamp": self.raw_data.get("timestamp"),
            "formatted_time": self.raw_data.get("formatted_time"),
            "issue_id": self.raw_data.get("issue_id"),
            "issue_title": self.raw_data.get("issue_title"),
            "team_id": self.raw_data.get("team_id"),
            "team_name": self.raw_data.get("team_name"),
            "activity_id": self.raw_data.get("activity_id"),
            "parent_id": self.raw_data.get("parent_id"),
            "comment_body": self.raw_data.get("comment_body"),
            "comment_id": self.raw_data.get("comment_id"),
            "old_status": self.raw_data.get("old_status"),
            "new_status": self.raw_data.get("new_status"),
            "assignee": self.raw_data.get("assignee"),
            "priority": self.raw_data.get("priority"),
            "label": self.raw_data.get("label"),
        }

        return metadata


@dataclass
class LinearIssueDocument(BaseDocument[LinearIssueChunk, LinearIssueDocumentMetadata]):
    """Represents a complete Linear issue with all its activities."""

    raw_data: dict[str, Any]

    def _get_team_name(self) -> str | None:
        return self.raw_data.get("team_name")

    def get_header_content(self) -> str:
        """Get the formatted header section of the document."""
        issue_id = self.raw_data.get("issue_id", "")
        issue_identifier = self.raw_data.get("issue_identifier", "")
        issue_title = self.raw_data.get("issue_title", "")
        issue_url = self.raw_data.get("issue_url", "")
        issue_description = self.raw_data.get("issue_description", "")
        team_name = self._get_team_name()
        status = self.raw_data.get("status", "")
        priority = self.raw_data.get("priority", "")
        assignee = self.raw_data.get("assignee", "")
        labels = self.raw_data.get("labels", [])
        activities = self.raw_data.get("activities", [])

        user_map = {}
        for activity in reversed(activities):
            actor_id = activity.get("actor_id", "")
            actor = activity.get("actor", "")
            if actor_id and actor and actor_id not in user_map:
                user_map[actor_id] = f"<@{actor_id}|@{actor}>"

        participants_list = list(user_map.values())

        lines = []

        if issue_identifier:
            lines.append(f"Issue Human ID: {issue_identifier}")
            lines.append("")

        lines.extend(
            [f"Issue: <{issue_id}|{issue_title}>", f"URL: {issue_url}", f"Team: {team_name}"]
        )

        if status:
            lines.append(f"Status: {status}")
        if priority:
            lines.append(f"Priority: {priority}")
        if assignee:
            lines.append(f"Assignee: {assignee}")
        if labels:
            lines.append(f"Labels: {', '.join(labels)}")
        if participants_list:
            lines.append(f"Participants: {', '.join(participants_list)}")

        if issue_description:
            lines.append("")
            lines.append("Description:")
            cleaned_description = self._clean_linear_text(issue_description)
            single_line_description = cleaned_description.replace("\n", " ").replace("\r", " ")
            single_line_description = " ".join(single_line_description.split())
            lines.append(single_line_description)

        return "\n".join(lines)

    def get_content(self) -> str:
        """Get the formatted document content."""
        activities = self.raw_data.get("activities", [])
        team_name = self._get_team_name()

        lines = [self.get_header_content()]
        lines.extend(["", "", "Activity:", ""])

        comment_to_activity: dict[str, str] = {}
        for activity in activities:
            comment_id = activity.get("comment_id", "")
            activity_id = activity.get("activity_id", "")
            if comment_id and activity_id:
                comment_to_activity[comment_id] = activity_id

        threads: dict[str, list] = {}
        root_activities = []

        for activity in activities:
            parent_id = activity.get("parent_id", "")
            if parent_id:
                parent_activity_id = comment_to_activity.get(parent_id, parent_id)
                if parent_activity_id not in threads:
                    threads[parent_activity_id] = []
                threads[parent_activity_id].append(activity)
            else:
                root_activities.append(activity)

        for activity_data in root_activities:
            chunk = LinearIssueChunk(
                document=self,
                linear_team_name=team_name,
                raw_data=activity_data,
            )
            lines.append(chunk.get_content())

            activity_id = activity_data.get("activity_id", "")
            if activity_id in threads:
                for thread_activity in threads[activity_id]:
                    thread_chunk = LinearIssueChunk(
                        document=self,
                        linear_team_name=team_name,
                        raw_data=thread_activity,
                    )
                    lines.append(f"  |-- {thread_chunk.get_content()}")

        orphaned_threads = []
        for parent_id, thread_activities in threads.items():
            if not any(act.get("activity_id") == parent_id for act in root_activities):
                orphaned_threads.extend(thread_activities)

        if orphaned_threads:
            lines.append("")
            lines.append("Thread replies to comments from other days:")
            for thread_activity in sorted(orphaned_threads, key=lambda a: a.get("timestamp", "")):
                thread_chunk = LinearIssueChunk(
                    document=self,
                    linear_team_name=team_name,
                    raw_data=thread_activity,
                )
                parent_id = thread_activity.get("parent_id", "")
                lines.append(f"  |-- (reply to {parent_id}) {thread_chunk.get_content()}")

        return "\n".join(lines)

    def _clean_linear_text(self, text: str) -> str:
        """Clean up common Linear text formatting issues."""
        if not text:
            return text

        text = html.unescape(text)

        try:
            if any(char in text for char in ["â€", "Â"]):
                text = text.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

        return text

    def to_embedding_chunks(self) -> list[LinearIssueChunk]:
        """Convert to embedding chunk format."""
        chunks = []
        activities = self.raw_data.get("activities", [])
        team_name = self._get_team_name()

        # Add header chunk
        header_chunk = LinearIssueChunk(
            document=self,
            linear_team_name=team_name,
            raw_data={
                "content": self.get_header_content(),
                "issue_id": self.raw_data.get("issue_id"),
                "issue_title": self.raw_data.get("issue_title"),
                "team_id": self.raw_data.get("team_id"),
                "team_name": team_name,
                "source": self.get_source(),
                "type": "linear_issue_header",
                "chunk_type": "header",
                "activity_count": len(activities),
                "source_created_at": self.raw_data.get("source_created_at"),
            },
        )
        chunks.append(header_chunk)

        # Then add all activity chunks, filtering out empty/meaningless ones
        for activity_data in activities:
            chunk = LinearIssueChunk(
                document=self,
                linear_team_name=team_name,
                raw_data=activity_data,
            )
            # Only include chunks with meaningful content
            if chunk.has_meaningful_content():
                chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.LINEAR

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        issue_identifier = self.raw_data.get("issue_identifier", "")
        return get_linear_issue_reference_id(issue_id=issue_identifier)

    def get_metadata(self) -> LinearIssueDocumentMetadata:
        """Get document metadata."""
        activities = self.raw_data.get("activities", [])

        source_created_at = None
        if activities:
            for activity in activities:
                if activity.get("activity_type") == "issue_created":
                    timestamp_str = activity.get("timestamp")
                    if timestamp_str:
                        try:
                            from datetime import datetime

                            created_dt = datetime.fromisoformat(
                                timestamp_str.replace("Z", "+00:00")
                            )
                            source_created_at = created_dt.isoformat()
                            break
                        except (ValueError, TypeError):
                            continue

            if not source_created_at:
                earliest_ts = None
                for activity in activities:
                    timestamp_str = activity.get("timestamp")
                    if timestamp_str:
                        try:
                            from datetime import datetime

                            activity_dt = datetime.fromisoformat(
                                timestamp_str.replace("Z", "+00:00")
                            )
                            if earliest_ts is None or activity_dt < earliest_ts:
                                earliest_ts = activity_dt
                        except (ValueError, TypeError):
                            continue

                if earliest_ts:
                    source_created_at = earliest_ts.isoformat()

        metadata: LinearIssueDocumentMetadata = {
            "issue_id": self.raw_data.get("issue_id"),
            "issue_title": self.raw_data.get("issue_title"),
            "issue_url": self.raw_data.get("issue_url"),
            "team_name": self._get_team_name(),
            "team_id": self.raw_data.get("team_id"),
            "status": self.raw_data.get("status"),
            "priority": self.raw_data.get("priority"),
            "assignee": self.raw_data.get("assignee"),
            "labels": self.raw_data.get("labels"),
            "source": self.get_source(),
            "type": "linear_issue_document",
            "activity_count": len(activities),
            "source_created_at": source_created_at,
        }

        return metadata
