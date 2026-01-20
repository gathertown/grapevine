"""
GitLab document classes for structured MR and activity representation.
"""

from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from src.ingest.references.reference_ids import get_gitlab_mr_reference_id

MAX_DIFF_CHUNK_SIZE = 8000
DIFF_CHUNK_OVERLAP = 100


class GitLabMRChunkMetadata(TypedDict):
    """Metadata for GitLab MR chunks."""

    event_type: str | None
    action: str | None
    actor: str | None
    actor_username: str | None
    timestamp: str | None
    formatted_time: str | None
    mr_iid: int | None
    mr_title: str | None
    project_path: str | None
    event_id: str | None
    note_body: str | None
    system: bool | None


class GitLabMRDiffChunkMetadata(TypedDict):
    """Metadata for GitLab MR diff/file change chunks."""

    old_path: str | None
    new_path: str | None
    status: str | None  # added, modified, deleted, renamed
    language: str | None
    mr_iid: int | None
    mr_title: str | None
    project_path: str | None


class GitLabMRDocumentMetadata(TypedDict):
    """Metadata for GitLab MR documents."""

    mr_iid: int | None
    mr_title: str | None
    mr_url: str | None
    mr_description: str | None
    mr_state: str | None
    mr_draft: bool | None
    mr_merged: bool | None
    mr_changes_count: int | None
    project_path: str | None
    project_id: int | None
    source_branch: str | None
    target_branch: str | None
    source: str | None
    type: str
    event_count: int
    source_created_at: str | None
    source_merged_at: str | None
    ingestion_timestamp: str | None


@dataclass
class GitLabMRChunk(BaseChunk[GitLabMRChunkMetadata]):
    """Represents a single GitLab MR event chunk."""

    def get_content(self) -> str:
        """Get the formatted MR event content."""
        # Handle header chunks
        if self.raw_data.get("chunk_type") == "header":
            return self.raw_data.get("content", "")

        event_type = self.raw_data.get("event_type", "")
        formatted_time = self.raw_data.get("formatted_time", "")
        actor = self.raw_data.get("actor", "")
        actor_username = self.raw_data.get("actor_username", "")
        action = self.raw_data.get("action", "")

        if actor_username:
            actor_display = f"@{actor_username}"
            if actor and actor != actor_username:
                actor_display = f"{actor} ({actor_display})"
        else:
            actor_display = actor if actor else "unknown"

        if event_type == "merge_request":
            return f"{formatted_time} {actor_display} {action} merge request"
        elif event_type == "note":
            note_body = self.raw_data.get("note_body", "")
            system = self.raw_data.get("system", False)

            if system:
                # System notes are auto-generated (e.g., "assigned to @user")
                single_line_body = note_body.replace("\n", " ").replace("\r", " ")
                single_line_body = " ".join(single_line_body.split())
                return f"{formatted_time} [system] {single_line_body}"
            else:
                single_line_body = note_body.replace("\n", " ").replace("\r", " ")
                single_line_body = " ".join(single_line_body.split())
                return f"{formatted_time} {actor_display} commented: {single_line_body}"
        elif event_type == "approval":
            return f"{formatted_time} {actor_display} approved merge request"
        else:
            return f"{formatted_time} {actor_display} {action}"

    def get_metadata(self) -> GitLabMRChunkMetadata:
        """Get chunk-specific metadata."""
        metadata: GitLabMRChunkMetadata = {
            "event_type": self.raw_data.get("event_type"),
            "action": self.raw_data.get("action"),
            "actor": self.raw_data.get("actor"),
            "actor_username": self.raw_data.get("actor_username"),
            "timestamp": self.raw_data.get("timestamp"),
            "formatted_time": self.raw_data.get("formatted_time"),
            "mr_iid": self.raw_data.get("mr_iid"),
            "mr_title": self.raw_data.get("mr_title"),
            "project_path": self.raw_data.get("project_path"),
            "event_id": self.raw_data.get("event_id"),
            "note_body": self.raw_data.get("note_body"),
            "system": self.raw_data.get("system"),
        }

        return metadata


