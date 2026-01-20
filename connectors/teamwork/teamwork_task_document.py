"""
Teamwork task document classes for structured task representation.
Multi-chunk approach with task details and comments as activity chunks.
"""

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.base.utils import convert_timestamp_to_iso
from connectors.teamwork.teamwork_artifacts import TeamworkTaskArtifact
from src.permissions.models import PermissionPolicy


class TeamworkTaskChunkMetadata(TypedDict, total=False):
    """Metadata for Teamwork task chunks."""

    chunk_type: str | None
    task_id: int | None
    comment_id: int | None
    author_name: str | None
    timestamp: str | None
    source: str | None
    content_preview: str | None


class TeamworkTaskDocumentMetadata(TypedDict, total=False):
    """Metadata for Teamwork task documents."""

    task_id: int | None
    task_name: str | None
    project_id: int | None
    project_name: str | None
    task_list_name: str | None
    status: str | None
    priority: str | None
    assignee_name: str | None
    assignee_id: int | None
    creator_name: str | None
    creator_id: int | None
    due_date: str | None
    start_date: str | None
    completed: bool
    completed_at: str | None
    estimated_minutes: int | None
    tags: list[str] | None
    has_attachments: bool
    attachment_count: int | None
    parent_task_id: int | None
    parent_task_name: str | None
    source_created_at: str | None
    source_updated_at: str | None
    source: str
    type: str


@dataclass
class TeamworkTaskChunk(BaseChunk[TeamworkTaskChunkMetadata]):
    """Represents a single Teamwork task chunk (header or comment)."""

    def get_content(self) -> str:
        """Get the formatted chunk content."""
        # Header chunks store pre-formatted content directly
        if self.raw_data.get("chunk_type") == "header":
            return self.raw_data.get("content", "")

        # Comment chunks
        timestamp = self.raw_data.get("datetime") or self.raw_data.get("createdAt", "")
        timestamp_str = ""
        if timestamp:
            try:
                dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                timestamp_str = ""

        # Extract author name
        author = self.raw_data.get("author", {})
        if isinstance(author, dict):
            author_name = (
                author.get("fullName")
                or author.get("name")
                or f"{author.get('firstName', '')} {author.get('lastName', '')}".strip()
            )
        else:
            author_name = ""

        author_str = f"by {author_name} " if author_name else ""

        # Get comment content
        body = self.raw_data.get("body") or self.raw_data.get("content", "")
        if body:
            body = body.strip()
            body = body.replace("\n", " ").replace("\r", " ")
            body = " ".join(body.split())

        return f"{timestamp_str} {author_str}commented: {body}"

    def get_metadata(self) -> TeamworkTaskChunkMetadata:
        """Get chunk-specific metadata."""
        chunk_type = self.raw_data.get("chunk_type", "comment")

        author = self.raw_data.get("author", {})
        author_name = None
        if isinstance(author, dict):
            author_name = (
                author.get("fullName")
                or author.get("name")
                or f"{author.get('firstName', '')} {author.get('lastName', '')}".strip()
            )

        metadata: TeamworkTaskChunkMetadata = {
            "chunk_type": chunk_type,
            "task_id": self.raw_data.get("task_id"),
            "comment_id": self.raw_data.get("id"),
            "author_name": author_name if author_name else None,
            "timestamp": self.raw_data.get("datetime") or self.raw_data.get("createdAt"),
            "source": "teamwork_task",
            "content_preview": (self.raw_data.get("body") or "")[:100],
        }

        return metadata


