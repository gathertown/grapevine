"""GitLab file document classes for structured file and chunk representation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from src.ingest.references.reference_ids import get_gitlab_file_reference_id


class GitLabFileChunkMetadata(TypedDict):
    """Metadata for GitLab file chunks."""

    chunk_index: int
    total_chunks: int
    file_path: str
    file_extension: str
    chunk_size: int | None
    source_created_at: str | None


class GitLabFileDocumentMetadata(TypedDict):
    """Metadata for GitLab file documents."""

    file_path: str
    file_extension: str
    project_id: int
    project_path: str
    contributors: list[dict[str, Any]]
    contributor_count: int
    source_created_at: str | None
    source_branch: str | None
    source_commit_sha: str | None
    source: str
    type: str
    chunk_count: int


@dataclass
class GitLabFileChunk(BaseChunk["GitLabFileChunkMetadata"]):
    """Represents a single GitLab file content chunk."""

    def get_content(self) -> str:
        """Get the formatted chunk content."""
        if self.raw_data.get("chunk_type") == "header":
            return self.raw_data.get("content", "")
        return self.raw_data.get("content", "")

    def get_metadata(self) -> "GitLabFileChunkMetadata":
        """Get chunk-specific metadata."""
        return {
            "chunk_index": self.raw_data.get("chunk_index", 0),
            "total_chunks": self.raw_data.get("total_chunks", 1),
            "file_path": self.raw_data.get("file_path", ""),
            "file_extension": self.raw_data.get("file_extension", ""),
            "chunk_size": self.raw_data.get("chunk_size"),
            "source_created_at": self.raw_data.get("source_created_at"),
        }


@dataclass
class GitLabFileDocument(BaseDocument[GitLabFileChunk, "GitLabFileDocumentMetadata"]):
    """Represents a GitLab file document with metadata and content."""

    raw_data: dict[str, Any]

    def _get_project_path(self) -> str:
        return self.raw_data.get("project_path", "unknown")

    def get_header_content(self) -> str:
        """Get the formatted header section of the document."""
        file_path = self.raw_data.get("file_path", "")
        file_extension = Path(file_path).suffix.lower()
        contributors = self.raw_data.get("contributors", [])
        source_created_at = self.raw_data.get("source_created_at", "")
        project_path = self._get_project_path()
        project_id = self.raw_data.get("project_id", 0)

        lines = [
            f"# File: {file_path}",
            f"Extension: {file_extension}",
            f"Project: {project_path}",
            f"Project ID: {project_id}",
        ]

        if source_created_at:
            lines.append(f"Last Modified: {source_created_at}")

        if contributors:
            lines.append(f"Contributors: {len(contributors)}")
            sorted_contributors = sorted(
                contributors, key=lambda c: c.get("commit_count", 0), reverse=True
            )
            for i, contributor in enumerate(sorted_contributors[:3]):
                name = contributor.get("name", "Unknown")
                commit_count = contributor.get("commit_count", 0)
                lines.append(f"  {i + 1}. {name} ({commit_count} commits)")

        return "\n".join(lines)

    def get_content(self) -> str:
        """Get the raw file content without headers."""
        chunks = self.raw_data.get("chunks", [])
        content_parts = []
        for chunk_data in chunks:
            content = chunk_data.get("content", "")
            if content.strip():
                content_parts.append(content)
        return "\n".join(content_parts)

    def to_embedding_chunks(self) -> list[GitLabFileChunk]:
        """Convert to embedding chunk format."""
        chunks = []
        file_chunks = self.raw_data.get("chunks", [])
        project_path = self._get_project_path()
        project_id = self.raw_data.get("project_id", 0)
        total_chunks = len(file_chunks) + 1  # +1 for header chunk

        # Create header chunk at index 0
        header_chunk = GitLabFileChunk(
            document=self,
            raw_data={
                "content": self.get_header_content(),
                "file_path": self.raw_data.get("file_path"),
                "file_extension": Path(self.raw_data.get("file_path", "")).suffix.lower(),
                "project_id": project_id,
                "project_path": project_path,
                "contributors": self.raw_data.get("contributors", []),
                "contributor_count": self.raw_data.get("contributor_count", 0),
                "source_created_at": self.raw_data.get("source_created_at"),
                "source": self.get_source(),
                "type": "gitlab_file_header",
                "chunk_type": "header",
                "chunk_index": 0,
                "total_chunks": total_chunks,
            },
        )
        chunks.append(header_chunk)

        # Content chunks start at index 1
        for i, chunk_data in enumerate(file_chunks):
            content_chunk = GitLabFileChunk(
                document=self,
                raw_data={
                    **chunk_data,
                    "source": self.get_source(),
                    "type": "gitlab_file_content",
                    "chunk_type": "content",
                    "project_id": project_id,
                    "project_path": project_path,
                    "chunk_index": i + 1,  # Offset by 1 for header
                    "total_chunks": total_chunks,
                },
            )
            chunks.append(content_chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.GITLAB_CODE

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        project_path = self.raw_data.get("project_path", "")
        file_path = self.raw_data.get("file_path", "")
        return get_gitlab_file_reference_id(project_path=project_path, file_path=file_path)

    def get_metadata(self) -> "GitLabFileDocumentMetadata":
        """Get document metadata."""
        file_path = self.raw_data.get("file_path", "")
        return {
            "file_path": file_path,
            "file_extension": Path(file_path).suffix.lower(),
            "project_id": self.raw_data.get("project_id", 0),
            "project_path": self.raw_data.get("project_path", "unknown"),
            "contributors": self.raw_data.get("contributors", []),
            "contributor_count": self.raw_data.get("contributor_count", 0),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_branch": self.raw_data.get("source_branch"),
            "source_commit_sha": self.raw_data.get("source_commit_sha"),
            "source": self.get_source(),
            "type": "gitlab_file_document",
            "chunk_count": len(self.raw_data.get("chunks", [])),
        }