@dataclass
class GitLabMRDiffChunk(BaseChunk[GitLabMRDiffChunkMetadata]):
    """Represents a single file change in a GitLab MR."""

    def get_content(self) -> str:
        """Get the formatted file change content with diff."""
        old_path = self.raw_data.get("old_path", "")
        new_path = self.raw_data.get("new_path", "")
        new_file = self.raw_data.get("new_file", False)
        deleted_file = self.raw_data.get("deleted_file", False)
        renamed_file = self.raw_data.get("renamed_file", False)
        diff = self.raw_data.get("diff", "")

        # Determine status
        if new_file:
            status = "added"
            display_path = new_path
        elif deleted_file:
            status = "deleted"
            display_path = old_path
        elif renamed_file:
            status = "renamed"
            display_path = f"{old_path} -> {new_path}"
        else:
            status = "modified"
            display_path = new_path

        lines = [
            f"File: {display_path} ({status})",
        ]

        if diff:
            lines.extend(["", "Diff:", diff])

        return "\n".join(lines)

    def get_metadata(self) -> GitLabMRDiffChunkMetadata:
        """Get file chunk metadata."""
        from src.utils.filetype import get_language_from_extension

        new_path = self.raw_data.get("new_path", "")
        old_path = self.raw_data.get("old_path", "")
        new_file = self.raw_data.get("new_file", False)
        deleted_file = self.raw_data.get("deleted_file", False)
        renamed_file = self.raw_data.get("renamed_file", False)

        # Determine status
        if new_file:
            status = "added"
        elif deleted_file:
            status = "deleted"
        elif renamed_file:
            status = "renamed"
        else:
            status = "modified"

        # Use new_path for language detection (or old_path if deleted)
        path_for_lang = new_path if new_path else old_path

        metadata: GitLabMRDiffChunkMetadata = {
            "old_path": old_path,
            "new_path": new_path,
            "status": status,
            "language": get_language_from_extension(path_for_lang),
            "mr_iid": self.raw_data.get("mr_iid"),
            "mr_title": self.raw_data.get("mr_title"),
            "project_path": self.raw_data.get("project_path"),
        }
        return metadata