@dataclass
class TeamworkTaskDocument(BaseDocument[TeamworkTaskChunk, TeamworkTaskDocumentMetadata]):
    """Teamwork task document with embedded comments."""

    raw_data: dict[str, Any]
    metadata: TeamworkTaskDocumentMetadata | None = None
    chunk_class: type[TeamworkTaskChunk] = TeamworkTaskChunk

    @classmethod
    def from_artifact(
        cls,
        artifact: TeamworkTaskArtifact,
        permission_policy: PermissionPolicy = "tenant",
        permission_allowed_tokens: list[str] | None = None,
        hydrator: Any | None = None,
    ) -> "TeamworkTaskDocument":
        """Create document from artifact."""
        task_data = artifact.content.task_data.copy()
        task_id = artifact.metadata.task_id

        # Include comments from artifact
        task_data["comments"] = artifact.content.comments

        # Include project info from metadata
        task_data["_project_id"] = artifact.metadata.project_id
        task_data["_project_name"] = artifact.metadata.project_name
        task_data["_task_list_name"] = artifact.metadata.task_list_name

        return cls(
            id=f"teamwork_task_{task_id}",
            raw_data=task_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
        )

    def _get_task_name(self) -> str | None:
        """Get task name."""
        return self.raw_data.get("name") or self.raw_data.get("content")

    def _get_task_description(self) -> str | None:
        """Get task description."""
        return self.raw_data.get("description")

    def _get_assignee_info(self) -> tuple[str | None, int | None]:
        """Get assignee name and ID."""
        # Try assignees (array) first
        assignees = self.raw_data.get("assignees") or self.raw_data.get("responsible-party-ids", [])
        if assignees and isinstance(assignees, list) and len(assignees) > 0:
            assignee = assignees[0]
            if isinstance(assignee, dict):
                assignee_id = int(assignee.get("id", 0)) if assignee.get("id") else None
                name = (
                    assignee.get("fullName")
                    or assignee.get("name")
                    or f"{assignee.get('firstName', '')} {assignee.get('lastName', '')}".strip()
                )
                return name or None, assignee_id
            elif isinstance(assignee, (int, str)):
                return None, int(assignee) if assignee else None

        # Fallback to single assignee field
        assignee_id = self.raw_data.get("assigneeId") or self.raw_data.get("assignee-id")
        assignee_name = self.raw_data.get("assigneeName")
        return assignee_name, int(assignee_id) if assignee_id else None

    def _get_creator_info(self) -> tuple[str | None, int | None]:
        """Get creator name and ID."""
        creator = self.raw_data.get("createdBy") or self.raw_data.get("creator-id", {})
        if isinstance(creator, dict):
            creator_id = int(creator.get("id", 0)) if creator.get("id") else None
            name = (
                creator.get("fullName")
                or creator.get("name")
                or f"{creator.get('firstName', '')} {creator.get('lastName', '')}".strip()
            )
            return name or None, creator_id
        elif creator:
            return None, int(creator) if creator else None
        return None, None

    def _get_status(self) -> str | None:
        """Get task status."""
        status = self.raw_data.get("status")
        if status:
            return status

        # Derive from completed flag
        completed = self.raw_data.get("completed", False)
        if completed:
            return "completed"
        return "active"

    def _get_priority(self) -> str | None:
        """Get task priority."""
        priority = self.raw_data.get("priority")
        if priority:
            return priority

        # Some APIs use priority level
        priority_level = self.raw_data.get("priorityLevel")
        if priority_level:
            return str(priority_level)
        return None

    def _get_tags(self) -> list[str]:
        """Get task tags."""
        # First try enriched _tags from batch fetch
        tags = self.raw_data.get("_tags") or self.raw_data.get("tags") or []
        if isinstance(tags, list):
            tag_names = []
            for tag in tags:
                if isinstance(tag, dict):
                    tag_names.append(tag.get("name", ""))
                elif isinstance(tag, str):
                    tag_names.append(tag)
            return [t for t in tag_names if t]
        return []

    def _get_attachments(self) -> list[dict[str, Any]]:
        """Get task attachments from enriched data."""
        return self.raw_data.get("_attachments", [])

    def _get_parent_task_info(self) -> tuple[int | None, str | None]:
        """Get parent task ID and name for subtasks."""
        # First try enriched _parentTask from batch fetch
        parent_task = self.raw_data.get("_parentTask")
        if parent_task and isinstance(parent_task, dict):
            parent_id = int(parent_task.get("id", 0)) if parent_task.get("id") else None
            parent_name = parent_task.get("name")
            return parent_id, parent_name

        # Fallback to basic parentTask reference
        parent_ref = self.raw_data.get("parentTask", {})
        if isinstance(parent_ref, dict):
            parent_id = int(parent_ref.get("id", 0)) if parent_ref.get("id") else None
            parent_name = parent_ref.get("name")
            return parent_id, parent_name

        return None, None

    def get_header_content(self) -> str:
        """Get task header for display."""
        task_id = self.raw_data.get("id", "")
        task_name = self._get_task_name() or "Unnamed Task"
        return f"Task: <{task_id}|{task_name}>"

    def get_content(self) -> str:
        """Generate formatted task content with comments."""
        lines = [self.get_header_content(), ""]

        # Project and task list
        project_name = self.raw_data.get("_project_name") or self._get_project_name()
        if project_name:
            lines.append(f"Project: {project_name}")

        task_list_name = self.raw_data.get("_task_list_name") or self._get_task_list_name()
        if task_list_name:
            lines.append(f"Task List: {task_list_name}")

        # Description
        description = self._get_task_description()
        if description:
            lines.append(f"Description: {description}")

        # Status and priority
        status = self._get_status()
        if status:
            lines.append(f"Status: {status}")

        priority = self._get_priority()
        if priority:
            lines.append(f"Priority: {priority}")

        # Assignee
        assignee_name, _ = self._get_assignee_info()
        if assignee_name:
            lines.append(f"Assigned to: {assignee_name}")

        # Creator
        creator_name, _ = self._get_creator_info()
        if creator_name:
            lines.append(f"Created by: {creator_name}")

        # Dates
        due_date = self.raw_data.get("dueDate") or self.raw_data.get("due-date")
        if due_date:
            lines.append(f"Due date: {self._format_date(due_date)}")

        start_date = self.raw_data.get("startDate") or self.raw_data.get("start-date")
        if start_date:
            lines.append(f"Start date: {self._format_date(start_date)}")

        # Completion info
        completed = self.raw_data.get("completed", False)
        if completed:
            completed_at = self.raw_data.get("completedAt") or self.raw_data.get("completed-at")
            if completed_at:
                lines.append(f"Completed: {self._format_date(completed_at)}")
            else:
                lines.append("Completed: Yes")

        # Estimated time
        estimated_minutes = self.raw_data.get("estimatedMinutes") or self.raw_data.get(
            "estimated-minutes"
        )
        if estimated_minutes is not None and estimated_minutes > 0:
            hours = estimated_minutes // 60
            mins = estimated_minutes % 60
            if hours > 0:
                lines.append(f"Estimated: {hours}h {mins}m")
            else:
                lines.append(f"Estimated: {mins}m")

        # Tags
        tags = self._get_tags()
        if tags:
            lines.append(f"Tags: {', '.join(tags)}")

        # Parent task (for subtasks)
        parent_id, parent_name = self._get_parent_task_info()
        if parent_name:
            lines.append(f"Parent Task: {parent_name}")
        elif parent_id:
            lines.append(f"Parent Task ID: {parent_id}")

        # Attachments
        attachments = self._get_attachments()
        if attachments:
            attachment_names = []
            for att in attachments:
                if isinstance(att, dict):
                    name = att.get("name") or att.get("fileName") or "Unnamed"
                    attachment_names.append(name)
            if attachment_names:
                lines.append(f"Attachments: {', '.join(attachment_names[:5])}")
                if len(attachment_names) > 5:
                    lines.append(f"  (+{len(attachment_names) - 5} more)")

        # Created date
        created_at = self.raw_data.get("createdAt") or self.raw_data.get("created-at")
        if created_at:
            lines.append(f"Created: {self._format_date(created_at)}")

        # Comments
        comments = self.raw_data.get("comments", [])
        if comments and isinstance(comments, list):
            lines.extend(["", "Comments:"])
            for comment in comments:
                if isinstance(comment, dict):
                    comment_data = {**comment, "task_id": self.raw_data.get("id")}
                    chunk = TeamworkTaskChunk(document=self, raw_data=comment_data)
                    lines.append(chunk.get_content())

        return "\n".join(lines)

    def _get_project_name(self) -> str | None:
        """Get project name from task data."""
        project = self.raw_data.get("project", {})
        if isinstance(project, dict):
            return project.get("name")
        return None

    def _get_task_list_name(self) -> str | None:
        """Get task list name from task data."""
        task_list = self.raw_data.get("taskList", {})
        if isinstance(task_list, dict):
            return task_list.get("name")
        return None

    def to_embedding_chunks(self) -> list[TeamworkTaskChunk]:
        """Create chunks for task header and each comment."""
        chunks: list[TeamworkTaskChunk] = []

        # Build header content
        header_lines: list[str] = []
        task_id = self.raw_data.get("id", "")
        task_name = self._get_task_name() or "Unnamed Task"
        header_lines.append(f"Task: <{task_id}|{task_name}>")
        header_lines.append("")

        # Project and task list
        project_name = self.raw_data.get("_project_name") or self._get_project_name()
        if project_name:
            header_lines.append(f"Project: {project_name}")

        task_list_name = self.raw_data.get("_task_list_name") or self._get_task_list_name()
        if task_list_name:
            header_lines.append(f"Task List: {task_list_name}")

        # Description
        description = self._get_task_description()
        if description:
            header_lines.append(f"Description: {description}")

        # Status
        status = self._get_status()
        if status:
            header_lines.append(f"Status: {status}")

        # Priority
        priority = self._get_priority()
        if priority:
            header_lines.append(f"Priority: {priority}")

        # Assignee
        assignee_name, _ = self._get_assignee_info()
        if assignee_name:
            header_lines.append(f"Assigned to: {assignee_name}")

        # Due date
        due_date = self.raw_data.get("dueDate") or self.raw_data.get("due-date")
        if due_date:
            header_lines.append(f"Due date: {self._format_date(due_date)}")

        # Tags
        tags = self._get_tags()
        if tags:
            header_lines.append(f"Tags: {', '.join(tags)}")

        # Parent task (for subtasks)
        parent_id, parent_name = self._get_parent_task_info()
        if parent_name:
            header_lines.append(f"Parent Task: {parent_name}")
        elif parent_id:
            header_lines.append(f"Parent Task ID: {parent_id}")

        # Attachments
        attachments = self._get_attachments()
        if attachments:
            attachment_names = []
            for att in attachments:
                if isinstance(att, dict):
                    name = att.get("name") or att.get("fileName") or "Unnamed"
                    attachment_names.append(name)
            if attachment_names:
                header_lines.append(f"Attachments: {', '.join(attachment_names[:5])}")

        # Create header chunk
        header_content = f"[{self.id}]\n" + "\n".join(header_lines)
        header_chunk = self.chunk_class(
            document=self,
            raw_data={
                "content": header_content,
                **self.get_metadata(),
                "chunk_type": "header",
            },
        )
        self.populate_chunk_permissions(header_chunk)
        chunks.append(header_chunk)

        # Add comments as chunks
        comments = self.raw_data.get("comments", [])
        for comment in comments:
            if isinstance(comment, dict):
                comment_data = {**comment, "task_id": task_id}
                chunk = self.chunk_class(document=self, raw_data=comment_data)
                self.populate_chunk_permissions(chunk)
                chunks.append(chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.TEAMWORK_TASK

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        return "r_teamwork_task_" + self.id.replace("teamwork_task_", "")

    def get_metadata(self) -> TeamworkTaskDocumentMetadata:
        """Get document metadata for search and filtering."""
        if self.metadata is not None:
            return self.metadata

        assignee_name, assignee_id = self._get_assignee_info()
        creator_name, creator_id = self._get_creator_info()

        # Get estimated minutes safely
        estimated_minutes = self.raw_data.get("estimatedMinutes") or self.raw_data.get(
            "estimated-minutes"
        )
        estimated_minutes_int: int | None = None
        if estimated_minutes is not None:
            with contextlib.suppress(ValueError, TypeError):
                estimated_minutes_int = int(estimated_minutes)

        # Get attachment info
        attachments = self._get_attachments()
        has_attachments = len(attachments) > 0
        attachment_count = len(attachments) if has_attachments else None

        # Get parent task info
        parent_task_id, parent_task_name = self._get_parent_task_info()

        metadata: TeamworkTaskDocumentMetadata = {
            "task_id": self.raw_data.get("id"),
            "task_name": self._get_task_name(),
            "project_id": self.raw_data.get("_project_id"),
            "project_name": self.raw_data.get("_project_name") or self._get_project_name(),
            "task_list_name": self.raw_data.get("_task_list_name") or self._get_task_list_name(),
            "status": self._get_status(),
            "priority": self._get_priority(),
            "assignee_name": assignee_name,
            "assignee_id": assignee_id,
            "creator_name": creator_name,
            "creator_id": creator_id,
            "due_date": self.raw_data.get("dueDate") or self.raw_data.get("due-date"),
            "start_date": self.raw_data.get("startDate") or self.raw_data.get("start-date"),
            "completed": self.raw_data.get("completed", False),
            "completed_at": self.raw_data.get("completedAt") or self.raw_data.get("completed-at"),
            "estimated_minutes": estimated_minutes_int,
            "tags": self._get_tags() or None,
            "has_attachments": has_attachments,
            "attachment_count": attachment_count,
            "parent_task_id": parent_task_id,
            "parent_task_name": parent_task_name,
            "source_created_at": convert_timestamp_to_iso(
                self.raw_data.get("createdAt") or self.raw_data.get("created-at")
            ),
            "source_updated_at": convert_timestamp_to_iso(
                self.raw_data.get("updatedAt") or self.raw_data.get("updated-at")
            ),
            "source": self.get_source(),
            "type": "teamwork_task",
        }

        return metadata

    def _format_date(self, date_str: str | None) -> str:
        """Format ISO date string to readable format."""
        if not date_str:
            return ""
        try:
            if "T" in date_str:
                dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return dt.strftime("%Y-%m-%d")
            return date_str
        except Exception:
            return str(date_str)
