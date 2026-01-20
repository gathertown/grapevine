"""Pylon document classes for structured issue representation."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource


class PylonIssueChunkMetadata(TypedDict):
    """Metadata for Pylon issue chunks."""

    chunk_index: int
    total_chunks: int
    issue_id: str


class PylonIssueChunkRawData(PylonIssueChunkMetadata):
    """Raw data for Pylon issue chunks."""

    content: str


class PylonIssueDocumentMetadata(TypedDict):
    """Metadata for Pylon issue documents."""

    issue_id: str
    issue_number: int | None
    issue_title: str | None
    issue_state: str | None
    issue_priority: str | None

    created_at: str | None
    updated_at: str | None

    account_id: str | None
    account_name: str | None

    requester_id: str | None
    requester_email: str | None

    assignee_id: str | None
    assignee_email: str | None

    team_id: str | None
    team_name: str | None


@dataclass
class PylonIssueChunk(BaseChunk[PylonIssueChunkMetadata]):
    """Chunk from a Pylon issue document."""

    def get_content(self) -> str:
        content = self.raw_data.get("content", "")
        chunk_index = self.raw_data.get("chunk_index", 0)
        total_chunks = self.raw_data.get("total_chunks", 1)

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> PylonIssueChunkMetadata:
        return PylonIssueChunkMetadata(
            issue_id=self.raw_data["issue_id"],
            chunk_index=self.raw_data.get("chunk_index", -1),
            total_chunks=self.raw_data.get("total_chunks", -1),
        )


class RawDataUser(TypedDict):
    """User info in raw data."""

    id: str
    name: str | None
    email: str | None


class RawDataContact(TypedDict):
    """Contact info in raw data."""

    id: str
    name: str | None
    email: str | None


class RawDataAccount(TypedDict):
    """Account info in raw data."""

    id: str
    name: str | None
    domains: list[str] | None


class RawDataTeam(TypedDict):
    """Team info in raw data."""

    id: str
    name: str | None


class RawDataCsatResponse(TypedDict):
    """CSAT response in raw data."""

    score: int | None
    comment: str | None


class RawDataExternalIssue(TypedDict):
    """External issue reference in raw data."""

    source: str | None
    external_id: str | None
    link: str | None


class RawDataRequester(TypedDict):
    """Requester info in raw data."""

    id: str | None
    name: str | None
    email: str | None


class PylonIssueDocumentRawData(TypedDict):
    """Raw data for Pylon issue documents."""

    id: str
    number: int | None
    title: str | None
    body_html: str | None
    state: str | None
    priority: str | None
    tags: list[str] | None

    created_at: str | None
    updated_at: str | None

    # Time metrics - these are strings (RFC3339) not integers
    first_response_time: str | None
    resolution_time: str | None
    # Seconds metrics
    first_response_seconds: int | None
    resolution_seconds: int | None

    account: RawDataAccount | None
    team: RawDataTeam | None

    requester: RawDataRequester | None

    assignee: RawDataUser | None

    csat_responses: list[RawDataCsatResponse]
    external_issues: list[RawDataExternalIssue]

    custom_fields: dict[str, object] | None


@dataclass
class PylonIssueDocument(BaseDocument[PylonIssueChunk, PylonIssueDocumentMetadata]):
    """Document representing a Pylon support issue."""

    raw_data: PylonIssueDocumentRawData

    def get_header_content(self) -> str:
        """Generate structured header content for the issue."""
        lines: list[str] = []

        lines.append("# Pylon Support Issue")
        lines.append(f"- Title: {self.raw_data['title'] or ''}")
        lines.append(f"- Issue ID: {self.raw_data['id']}")
        if self.raw_data["number"]:
            lines.append(f"- Issue Number: #{self.raw_data['number']}")
        lines.append(f"- Status: {self.raw_data['state'] or 'Unknown'}")
        lines.append(f"- Priority: {self.raw_data['priority'] or 'Not set'}")
        lines.append(
            f"- Tags: {', '.join(self.raw_data['tags']) if self.raw_data['tags'] else 'None'}"
        )
        lines.append(f"- Created At: {self.raw_data['created_at'] or ''}")
        lines.append(f"- Updated At: {self.raw_data['updated_at'] or ''}")

        lines.append("\n## People Involved")
        lines.append(f"- Assignee: {self._get_user_content(self.raw_data['assignee'])}")
        lines.append(f"- Requester: {self._get_requester_content()}")

        if self.raw_data["account"]:
            lines.append("\n## Account")
            lines.append(f"- Name: {self.raw_data['account']['name'] or 'Unknown'}")
            if self.raw_data["account"]["domains"]:
                lines.append(f"- Domains: {', '.join(self.raw_data['account']['domains'])}")

        if self.raw_data["team"]:
            lines.append("\n## Team")
            lines.append(f"- Name: {self.raw_data['team']['name'] or 'Unknown'}")

        # Metrics
        if self.raw_data["first_response_seconds"] or self.raw_data["resolution_seconds"]:
            lines.append("\n## Metrics")
            if self.raw_data["first_response_seconds"]:
                minutes = self.raw_data["first_response_seconds"] // 60
                lines.append(f"- First Response Time: {minutes} minutes")
            if self.raw_data["resolution_seconds"]:
                minutes = self.raw_data["resolution_seconds"] // 60
                lines.append(f"- Resolution Time: {minutes} minutes")

        # CSAT
        if self.raw_data["csat_responses"]:
            lines.append("\n## Customer Satisfaction")
            for csat in self.raw_data["csat_responses"]:
                if csat["score"]:
                    lines.append(f"- Score: {csat['score']}")
                if csat["comment"]:
                    lines.append(f"- Comment: {csat['comment']}")

        # External issues
        if self.raw_data["external_issues"]:
            lines.append("\n## Linked External Issues")
            for ext in self.raw_data["external_issues"]:
                source = ext.get("source") or "Unknown"
                ext_id = ext.get("external_id") or "N/A"
                lines.append(f"- {source.title()}: {ext_id}")

        # Custom fields
        if self.raw_data["custom_fields"]:
            lines.append("\n## Custom Fields")
            for key, value in self.raw_data["custom_fields"].items():
                lines.append(f"- {key}: {value}")

        return "\n".join(lines)

    def _get_user_content(self, user: RawDataUser | None) -> str:
        if not user:
            return "Not assigned"
        parts: list[str] = []
        name = user.get("name")
        email = user.get("email")
        if name:
            parts.append(name)
        if email:
            parts.append(f"<{email}>")
        if not parts:
            parts.append(f"@{user['id']}")
        return " ".join(parts)

    def _get_requester_content(self) -> str:
        requester = self.raw_data["requester"]
        if not requester:
            return "Unknown"

        parts: list[str] = []
        name = requester.get("name")
        email = requester.get("email")
        requester_id = requester.get("id")
        if name:
            parts.append(name)
        if email:
            parts.append(f"<{email}>")
        if not parts and requester_id:
            parts.append(f"@{requester_id}")
        return " ".join(parts) if parts else "Unknown"

    def get_content(self) -> str:
        """Get full document content including header and body."""
        parts = [self.get_header_content()]

        if self.raw_data["body_html"]:
            parts.append("\n## Issue Description")
            # Strip HTML tags for plain text representation
            body = self._strip_html(self.raw_data["body_html"])
            parts.append(body)

        return "\n\n".join(parts)

    def _strip_html(self, html: str) -> str:
        """Simple HTML stripping - removes tags but keeps content."""
        import re

        # Remove script and style elements
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Replace br and p tags with newlines
        html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</p>", "\n\n", html, flags=re.IGNORECASE)
        html = re.sub(r"</div>", "\n", html, flags=re.IGNORECASE)
        # Remove remaining tags
        html = re.sub(r"<[^>]+>", "", html)
        # Clean up whitespace
        html = re.sub(r"\n{3,}", "\n\n", html)
        return html.strip()

    def to_embedding_chunks(self) -> list[PylonIssueChunk]:
        """Split document into chunks for embedding."""
        full_content = self.get_content()

        if not full_content.strip():
            return []

        # Use RecursiveCharacterTextSplitter with overlap for better context
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=200,  # 200 char overlap for context continuity
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        text_chunks = text_splitter.split_text(full_content)
        embedding_chunks: list[PylonIssueChunk] = []

        for i, chunk_text in enumerate(text_chunks):
            chunk_data = PylonIssueChunkRawData(
                issue_id=self.raw_data["id"],
                content=chunk_text,
                chunk_index=i,
                total_chunks=len(text_chunks),
            )

            chunk = PylonIssueChunk(document=self, raw_data=chunk_data)
            embedding_chunks.append(chunk)

        return embedding_chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.PYLON_ISSUE

    def get_reference_id(self) -> str:
        issue_id = self.raw_data.get("id")
        return f"r_pylon_issue_{issue_id}"

    def get_metadata(self) -> PylonIssueDocumentMetadata:
        requester = self.raw_data["requester"]
        return PylonIssueDocumentMetadata(
            issue_id=self.raw_data["id"],
            issue_number=self.raw_data["number"],
            issue_title=self.raw_data["title"],
            issue_state=self.raw_data["state"],
            issue_priority=self.raw_data["priority"],
            created_at=self.raw_data["created_at"],
            updated_at=self.raw_data["updated_at"],
            account_id=self.raw_data["account"]["id"] if self.raw_data["account"] else None,
            account_name=self.raw_data["account"]["name"] if self.raw_data["account"] else None,
            requester_id=requester.get("id") if requester else None,
            requester_email=requester.get("email") if requester else None,
            assignee_id=self.raw_data["assignee"]["id"] if self.raw_data["assignee"] else None,
            assignee_email=self.raw_data["assignee"]["email"]
            if self.raw_data["assignee"]
            else None,
            team_id=self.raw_data["team"]["id"] if self.raw_data["team"] else None,
            team_name=self.raw_data["team"]["name"] if self.raw_data["team"] else None,
        )

    def get_source_created_at(self) -> datetime:
        created_at = self.get_metadata()["created_at"]
        if created_at:
            return datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return datetime.now(UTC)


def pylon_issue_document_id(issue_id: str) -> str:
    """Generate document ID for a Pylon issue."""
    return f"pylon_issue_{issue_id}"