@dataclass
class GitLabMRDocument(BaseDocument[GitLabMRChunk, GitLabMRDocumentMetadata]):
    """Represents a GitLab MR with all its events and activities."""

    raw_data: dict[str, Any]

    def _get_project_path(self) -> str:
        return self.raw_data.get("project_path", "unknown")

    def get_header_content(self) -> str:
        """Get the formatted header section of the document."""
        mr_iid = self.raw_data.get("mr_iid", "")
        mr_title = self.raw_data.get("mr_title", "")
        mr_url = self.raw_data.get("mr_url", "")
        project_path = self._get_project_path()
        mr_description = self.raw_data.get("mr_description", "")
        mr_state = self.raw_data.get("mr_state", "")
        source_branch = self.raw_data.get("source_branch", "")
        target_branch = self.raw_data.get("target_branch", "")
        events = self.raw_data.get("events", [])

        # Build participants list from events
        participants_set: set[str] = set()
        for event in events:
            actor_username = event.get("actor_username", "")
            if actor_username:
                participants_set.add(f"@{actor_username}")

        participants_list = sorted(participants_set)

        # Format MR description to single line
        single_line_description = ""
        if mr_description:
            single_line_description = mr_description.replace("\n", " ").replace("\r", " ")
            single_line_description = " ".join(single_line_description.split())

        lines = [
            f"Project: {project_path}",
            f"Merge Request: !{mr_iid} - {mr_title}",
            f"URL: {mr_url}",
        ]

        # Add branch info if available
        if source_branch and target_branch:
            lines.append(f"Branches: {source_branch} -> {target_branch}")

        # Add status if available
        if mr_state:
            lines.append(f"Status: {mr_state}")

        if participants_list:
            lines.append(f"Participants: {', '.join(participants_list)}")

        lines.extend(["", "Description:", single_line_description])

        return "\n".join(lines)

    def get_content(self) -> str:
        """Get the formatted document content."""
        events = self.raw_data.get("events", [])
        diffs = self.raw_data.get("diffs", [])

        lines = [self.get_header_content()]
        lines.extend(["", "Activity:", ""])

        for event_data in events:
            chunk = GitLabMRChunk(
                document=self,
                raw_data=event_data,
            )
            lines.append(chunk.get_content())

        # Add file changes with diff content
        if diffs:
            lines.extend(["", "Files Changed:", ""])
            for diff_data in diffs:
                old_path = diff_data.get("old_path", "")
                new_path = diff_data.get("new_path", "")
                new_file = diff_data.get("new_file", False)
                deleted_file = diff_data.get("deleted_file", False)
                renamed_file = diff_data.get("renamed_file", False)
                diff_content = diff_data.get("diff", "")

                # Determine status and display path
                if new_file:
                    status = "added"
                    display_path = new_path
                elif deleted_file:
                    status = "deleted"
                    display_path = old_path
                elif renamed_file:
                    status = "renamed"
                    display_path = f"{old_path} -> {new_path}"
                else:
                    status = "modified"
                    display_path = new_path

                lines.append(f"  {status}: {display_path}")
                if diff_content:
                    lines.append("    --/ Diff")
                    # Indent diff content
                    diff_lines = diff_content.split("\n")
                    for diff_line in diff_lines:
                        lines.append(f"      {diff_line}")

        return "\n".join(lines)

    def to_embedding_chunks(self) -> list[GitLabMRChunk | GitLabMRDiffChunk]:  # type: ignore[override]
        """Convert to embedding chunk format."""
        chunks: list[GitLabMRChunk | GitLabMRDiffChunk] = []
        events = self.raw_data.get("events", [])
        diffs = self.raw_data.get("diffs", [])
        project_path = self._get_project_path()
        mr_iid = self.raw_data.get("mr_iid")
        mr_title = self.raw_data.get("mr_title", "")

        # Add header chunk
        header_chunk = GitLabMRChunk(
            document=self,
            raw_data={
                "content": self.get_header_content(),
                "mr_iid": mr_iid,
                "mr_title": mr_title,
                "mr_url": self.raw_data.get("mr_url"),
                "mr_description": self.raw_data.get("mr_description"),
                "mr_state": self.raw_data.get("mr_state"),
                "project_path": project_path,
                "source": self.raw_data.get("source", self.get_source()),
                "type": "gitlab_mr_header",
                "chunk_type": "header",
                "event_count": len(events),
                "source_created_at": self.raw_data.get("source_created_at"),
            },
        )
        chunks.append(header_chunk)

        # Add activity event chunks
        for event_data in events:
            chunk = GitLabMRChunk(
                document=self,
                raw_data=event_data,
            )
            chunks.append(chunk)

        # Add diff chunks (split large diffs into multiple chunks)
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=MAX_DIFF_CHUNK_SIZE,
            chunk_overlap=DIFF_CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        for diff_data in diffs:
            old_path = diff_data.get("old_path", "")
            new_path = diff_data.get("new_path", "")
            new_file = diff_data.get("new_file", False)
            deleted_file = diff_data.get("deleted_file", False)
            renamed_file = diff_data.get("renamed_file", False)
            diff_content = diff_data.get("diff", "")

            # Determine status and display path for header
            if new_file:
                status = "added"
                display_path = new_path
            elif deleted_file:
                status = "deleted"
                display_path = old_path
            elif renamed_file:
                status = "renamed"
                display_path = f"{old_path} -> {new_path}"
            else:
                status = "modified"
                display_path = new_path

            # Build base content with file header
            header = f"File: {display_path} ({status})"

            # Common diff chunk data
            base_diff_chunk_data = {
                "old_path": old_path,
                "new_path": new_path,
                "new_file": new_file,
                "deleted_file": deleted_file,
                "renamed_file": renamed_file,
                "mr_iid": mr_iid,
                "mr_title": mr_title,
                "project_path": project_path,
            }

            diff_chunks_to_create: list[dict[str, Any]] = []

            if diff_content:
                full_content = f"{header}\n\nDiff:\n{diff_content}"

                if len(full_content) > MAX_DIFF_CHUNK_SIZE:
                    diff_text_chunks = text_splitter.split_text(diff_content)

                    for i, diff_text_chunk in enumerate(diff_text_chunks):
                        diff_chunks_to_create.append(
                            {
                                "diff": diff_text_chunk,
                                "chunk_index": i,
                                "total_chunks": len(diff_text_chunks),
                            }
                        )
                else:
                    diff_chunks_to_create.append(
                        {
                            "diff": diff_content,
                        }
                    )
            else:
                diff_chunks_to_create.append(
                    {
                        "diff": None,
                    }
                )

            for chunk_data in diff_chunks_to_create:
                diff_chunk_data = {
                    **base_diff_chunk_data,
                    **chunk_data,
                }
                diff_chunk = GitLabMRDiffChunk(
                    document=self,
                    raw_data=diff_chunk_data,
                )
                chunks.append(diff_chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.GITLAB_MR

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        project_path = self._get_project_path()
        mr_iid = str(self.raw_data.get("mr_iid", ""))
        return get_gitlab_mr_reference_id(project_path=project_path, mr_iid=mr_iid)

    def get_metadata(self) -> GitLabMRDocumentMetadata:
        """Get document metadata."""
        events = self.raw_data.get("events", [])
        metadata: GitLabMRDocumentMetadata = {
            "mr_iid": self.raw_data.get("mr_iid"),
            "mr_title": self.raw_data.get("mr_title"),
            "mr_url": self.raw_data.get("mr_url"),
            "mr_description": self.raw_data.get("mr_description"),
            "mr_state": self.raw_data.get("mr_state"),
            "mr_draft": self.raw_data.get("mr_draft"),
            "mr_merged": self.raw_data.get("mr_merged"),
            "mr_changes_count": self.raw_data.get("mr_changes_count"),
            "project_path": self.raw_data.get("project_path"),
            "project_id": self.raw_data.get("project_id"),
            "source_branch": self.raw_data.get("source_branch"),
            "target_branch": self.raw_data.get("target_branch"),
            "source": self.raw_data.get("source", self.get_source()),
            "type": "gitlab_mr_document",
            "event_count": len(events),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_merged_at": self.raw_data.get("source_merged_at"),
            "ingestion_timestamp": self.raw_data.get("ingestion_timestamp"),
        }

        return metadata
