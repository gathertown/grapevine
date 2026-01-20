"""
Figma connector models - artifacts and backfill configurations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import (
    ArtifactEntity,
    BaseIngestArtifact,
)
from connectors.base.models import BackfillIngestConfig

# =============================================================================
# Artifact Metadata Types (Pydantic for validation)
# =============================================================================


class FigmaFileArtifactMetadata(BaseModel):
    """Metadata for Figma file artifacts."""

    file_key: str
    project_id: str | None = None
    team_id: str | None = None
    editor_type: str | None = None
    page_count: int | None = None
    component_count: int | None = None


class FigmaCommentArtifactMetadata(BaseModel):
    """Metadata for Figma comment artifacts."""

    comment_id: str
    file_key: str
    is_reply: bool = False
    is_resolved: bool = False
    editor_type: str | None = None


# =============================================================================
# Artifact Classes
# =============================================================================


def get_figma_entity_id(entity_type: str, entity_id: str) -> str:
    """Generate a consistent entity ID for Figma artifacts."""
    return f"figma_{entity_type}_{entity_id}"


class FigmaFileArtifact(BaseIngestArtifact):
    """Artifact representing a Figma design file."""

    entity: ArtifactEntity = ArtifactEntity.FIGMA_FILE
    content: dict[str, Any]
    metadata: FigmaFileArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        file_key: str,
        file_data: dict[str, Any],
        ingest_job_id: UUID,
        project_id: str | None = None,
        team_id: str | None = None,
    ) -> FigmaFileArtifact:
        """
        Create a FigmaFileArtifact from API response data.

        Args:
            file_key: The file key from Figma
            file_data: Response from GET /v1/files/:key
            ingest_job_id: The job ID for this ingest operation
            project_id: Optional project ID
            team_id: Optional team ID
        """
        # Extract page names from document structure
        page_names: list[str] = []
        document = file_data.get("document", {})
        for child in document.get("children", []):
            if child.get("type") == "CANVAS":
                page_names.append(child.get("name", "Untitled Page"))

        # Extract component names and descriptions
        components = file_data.get("components", {})
        component_names = [comp.get("name", "") for comp in components.values()]
        component_descriptions = _extract_component_descriptions(components)

        # Build document summary (includes structure and text content)
        document_summary = _build_document_summary(document)

        # Extract all text content from TEXT nodes
        text_content = _extract_text_content(document)

        # Parse last_modified timestamp
        last_modified_str = file_data.get("lastModified", "")
        try:
            source_updated_at = datetime.fromisoformat(last_modified_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            source_updated_at = datetime.now(UTC)

        content: dict[str, Any] = {
            "file_key": file_key,
            "file_name": file_data.get("name", "Untitled"),
            "thumbnail_url": file_data.get("thumbnailUrl"),
            "last_modified": last_modified_str,
            "version": file_data.get("version", ""),
            "editor_type": file_data.get("editorType", "figma"),
            "role": file_data.get("role", "viewer"),
            "page_names": page_names,
            "component_names": component_names,
            "component_descriptions": component_descriptions,
            "component_count": len(components),
            "page_count": len(page_names),
            "document_summary": document_summary,
            "text_content": text_content,
        }

        metadata = FigmaFileArtifactMetadata(
            file_key=file_key,
            project_id=project_id,
            team_id=team_id,
            editor_type=file_data.get("editorType", "figma"),
            page_count=len(page_names),
            component_count=len(components),
        )

        return cls(
            entity_id=get_figma_entity_id("file", file_key),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


class FigmaCommentArtifact(BaseIngestArtifact):
    """Artifact representing a Figma comment or reply."""

    entity: ArtifactEntity = ArtifactEntity.FIGMA_COMMENT
    content: dict[str, Any]
    metadata: FigmaCommentArtifactMetadata

    @classmethod
    def from_api_response(
        cls,
        comment_data: dict[str, Any],
        file_name: str,
        ingest_job_id: UUID,
        reply_count: int = 0,
        editor_type: str | None = None,
    ) -> FigmaCommentArtifact:
        """
        Create a FigmaCommentArtifact from API response data.

        Args:
            comment_data: Comment object from GET /v1/files/:key/comments
            file_name: Name of the file the comment belongs to
            ingest_job_id: The job ID for this ingest operation
            reply_count: Number of replies to this comment
            editor_type: The editor type of the file (figma or figjam)
        """
        user = comment_data.get("user", {})
        created_at_str = comment_data.get("created_at", "")

        try:
            source_updated_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            source_updated_at = datetime.now(UTC)

        comment_id = comment_data.get("id", "")
        file_key = comment_data.get("file_key", "")

        content: dict[str, Any] = {
            "comment_id": comment_id,
            "file_key": file_key,
            "file_name": file_name,
            "parent_id": comment_data.get("parent_id"),
            "user_id": user.get("id", ""),
            "user_handle": user.get("handle", ""),
            "user_email": user.get("email"),
            "created_at": created_at_str,
            "resolved_at": comment_data.get("resolved_at"),
            "message": comment_data.get("message", ""),
            "reply_count": reply_count,
            "editor_type": editor_type,
        }

        metadata = FigmaCommentArtifactMetadata(
            comment_id=comment_id,
            file_key=file_key,
            is_reply=comment_data.get("parent_id") is not None,
            is_resolved=comment_data.get("resolved_at") is not None,
            editor_type=editor_type,
        )

        return cls(
            entity_id=get_figma_entity_id("comment", comment_id),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
            ingest_job_id=ingest_job_id,
        )


def _extract_text_content(document: dict[str, Any]) -> list[str]:
    """
    Extract all text content from TEXT nodes in the document.

    This traverses the entire document tree and extracts the actual text
    content (characters) from TEXT nodes, which contain user-written text.
    """
    texts: list[str] = []

    def traverse(node: dict[str, Any]) -> None:
        node_type = node.get("type", "")

        # TEXT nodes contain actual text content in the "characters" field
        if node_type == "TEXT":
            characters = node.get("characters", "")
            if characters and characters.strip():
                texts.append(characters.strip())

        # Recursively process children
        for child in node.get("children", []):
            traverse(child)

    traverse(document)
    return texts


def _build_document_summary(document: dict[str, Any], max_depth: int = 10) -> str:
    """
    Build a text summary of the document structure for indexing.

    This creates a hierarchical text representation of the design file
    that can be searched. Includes frame names, component names, and
    actual text content from TEXT nodes.
    """
    lines: list[str] = []

    def traverse(node: dict[str, Any], depth: int = 0) -> None:
        if depth >= max_depth:
            return

        node_type = node.get("type", "")
        node_name = node.get("name", "")

        # Include structural elements (pages, frames, components)
        if node_name and node_type in {
            "CANVAS",
            "FRAME",
            "COMPONENT",
            "COMPONENT_SET",
            "GROUP",
            "SECTION",
        }:
            indent = "  " * depth
            lines.append(f"{indent}{node_type}: {node_name}")

        # For TEXT nodes, include both the name and actual text content
        if node_type == "TEXT":
            indent = "  " * depth
            characters = node.get("characters", "")
            if characters and characters.strip():
                # Include actual text content, not just the node name
                lines.append(f"{indent}TEXT: {characters.strip()}")
            elif node_name:
                lines.append(f"{indent}TEXT: {node_name}")

        for child in node.get("children", []):
            traverse(child, depth + 1)

    traverse(document)
    return "\n".join(lines[:500])  # Increased limit to 500 entries


def _extract_component_descriptions(components: dict[str, Any]) -> list[str]:
    """
    Extract descriptions from components.

    Components can have descriptions that explain their purpose,
    which is valuable for search.
    """
    descriptions: list[str] = []

    for _comp_id, comp_data in components.items():
        name = comp_data.get("name", "")
        description = comp_data.get("description", "")

        if description and description.strip():
            descriptions.append(f"{name}: {description.strip()}")

    return descriptions


# =============================================================================
# Backfill Configuration Models
# =============================================================================


class FigmaBackfillRootConfig(BackfillIngestConfig, frozen=True):
    """Configuration for starting a Figma full backfill."""

    source: str = "figma_backfill_root"
    # Optional: specific team IDs to sync. If not provided, syncs all selected teams.
    team_ids_to_sync: list[str] | None = None


class FigmaTeamBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for backfilling a specific team."""

    source: str = "figma_team_backfill"
    team_id: str


class FigmaFileBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for backfilling specific files."""

    source: str = "figma_file_backfill"
    file_keys: list[str]
    project_id: str | None = None
    team_id: str | None = None


class FigmaIncrementalBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for incremental Figma sync."""

    source: str = "figma_incremental_backfill"
    lookback_hours: int = 24
