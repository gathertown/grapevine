"""
GitHub file document classes for structured file and chunk representation.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypedDict

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource
from src.ingest.references.reference_ids import get_github_file_reference_id


class GitHubFileChunkMetadata(TypedDict):
    """Metadata for GitHub file chunks."""

    chunk_index: int
    total_chunks: int
    file_path: str  # Always present - set from artifact path during chunk creation
    file_extension: str  # Always present - computed from file_path
    chunk_size: int | None  # May be None for header chunks which don't have measured content
    source_created_at: str | None  # May be None if file timestamp unavailable (edge cases in Git)


class GitHubFileDocumentMetadata(TypedDict):
    """Metadata for GitHub file documents."""

    file_path: str
    file_extension: str
    repository: str
    organization: str
    contributors: list[dict[str, Any]]
    contributor_count: int
    source_created_at: str | None  # May be None if Git file timestamp unavailable (rare edge cases)
    source_branch: str | None  # Optional branch name for stable links
    source_commit_sha: str | None  # Optional commit SHA for stable links
    change_type: str
    source_type: str
    source: str
    type: str
    chunk_count: int


@dataclass
class GitHubFileChunk(BaseChunk[GitHubFileChunkMetadata]):
    """Represents a single GitHub file content chunk."""

    def get_content(self) -> str:
        """Get the formatted chunk content."""
        return self.raw_data.get("content", "")

    def get_metadata(self) -> GitHubFileChunkMetadata:
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
class GitHubFileDocument(BaseDocument[GitHubFileChunk, GitHubFileDocumentMetadata]):
    """Represents a GitHub file document with metadata and content."""

    raw_data: dict[str, Any]

    def _get_repo_name(self) -> str:
        return self.raw_data.get("repository", "unknown")

    def get_header_content(self) -> str:
        """Get the formatted header section of the document."""
        file_path = self.raw_data.get("file_path", "")
        file_extension = Path(file_path).suffix.lower()
        contributors = self.raw_data.get("contributors", [])
        source_created_at = self.raw_data.get("source_created_at", "")
        repository = self._get_repo_name()
        organization = self.raw_data.get("organization", "unknown")
        change_type = self.raw_data.get("change_type", "")
        source_type = self.raw_data.get("source_type", "")

        lines = [
            f"# File: {file_path}",
            f"Extension: {file_extension}",
            f"Repository: {repository}",
            f"Organization: {organization}",
        ]

        if source_created_at:
            lines.append(f"Last Modified: {source_created_at}")

        if change_type:
            lines.append(f"Change Type: {change_type}")

        if source_type:
            lines.append(f"Source: {source_type}")

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

    def to_embedding_chunks(self) -> list[GitHubFileChunk]:
        """Convert to embedding chunk format."""
        chunks = []
        file_chunks = self.raw_data.get("chunks", [])
        repo = self._get_repo_name()

        # Create header chunk
        header_chunk = GitHubFileChunk(
            document=self,
            github_repository=repo,
            raw_data={
                "content": self.get_header_content(),
                "file_path": self.raw_data.get("file_path"),
                "file_extension": Path(self.raw_data.get("file_path", "")).suffix.lower(),
                "repository": repo,
                "organization": self.raw_data.get("organization", "unknown"),
                "contributors": self.raw_data.get("contributors", []),
                "contributor_count": self.raw_data.get("contributor_count", 0),
                "source_created_at": self.raw_data.get(
                    "source_created_at"
                ),  # TODO AIVP-496 cleanup redundant metadata field
                "change_type": self.raw_data.get("change_type", ""),
                "source_type": self.raw_data.get("source_type", ""),
                "source": self.get_source(),
                "type": "github_file_header",
                "chunk_type": "header",
                "total_chunks": len(file_chunks),
            },
        )
        chunks.append(header_chunk)

        for chunk_data in file_chunks:
            content_chunk = GitHubFileChunk(
                document=self,
                github_repository=repo,
                raw_data={
                    **chunk_data,
                    "source": self.get_source(),
                    "type": "github_file_content",
                    "chunk_type": "content",
                    "repository": repo,
                    "organization": self.raw_data.get("organization", "unknown"),
                    "change_type": self.raw_data.get("change_type", ""),
                    "source_type": self.raw_data.get("source_type", ""),
                },
            )
            chunks.append(content_chunk)

        return chunks

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.GITHUB_CODE

    def get_reference_id(self) -> str:
        """Get the reference ID for this document."""
        organization = self.raw_data.get("organization", "")
        repository = self.raw_data.get("repository", "")
        file_path = self.raw_data.get("file_path", "")
        return get_github_file_reference_id(
            owner=organization, repo=repository, file_path=file_path
        )

    def get_metadata(self) -> GitHubFileDocumentMetadata:
        """Get document metadata."""
        file_path = self.raw_data.get("file_path", "")
        return {
            "file_path": file_path,
            "file_extension": Path(file_path).suffix.lower(),
            "repository": self.raw_data.get("repository", "unknown"),
            "organization": self.raw_data.get("organization", "unknown"),
            "contributors": self.raw_data.get("contributors", []),
            "contributor_count": self.raw_data.get("contributor_count", 0),
            "source_created_at": self.raw_data.get("source_created_at"),
            "source_branch": self.raw_data.get("source_branch"),
            "source_commit_sha": self.raw_data.get("source_commit_sha"),
            "change_type": self.raw_data.get("change_type", ""),
            "source_type": self.raw_data.get("source_type", ""),
            "source": self.get_source(),
            "type": "github_file_document",
            "chunk_count": len(self.raw_data.get("chunks", [])),
        }
