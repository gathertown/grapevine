"""
GitHub document classes for structured PR and activity representation.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from src.ingest.references.reference_ids import get_github_pr_reference_id

MAX_FILE_CHUNK_SIZE = 8000
FILE_CHUNK_OVERLAP = 100


class GitHubPRChunkMetadata(TypedDict):
    """Metadata for GitHub PR chunks."""

    event_type: str | None
    action: str | None
    actor: str | None
    actor_id: str | None
    actor_login: str | None
    timestamp: str | None
    formatted_time: str | None
    pr_number: int | None
    pr_title: str | None
    repository: str | None
    organization: str | None
    event_id: str | None
    comment_body: str | None
    comment_id: str | None
    review_state: str | None


class GitHubPRFileChunkMetadata(TypedDict):
    """Metadata for GitHub PR file change chunks."""

    filename: str | None
    status: str | None  # added, modified, removed, renamed
    additions: int | None
    deletions: int | None
    language: str | None
    pr_number: int | None
    pr_title: str | None
    repository: str | None
    organization: str | None


class GitHubPRDocumentMetadata(TypedDict):
    """Metadata for GitHub PR documents."""

    pr_number: int | None
    pr_title: str | None
    pr_url: str | None
    pr_body: str | None
    pr_status: str | None
    pr_draft: bool | None
    pr_merged: bool | None
    pr_commits: int | None
    pr_additions: int | None
    pr_deletions: int | None
    pr_changed_files: int | None
    repository: str | None
    organization: str | None
    repo_spec: str | None
    actual_repo_id: str | None
    source: str | None
    type: str
    event_count: int
    source_created_at: str | None
    source_merged_at: str | None
    ingestion_timestamp: str | None


@dataclass
class GitHubPRChunk(BaseChunk[GitHubPRChunkMetadata]):
    """Represents a single GitHub PR event chunk."""

    def get_content(self) -> str:
        """Get the formatted PR event content."""
        event_type = self.raw_data.get("event_type", "")
        formatted_time = self.raw_data.get("formatted_time", "")
        actor = self.raw_data.get("actor", "")
        action = self.raw_data.get("action", "")

        actor_id = self.raw_data.get("actor_id", "")
        actor_login = self.raw_data.get("actor_login", "")

        if not actor_id or not actor_login:
            actor_display = actor if actor else "unknown"
        else:
            actor_display = f"<@{actor_id}|@{actor_login}>"

        if event_type == "pull_request":
            return f"{formatted_time} {actor_display} {action} pull request"
        elif event_type == "pull_request_review":
            review_state = self.raw_data.get("review_state", "")
            comment_body = self.raw_data.get("comment_body", "")

            if comment_body.strip():
                single_line_body = comment_body.replace("\n", " ").replace("\r", " ")
                single_line_body = " ".join(single_line_body.split())
                return f"{formatted_time} {actor_display} {action} review ({review_state}): {single_line_body}"
            else:
                return f"{formatted_time} {actor_display} {action} review ({review_state})"
        elif event_type == "pull_request_review_comment":
            return f"{formatted_time} {actor_display} commented on review"
        elif event_type == "issue_comment":
            body = self.raw_data.get("comment_body", "")
            single_line_body = body.replace("\n", " ").replace("\r", " ")
            single_line_body = " ".join(single_line_body.split())
            return f"{formatted_time} {actor_display} commented: {single_line_body}"
        else:
            return f"{formatted_time} {actor_display} {action}"

    def get_metadata(self) -> GitHubPRChunkMetadata:
        """Get chunk-specific metadata."""
        metadata: GitHubPRChunkMetadata = {
            "event_type": self.raw_data.get("event_type"),
            "action": self.raw_data.get("action"),
            "actor": self.raw_data.get("actor"),
            "actor_id": self.raw_data.get("actor_id"),
            "actor_login": self.raw_data.get("actor_login"),
            "timestamp": self.raw_data.get("timestamp"),
            "formatted_time": self.raw_data.get("formatted_time"),
            "pr_number": self.raw_data.get("pr_number"),
            "pr_title": self.raw_data.get("pr_title"),
            "repository": self.raw_data.get("repository"),
            "organization": self.raw_data.get("organization"),
            "event_id": self.raw_data.get("event_id"),
            "comment_body": self.raw_data.get("comment_body"),
            "comment_id": self.raw_data.get("comment_id"),
            "review_state": self.raw_data.get("review_state"),
        }

        return metadata


@dataclass
class GitHubPRFileChunk(BaseChunk[GitHubPRFileChunkMetadata]):
    """Represents a single file change in a GitHub PR."""

    def get_content(self) -> str:
        """Get the formatted file change content with diff."""
        filename = self.raw_data.get("filename", "")
        status = self.raw_data.get("status", "")
        additions = self.raw_data.get("additions", 0)
        deletions = self.raw_data.get("deletions", 0)
        patch = self.raw_data.get("patch", "")

        lines = [
            f"File: {filename} ({status})",
            f"+{additions} -{deletions} lines",
        ]

        if patch:
            lines.extend(["", "Diff:", patch])

        return "\n".join(lines)

    def get_metadata(self) -> GitHubPRFileChunkMetadata:
        """Get file chunk metadata."""
        from src.utils.filetype import get_language_from_extension

        filename = self.raw_data.get("filename", "")
        metadata: GitHubPRFileChunkMetadata = {
            "filename": filename,
            "status": self.raw_data.get("status"),
            "additions": self.raw_data.get("additions"),
            "deletions": self.raw_data.get("deletions"),
            "language": get_language_from_extension(filename),
            "pr_number": self.raw_data.get("pr_number"),
            "pr_title": self.raw_data.get("pr_title"),
            "repository": self.raw_data.get("repository"),
            "organization": self.raw_data.get("organization"),
        }
        return metadata


@dataclass
class GitHubPRDocument(BaseDocument[GitHubPRChunk, GitHubPRDocumentMetadata]):
    """Represents a GitHub PR with all its events and activities."""

    raw_data: dict[str, Any]

    def _get_repo_name(self) -> str:
        return self.raw_data.get("repository", "unknown")

    def get_header_content(self) -> str:
        """Get the formatted header section of the document."""
        pr_number = self.raw_data.get("pr_number", "")
        pr_title = self.raw_data.get("pr_title", "")
        pr_url = self.raw_data.get("pr_url", "")
        repository = self._get_repo_name()
        organization = self.raw_data.get("organization", "")
        pr_body = self.raw_data.get("pr_body", "")
        pr_status = self.raw_data.get("pr_status", "")
        events = self.raw_data.get("events", [])

        # Build participants list from events with most recent username per actor
        user_map = {}
        for event in reversed(events):
            actor_id = event.get("actor_id", "")
            actor_login = event.get("actor_login", "")
            actor = event.get("actor", "")
            if actor_id and actor_login and actor and actor_id not in user_map:
                user_map[actor_id] = {"login": actor_login, "name": actor}

        participants_list = [
            f"<@{user_id}|@{user_data['login']}>"
            for user_id, user_data in sorted(user_map.items(), key=lambda x: str(x[0]))
        ]

        # Format PR body to single line
        single_line_body = ""
        if pr_body:
            single_line_body = pr_body.replace("\n", " ").replace("\r", " ")
            single_line_body = " ".join(single_line_body.split())

        lines = [
            f"Repository: {organization}/{repository}",
            f"Pull Request: #{pr_number} - {pr_title}",
            f"URL: {pr_url}",
        ]

        # Add status if available
        if pr_status:
            lines.append(f"Status: {pr_status}")

        lines.extend(
            [f"Participants: {', '.join(participants_list)}", "", "Description:", single_line_body]
        )

        return "\n".join(lines)

    def get_content(self) -> str:
        """Get the formatted document content."""
        events = self.raw_data.get("events", [])
        files = self.raw_data.get("files", [])

        lines = [self.get_header_content()]
        lines.extend(["", "Activity:", ""])

        for event_data in events:
            actor_id = event_data.get("actor_id", "")
            actor_login = event_data.get("actor_login", "")
            if not actor_id or not actor_login:
                continue

            if event_data.get("action") == "edited":
                continue

            chunk = GitHubPRChunk(
                document=self,
                github_repository=self._get_repo_name(),
                raw_data=event_data,
            )
            lines.append(chunk.get_content())

        # Add file changes with patch content
        if files:
            lines.extend(["", "Files Changed:", ""])
            for file in files:
                filename = file.get("filename", "")
                status = file.get("status", "")
                adds = file.get("additions", 0)
                dels = file.get("deletions", 0)
                patch = file.get("patch", "")

                lines.append(f"  {status}: {filename} (+{adds} -{dels})")
                if patch:
                    lines.append("    --/ Patch")
                    # Indent patch content
                    patch_lines = patch.split("\n")
                    for patch_line in patch_lines:
                        lines.append(f"      {patch_line}")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[GitHubPRChunk | GitHubPRFileChunk]:  # type: ignore[override]
        """Convert to embedding chunk format."""
        chunks: list[GitHubPRChunk | GitHubPRFileChunk] = []
        events = self.raw_data.get("events", [])
        files = self.raw_data.get("files", [])
        repo = self._get_repo_name()
        organization = self.raw_data.get("organization", "")
        pr_number = self.raw_data.get("pr_number")
        pr_title = self.raw_data.get("pr_title", "")

        # Add header chunk
        header_chunk = GitHubPRChunk(
            document=self,
            github_repository=repo,
            raw_data={
                "content": self.get_header_content(),
                "pr_number": pr_number,
                "pr_title": pr_title,
                "pr_url": self.raw_data.get("pr_url"),
                "pr_body": self.raw_data.get("pr_body"),
                "pr_status": self.raw_data.get("pr_status"),
                "repository": repo,
                "organization": organization,
                "source": self.raw_data.get("source", self.get_source()),
                "type": "github_pr_header",
                "chunk_type": "header",
                "event_count": len(events),
                "source_created_at": self.raw_data.get("source_created_at"),
            },
        )
        chunks.append(header_chunk)

        # Add activity event chunks
        for event_data in events:
            chunk = GitHubPRChunk(
                document=self,
                github_repository=repo,
                raw_data=event_data,
            )
            chunks.append(chunk)

        # Add file change chunks (split large patches into multiple chunks)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=MAX_FILE_CHUNK_SIZE,
            chunk_overlap=FILE_CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        for file_data in files:
            filename = file_data.get("filename", "")
            status = file_data.get("status", "")
            additions = file_data.get("additions", 0)
            deletions = file_data.get("deletions", 0)
            patch = file_data.get("patch", "")

            # Build base content with file header
            header_lines = [
                f"File: {filename} ({status})",
                f"+{additions} -{deletions} lines",
            ]
            header = "\n".join(header_lines)

            # Common file chunk data (shared across all cases)
            base_file_chunk_data = {
                "filename": filename,
                "status": status,
                "additions": additions,
                "deletions": deletions,
                "changes": file_data.get("changes"),
                "previous_filename": file_data.get("previous_filename"),
                "pr_number": pr_number,
                "pr_title": pr_title,
                "repository": repo,
                "organization": organization,
            }

            patch_chunks_to_create: list[dict[str, Any]] = []

            if patch:
                full_content = f"{header}\n\nDiff:\n{patch}"

                if len(full_content) > MAX_FILE_CHUNK_SIZE:
                    patch_chunks = text_splitter.split_text(patch)

                    for i, patch_chunk in enumerate(patch_chunks):
                        patch_chunks_to_create.append(
                            {
                                "patch": patch_chunk,  # Only this chunk's portion
                                "chunk_index": i,
                                "total_chunks": len(patch_chunks),
                            }
                        )
                else:
                    patch_chunks_to_create.append(
                        {
                            "patch": patch,
                        }
                    )
            else:
                patch_chunks_to_create.append(
                    {
                        "patch": None,
                    }
                )

            for patch_data in patch_chunks_to_create:
                file_chunk_data = {
                    **base_file_chunk_data,
                    **patch_data,
                }
                file_chunk = GitHubPRFileChunk(
                    document=self,
                    github_repository=repo,
                    raw_data=file_chunk_data,
                )
                chunks.append(file_chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.GITHUB_PRS

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        organization = self.raw_data.get("organization", "")
        repository = self._get_repo_name()
        pr_number = str(self.raw_data.get("pr_number", ""))
        return get_github_pr_reference_id(owner=organization, repo=repository, pr_number=pr_number)

    def get_metadata(self) -> GitHubPRDocumentMetadata:
        """Get document metadata."""
        events = self.raw_data.get("events", [])
        metadata: GitHubPRDocumentMetadata = {
            "pr_number": self.raw_data.get("pr_number"),
            "pr_title": self.raw_data.get("pr_title"),
            "pr_url": self.raw_data.get("pr_url"),
            "pr_body": self.raw_data.get("pr_body"),
            "pr_status": self.raw_data.get("pr_status"),
            "pr_draft": self.raw_data.get("pr_draft"),
            "pr_merged": self.raw_data.get("pr_merged"),
            "pr_commits": self.raw_data.get("pr_commits"),
            "pr_additions": self.raw_data.get("pr_additions"),
            "pr_deletions": self.raw_data.get("pr_deletions"),
            "pr_changed_files": self.raw_data.get("pr_changed_files"),
            "repository": self.raw_data.get("repository"),
            "organization": self.raw_data.get("organization"),
            "repo_spec": self.raw_data.get("repo_spec"),
            "actual_repo_id": self.raw_data.get("actual_repo_id"),
            "source": self.raw_data.get("source", self.get_source()),
            "type": "github_pr_document",
            "event_count": len(events),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_merged_at": self.raw_data.get("source_merged_at"),
            "ingestion_timestamp": self.raw_data.get("ingestion_timestamp"),
        }

        return metadata
