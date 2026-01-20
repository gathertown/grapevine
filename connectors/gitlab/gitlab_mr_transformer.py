"""GitLab MR transformer.

Transforms GitLab MR artifacts into searchable documents.
"""

import logging
from datetime import datetime
from typing import Any

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_gitlab_mr_doc_id
from connectors.base.document_source import DocumentSource
from connectors.gitlab.gitlab_artifacts import (
    GitLabMRApprovalEvent,
    GitLabMRArtifact,
    GitLabMRDocumentData,
    GitLabMREventBase,
    GitLabMRNoteEvent,
)
from connectors.gitlab.gitlab_merge_request_document import GitLabMRDocument
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class GitLabMRTransformer(BaseTransformer[GitLabMRDocument]):
    def __init__(self):
        super().__init__(DocumentSource.GITLAB_MR)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[GitLabMRDocument]:
        repo = ArtifactRepository(readonly_db_pool)
        mr_artifacts = await repo.get_artifacts_by_entity_ids(GitLabMRArtifact, entity_ids)

        logger.info(f"Loaded {len(mr_artifacts)} MR artifacts for {len(entity_ids)} entity IDs")

        documents = []
        counter: ErrorCounter = {}

        for artifact in mr_artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform artifact {artifact.id}", counter
            ):
                document = await self._create_document(artifact)
                documents.append(document)

                if len(documents) % 50 == 0:
                    logger.info(f"Processed {len(documents)}/{len(mr_artifacts)} MRs")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"GitLab MR transformation complete: {successful} successful, {failed} failed. "
            f"Created {len(documents)} documents from {len(mr_artifacts)} artifacts"
        )
        return documents

    async def _create_document(self, artifact: GitLabMRArtifact) -> GitLabMRDocument:
        mr_data = artifact.content.mr_data
        notes = artifact.content.notes
        approvals = artifact.content.approvals
        diffs = artifact.content.diffs

        # Extract metadata
        mr_iid = artifact.metadata.mr_iid
        mr_title = artifact.metadata.mr_title
        project_path = artifact.metadata.project_path
        project_id = artifact.metadata.project_id

        # Build events list
        events: list[dict[str, Any]] = []

        # Add MR creation event
        if mr_data.created_at:
            event = self._create_mr_event(
                "merge_request",
                "opened",
                mr_data,
                mr_data.created_at,
                mr_iid,
                mr_title,
                project_path,
            )
            events.append(event.model_dump())

        # Add note events (both user comments and system notes)
        for note in notes:
            if note.created_at:
                author_name = (
                    note.author.name
                    if note.author and note.author.name
                    else note.author.username
                    if note.author
                    else "Unknown"
                )
                event = GitLabMRNoteEvent(
                    event_type="note",
                    action="created",
                    actor=author_name,
                    actor_username=note.author.username if note.author else "",
                    timestamp=note.created_at,
                    formatted_time=self._format_timestamp(note.created_at),
                    mr_iid=mr_iid,
                    mr_title=mr_title,
                    project_path=project_path,
                    note_body=note.body,
                    system=note.system,
                )
                events.append(event.model_dump())

        # Add approval events
        for approval in approvals:
            # Approvals don't have timestamps in GitLab API, use current time placeholder
            event = GitLabMRApprovalEvent(
                event_type="approval",
                action="approved",
                actor=approval.user.name or approval.user.username,
                actor_username=approval.user.username,
                timestamp=approval.approved_at or mr_data.updated_at or "",
                formatted_time=self._format_timestamp(
                    approval.approved_at or mr_data.updated_at or ""
                ),
                mr_iid=mr_iid,
                mr_title=mr_title,
                project_path=project_path,
            )
            events.append(event.model_dump())

        # Add MR close/merge events if applicable
        if mr_data.state == "merged" and mr_data.merged_at:
            merged_by = mr_data.merged_by
            # Get actor name with proper fallbacks
            if merged_by:
                merged_actor = merged_by.name or merged_by.username
            elif mr_data.author:
                merged_actor = mr_data.author.name or mr_data.author.username
            else:
                merged_actor = "Unknown"
            event = GitLabMREventBase(
                event_type="merge_request",
                action="merged",
                actor=merged_actor,
                actor_username=merged_by.username
                if merged_by
                else (mr_data.author.username if mr_data.author else ""),
                timestamp=mr_data.merged_at,
                formatted_time=self._format_timestamp(mr_data.merged_at),
                mr_iid=mr_iid,
                mr_title=mr_title,
                project_path=project_path,
                event_id=f"mr_merge_{mr_iid}_{mr_data.merged_at}",
            )
            events.append(event.model_dump())
        elif mr_data.state == "closed" and mr_data.closed_at:
            # Get actor name with proper fallbacks
            closed_actor = (
                (mr_data.author.name or mr_data.author.username) if mr_data.author else "Unknown"
            )
            event = GitLabMREventBase(
                event_type="merge_request",
                action="closed",
                actor=closed_actor,
                actor_username=mr_data.author.username if mr_data.author else "",
                timestamp=mr_data.closed_at,
                formatted_time=self._format_timestamp(mr_data.closed_at),
                mr_iid=mr_iid,
                mr_title=mr_title,
                project_path=project_path,
                event_id=f"mr_close_{mr_iid}_{mr_data.closed_at}",
            )
            events.append(event.model_dump())

        # Sort events by timestamp
        events.sort(key=lambda x: x.get("timestamp", ""))

        # Convert diffs to dict format for document
        diffs_dicts = [diff.model_dump() for diff in diffs]

        # Determine if merged
        merged = mr_data.merged or mr_data.state == "merged"

        # Create typed document data
        document_data = GitLabMRDocumentData(
            mr_iid=mr_iid,
            mr_title=mr_title,
            mr_url=mr_data.web_url or "",
            mr_description=mr_data.description or "",
            mr_state=mr_data.state,
            mr_draft=mr_data.draft,
            mr_merged=merged,
            mr_changes_count=mr_data.changes_count or 0,
            project_path=project_path,
            project_id=project_id,
            source_branch=mr_data.source_branch,
            target_branch=mr_data.target_branch,
            events=events,
            diffs=diffs_dicts,
            source="gitlab",
            source_created_at=mr_data.created_at,
            source_merged_at=mr_data.merged_at,
            ingestion_timestamp=datetime.now().isoformat(),
        )

        document_id = get_gitlab_mr_doc_id(project_id, mr_iid)
        return GitLabMRDocument(
            id=document_id,
            raw_data=document_data.model_dump(),
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )

    def _create_mr_event(
        self,
        event_type: str,
        action: str,
        mr_data,  # GitLabMergeRequestData
        timestamp: str,
        mr_iid: int,
        mr_title: str,
        project_path: str,
    ) -> GitLabMREventBase:
        """Create an MR event from MR data."""
        return GitLabMREventBase(
            event_type=event_type,
            action=action,
            actor=(mr_data.author.name or mr_data.author.username) if mr_data.author else "Unknown",
            actor_username=mr_data.author.username if mr_data.author else "",
            timestamp=timestamp,
            formatted_time=self._format_timestamp(timestamp),
            mr_iid=mr_iid,
            mr_title=mr_title,
            project_path=project_path,
            event_id=f"mr_{action}_{mr_iid}_{timestamp}",
        )

    def _format_timestamp(self, timestamp: str) -> str:
        """Format ISO timestamp to readable format."""
        if not timestamp:
            return ""
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return timestamp
