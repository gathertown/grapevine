import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.linear.linear_artifacts import LinearIssueArtifact
from connectors.linear.linear_helpers import (
    create_comment_activity,
    create_issue_created_activity,
    create_linear_document,
    create_linear_document_data,
    get_user_display_name,
    is_system_activity,
)
from connectors.linear.linear_issue_document import LinearIssueDocument
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class LinearTransformer(BaseTransformer[LinearIssueDocument]):
    def __init__(self):
        super().__init__(DocumentSource.LINEAR)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[LinearIssueDocument]:
        repo = ArtifactRepository(readonly_db_pool)
        issue_artifacts = await repo.get_artifacts_by_entity_ids(LinearIssueArtifact, entity_ids)

        logger.info(
            f"Loaded {len(issue_artifacts)} issue artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}
        skipped_count = 0

        for artifact in issue_artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform artifact {artifact.id}", counter
            ):
                document = await self._create_document(artifact)

                if document:
                    documents.append(document)

                    if len(documents) % 100 == 0:
                        logger.info(f"Processed {len(documents)}/{len(issue_artifacts)} issues")
                else:
                    skipped_count += 1
                    logger.warning(f"Skipped artifact {artifact.entity_id} - no document created")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Linear transformation complete: {successful} successful, {failed} failed, {skipped_count} skipped. "
            f"Created {len(documents)} documents from {len(issue_artifacts)} artifacts"
        )
        return documents

    async def _create_document(self, artifact: LinearIssueArtifact) -> LinearIssueDocument | None:
        try:
            issue_data = artifact.content.issue_data
            issue_id = artifact.metadata.issue_id
            issue_identifier = artifact.metadata.issue_identifier
            team_id = artifact.metadata.team_id
            team_name = artifact.metadata.team_name

            # Check if issue_data is None
            if issue_data is None:
                logger.error(f"Issue {issue_identifier} has None issue_data")  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                return None

            # Build activities list
            activities = []

            # Add issue creation activity
            created_at = issue_data.get("createdAt")
            creator = issue_data.get("creator") or {}
            if created_at and creator:
                activities.append(
                    create_issue_created_activity(
                        creator,
                        created_at,
                        issue_id,
                        artifact.metadata.issue_title,
                        team_id,
                        team_name,
                    )
                )
            else:
                logger.debug(
                    f"Issue {issue_identifier} missing creator or createdAt - created_at: {created_at}, has_creator: {bool(creator)}"
                )

            # Add comments
            for comment in artifact.content.comments:
                if not comment or not isinstance(comment, dict):
                    continue

                timestamp = comment.get("createdAt")
                if not timestamp:
                    continue

                # Filter out system comments
                user = comment.get("user") or {}
                user_name = get_user_display_name(user)
                user_id = user.get("id", "") if user else ""

                if is_system_activity(user_name, user_id):
                    logger.debug(f"Filtering out system comment from {user_name}")
                    continue

                activity = create_comment_activity(
                    comment, issue_id, artifact.metadata.issue_title, team_id, team_name
                )
                activities.append(activity)

            # Sort activities by timestamp
            activities.sort(key=lambda a: a.get("timestamp", ""))

            # Log if no activities
            if not activities:
                logger.warning(
                    f"Issue {issue_identifier} has no activities (no creation event or comments)"
                )

            # Create document data using shared utility
            document_data = create_linear_document_data(issue_id, issue_data, activities)

            # Create document using shared utility
            return create_linear_document(issue_id, document_data, artifact.source_updated_at)

        except Exception as e:
            import traceback

            logger.error(
                f"Failed to create document for issue {artifact.metadata.issue_identifier}: {e}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            return None
