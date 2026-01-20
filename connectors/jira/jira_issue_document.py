"""
Jira document classes for structured issue and activity representation.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from src.ingest.references.reference_ids import get_jira_issue_reference_id


class JiraIssueChunkMetadata(TypedDict):
    """Metadata for Jira issue chunks."""

    activity_type: str | None  # "comment", "status_change", "assignment", etc.
    actor: str | None  # Display name of user who performed action
    actor_id: str | None  # Jira user ID
    timestamp: str | None  # ISO timestamp of activity
    formatted_time: str | None  # Human-readable timestamp
    issue_id: str | None  # Jira internal issue ID (numeric string format, e.g., "10218")
    issue_key: str | None  # Jira issue key (e.g., "PROJ-123")
    issue_title: str | None
    project_id: str | None
    project_name: str | None
    activity_id: str | None  # Unique ID for this activity
    comment_body: str | None  # For comment activities
    comment_id: str | None  # Jira comment ID
    old_status: str | None  # For status change activities
    new_status: str | None
    assignee: str | None  # Current assignee display name
    assignee_id: str | None  # Current assignee ID
    priority: str | None
    labels: list[str] | None


class JiraIssueDocumentMetadata(TypedDict):
    """Metadata for Jira issue documents."""

    issue_id: str  # "Issue ID" field
    issue: str  # "Issue" field with formatted link
    url: str  # "URL" field
    assignee: str  # "Assignee" field
    participants: dict[str, str]  # "Participants" field as object
    project: str  # "Project" field with formatted link
    status: str  # "Status" field
    priority: str  # "Priority" field
    source_created_at: str | None  # For base document


@dataclass
class JiraIssueChunk(BaseChunk[JiraIssueChunkMetadata]):
    """
    A chunk representing either the header section or a single activity item from a Jira issue.
    """

    def get_content(self) -> str:
        """Get formatted content for this chunk."""
        # This is a placeholder - content should be set during construction
        return self.raw_data.get("content", "")

    def get_metadata(self) -> JiraIssueChunkMetadata:
        """Get chunk metadata."""
        return self.raw_data  # type: ignore

    def get_reference_id(self) -> str:
        """Generate a reference ID for this chunk."""
        issue_id = self.raw_data.get("issue_id")
        if not issue_id:
            return f"jira_issue_chunk_{id(self)}"

        activity_id = self.raw_data.get("activity_id")
        if activity_id:
            return f"jira_issue_{issue_id}_activity_{activity_id}"
        else:
            # This is the header chunk
            return f"jira_issue_{issue_id}_header"


@dataclass
class JiraIssueDocument(BaseDocument[JiraIssueChunk, JiraIssueDocumentMetadata]):
    """
    A document representing a complete Jira issue with its header and all activities.
    """

    raw_data: dict[str, Any]

    def get_content(self) -> str:
        """Get document content by combining all chunks."""
        return "\n".join(chunk.get_content() for chunk in self.to_embedding_chunks())

    def get_metadata(self) -> JiraIssueDocumentMetadata:
        return {
            "issue_id": self.raw_data.get("issue_id", ""),
            "issue": self.raw_data.get("issue", ""),
            "url": self.raw_data.get("url", ""),
            "assignee": self.raw_data.get("assignee", ""),
            "participants": self.raw_data.get("participants", {}),
            "project": self.raw_data.get("project", ""),
            "status": self.raw_data.get("status", ""),
            "priority": self.raw_data.get("priority", ""),
            "source_created_at": self.raw_data.get("source_created_at"),  # For base document
        }

    def get_source_enum(self) -> DocumentSource:
        """Get document source enum."""
        return DocumentSource.JIRA

    def to_embedding_chunks(self) -> list[JiraIssueChunk]:
        """Convert document to embedding chunks."""
        chunks = []
        activities = self.raw_data.get("activities", [])

        # Create header chunk
        header_data = dict(self.raw_data)
        header_data["activity_type"] = "header"
        header_data["content"] = self._get_header_content()
        chunks.append(JiraIssueChunk(document=self, raw_data=header_data))

        # Create activity chunks with "Activity:" header before the first one
        for idx, activity in enumerate(activities):
            activity_data = dict(self.raw_data)
            activity_data.update(activity)

            # Add "Activity:" header before the first activity's content
            if idx == 0 and "content" in activity_data:
                activity_data["content"] = f"\nActivity:\n{activity_data['content']}"

            chunks.append(JiraIssueChunk(document=self, raw_data=activity_data))

        return chunks

    def _get_header_content(self) -> str:
        """Generate header content for the issue with the required format."""
        issue_key = self.raw_data.get("issue_id", "")  # Issue key like "ECS-6"
        issue_internal_id = self.raw_data.get("issue_internal_id", "")
        issue_title = self.raw_data.get("issue_title", "")
        url = self.raw_data.get("url", "")
        assignee = self.raw_data.get("assignee", "Unassigned")
        participants_text = self.raw_data.get("participants_text", "")
        project = self.raw_data.get("project", "")
        parent_issue = self.raw_data.get("parent_issue", "")
        status = self.raw_data.get("status", "")
        priority = self.raw_data.get("priority", "")
        labels_text = self.raw_data.get("labels_text", "")

        # Build header in the required format
        header_lines = [
            f"Issue Key: {issue_key}",
            "",
            f"Issue: <{issue_internal_id}|{issue_title}>",
            f"URL: {url}",
            f"Assignee: {assignee}",
        ]

        # Add participants if available
        if participants_text:
            header_lines.append(f"Participants: {participants_text}")

        header_lines.append(f"Project: {project}")

        # Add parent issue if available
        if parent_issue:
            header_lines.append(f"Parent Issue: {parent_issue}")

        header_lines.extend(
            [
                f"Status: {status}",
                f"Priority: {priority}",
            ]
        )

        # Add labels if available
        if labels_text:
            header_lines.append(f"Labels: {labels_text}")

        # Add description if available
        description = self._extract_description()
        if description:
            header_lines.extend(["", "Description:", description])

        return "\n".join(header_lines)

    def _extract_issue_title(self) -> str:
        """Extract the issue title from the raw data."""
        # Try to extract from the issue field which has format <id|title>
        issue_field = self.raw_data.get("issue", "")
        if issue_field and "|" in issue_field:
            # Extract title from <id|title> format
            parts = issue_field.split("|", 1)
            if len(parts) > 1:
                title = parts[1].rstrip(">")
                return title

        # Fallback to extracting from fields.summary
        fields = self.raw_data.get("fields", {})
        if isinstance(fields, dict):
            summary = fields.get("summary", "")
            if summary:
                return summary

        return "Untitled Issue"

    def _extract_custom_properties(self) -> list[str]:
        """Extract custom fields and properties from the issue."""
        # This would be populated from custom fields in the Jira issue data
        # For now, return empty list - can be enhanced later
        return []

    def _extract_description(self) -> str:
        """Extract the issue description from the raw data."""
        # Try to get description from various possible locations
        # From fields.description in the raw issue data
        fields = self.raw_data.get("fields", {})
        if not isinstance(fields, dict):
            return ""

        description_raw = fields.get("description", "")

        # If description is a complex object (ADF format), extract text
        if isinstance(description_raw, dict):
            return self._extract_text_from_adf(description_raw)

        # If it's already a string, return it
        if isinstance(description_raw, str):
            return description_raw

        # For any other type, return empty string
        return ""

    def _extract_text_from_adf(self, adf_content: dict) -> str:
        """Extract plain text from Atlassian Document Format (ADF)."""
        # Simple ADF text extraction - can be enhanced for complex formatting
        content = adf_content.get("content", [])
        if not isinstance(content, list):
            return ""

        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "paragraph":
                para_content = item.get("content", [])
                for para_item in para_content:
                    if isinstance(para_item, dict) and para_item.get("type") == "text":
                        text_parts.append(para_item.get("text", ""))

        return " ".join(text_parts)

    def get_reference_id(self) -> str:
        """Generate a reference ID for this document."""
        issue_id = self.raw_data.get("issue_id")
        if issue_id:
            return get_jira_issue_reference_id(issue_id)
        return f"jira_issue_{self.id}"
