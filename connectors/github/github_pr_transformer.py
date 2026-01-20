import logging
from datetime import datetime
from typing import Any

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_github_pr_doc_id
from connectors.base.document_source import DocumentSource
from connectors.github.github_artifacts import (
    GitHubPRCommentEvent,
    GitHubPRDocumentData,
    GitHubPREventBase,
    GitHubPRReviewEvent,
    GitHubPullRequestArtifact,
)
from connectors.github.github_pull_request_document import GitHubPRDocument
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class GithubPRTransformer(BaseTransformer[GitHubPRDocument]):
    def __init__(self):
        super().__init__(DocumentSource.GITHUB_PRS)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[GitHubPRDocument]:
        repo = ArtifactRepository(readonly_db_pool)
        pr_artifacts = await repo.get_artifacts_by_entity_ids(GitHubPullRequestArtifact, entity_ids)

        logger.info(f"Loaded {len(pr_artifacts)} PR artifacts for {len(entity_ids)} entity IDs")

        documents = []
        counter: ErrorCounter = {}
        skipped_count = 0

        for artifact in pr_artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform artifact {artifact.id}", counter
            ):
                document = await self._create_document(artifact)

                if document:
                    documents.append(document)

                    if len(documents) % 50 == 0:
                        logger.info(f"Processed {len(documents)}/{len(pr_artifacts)} PRs")
                else:
                    skipped_count += 1
                    logger.warning(f"Skipped artifact {artifact.entity_id} - no document created")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"GitHub PR transformation complete: {successful} successful, {failed} failed, {skipped_count} skipped. "
            f"Created {len(documents)} documents from {len(pr_artifacts)} artifacts"
        )
        return documents

    async def _create_document(
        self, artifact: GitHubPullRequestArtifact
    ) -> GitHubPRDocument | None:
        try:
            pr_data = artifact.content.pr_data
            comments = artifact.content.comments
            reviews = artifact.content.reviews
            files = artifact.content.files

            # Extract metadata
            pr_number = artifact.metadata.pr_number
            pr_title = artifact.metadata.pr_title
            repository = artifact.metadata.repository
            organization = artifact.metadata.organization
            repo_id = artifact.metadata.repo_id

            # Build events list
            events: list[dict[str, Any]] = []

            # Add PR creation event
            if pr_data.created_at:
                event = self._create_pr_event(
                    "pull_request",
                    "opened",
                    pr_data,
                    pr_data.created_at,
                    pr_number,
                    pr_title,
                    repository,
                    organization,
                )
                events.append(event.model_dump())

            # Add comment events
            for comment in comments:
                if comment.created_at:
                    # Map comment type to event type for display
                    if comment.comment_type == "review":
                        event_type = "pull_request_review_comment"
                    else:
                        event_type = "issue_comment"

                    event = GitHubPRCommentEvent(
                        event_type=event_type,
                        action="created",
                        comment_type=comment.comment_type,
                        actor=comment.user.login if comment.user else "Unknown",
                        actor_id=str(comment.user.id) if comment.user else "",
                        actor_login=comment.user.login if comment.user else "",
                        timestamp=comment.created_at,
                        formatted_time=self._format_timestamp(comment.created_at),
                        pr_number=pr_number,
                        pr_title=pr_title,
                        repository=repository,
                        organization=organization,
                        comment_body=comment.body,
                    )
                    events.append(event.model_dump())

            # Add review events
            for review in reviews:
                if review.submitted_at:
                    event = GitHubPRReviewEvent(
                        event_type="pull_request_review",
                        action="submitted",
                        actor=review.user.login if review.user else "Unknown",
                        actor_id=str(review.user.id) if review.user else "",
                        actor_login=review.user.login if review.user else "",
                        timestamp=review.submitted_at,
                        formatted_time=self._format_timestamp(review.submitted_at),
                        pr_number=pr_number,
                        pr_title=pr_title,
                        repository=repository,
                        organization=organization,
                        review_state=review.state,
                        review_body=review.body or "",
                    )
                    events.append(event.model_dump())

            # Add PR close/merge events if applicable
            if pr_data.state == "closed" and pr_data.closed_at:
                if pr_data.merged:
                    event = GitHubPREventBase(
                        event_type="pull_request",
                        action="merged",
                        actor=pr_data.user.login if pr_data.user else "Unknown",
                        actor_id=str(pr_data.user.id) if pr_data.user else "",
                        actor_login=pr_data.user.login if pr_data.user else "",
                        timestamp=pr_data.merged_at or pr_data.closed_at,
                        formatted_time=self._format_timestamp(
                            pr_data.merged_at or pr_data.closed_at
                        ),
                        pr_number=pr_number,
                        pr_title=pr_title,
                        repository=repository,
                        organization=organization,
                        event_id=f"pr_merge_{pr_number}_{pr_data.merged_at or pr_data.closed_at}",
                    )
                    events.append(event.model_dump())
                else:
                    event = GitHubPREventBase(
                        event_type="pull_request",
                        action="closed",
                        actor=pr_data.user.login if pr_data.user else "Unknown",
                        actor_id=str(pr_data.user.id) if pr_data.user else "",
                        actor_login=pr_data.user.login if pr_data.user else "",
                        timestamp=pr_data.closed_at,
                        formatted_time=self._format_timestamp(pr_data.closed_at),
                        pr_number=pr_number,
                        pr_title=pr_title,
                        repository=repository,
                        organization=organization,
                        event_id=f"pr_close_{pr_number}_{pr_data.closed_at}",
                    )
                    events.append(event.model_dump())

            # Sort events by timestamp
            events.sort(key=lambda x: x.get("timestamp", ""))

            # Convert files to dict format for document
            files_dicts = [file.model_dump() for file in files]

            # Create typed document data
            document_data = GitHubPRDocumentData(
                pr_number=pr_number,
                pr_title=pr_title,
                pr_url=pr_data.html_url or "",
                pr_body=pr_data.body or "",
                pr_status=pr_data.state,
                pr_draft=pr_data.draft,
                pr_merged=pr_data.merged or False,
                pr_commits=pr_data.commits or 0,
                pr_additions=pr_data.additions or 0,
                pr_deletions=pr_data.deletions or 0,
                pr_changed_files=pr_data.changed_files or 0,
                repository=repository,
                organization=organization,
                repo_spec=f"{organization}/{repository}",
                actual_repo_id=repo_id,
                events=events,
                files=files_dicts,
                source="github",
                source_created_at=pr_data.created_at,
                source_merged_at=pr_data.merged_at,
                ingestion_timestamp=datetime.now().isoformat(),
            )

            document_id = get_github_pr_doc_id(str(repo_id), pr_number)
            return GitHubPRDocument(
                id=document_id,
                raw_data=document_data.model_dump(),
                source_updated_at=artifact.source_updated_at,
                permission_policy="tenant",
                permission_allowed_tokens=None,
            )

        except Exception as e:
            import traceback

            logger.error(
                f"Failed to create document for PR {artifact.metadata.pr_number}: {e}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            return None

    def _create_pr_event(
        self,
        event_type: str,
        action: str,
        pr_data,  # GitHubPullRequestData
        timestamp: str,
        pr_number: int,
        pr_title: str,
        repository: str,
        organization: str,
    ) -> GitHubPREventBase:
        """Create a PR event from PR data."""
        return GitHubPREventBase(
            event_type=event_type,
            action=action,
            actor=pr_data.user.login if pr_data.user else "Unknown",
            actor_id=str(pr_data.user.id) if pr_data.user else "",
            actor_login=pr_data.user.login if pr_data.user else "",
            timestamp=timestamp,
            formatted_time=self._format_timestamp(timestamp),
            pr_number=pr_number,
            pr_title=pr_title,
            repository=repository,
            organization=organization,
            event_id=f"pr_{action}_{pr_number}_{timestamp}",
        )

    def _format_timestamp(self, timestamp: str) -> str:
        """Format ISO timestamp to readable format."""
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            return timestamp
