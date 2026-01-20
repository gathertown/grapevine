"""GitLab MR incremental backfill project extractor.

This extractor fetches only MRs that have been updated since the last sync.
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.base_ingest_artifact import get_gitlab_mr_entity_id
from connectors.base.document_source import DocumentSource
from connectors.gitlab.gitlab_artifacts import (
    GitLabMRArtifact,
    GitLabMRArtifactContent,
    GitLabMRArtifactMetadata,
)
from connectors.gitlab.gitlab_client_factory import get_gitlab_client_for_tenant
from connectors.gitlab.gitlab_models import GitLabMRIncrBackfillProjectConfig
from connectors.gitlab.gitlab_sync_service import GitLabSyncService
from connectors.gitlab.gitlab_utils import (
    normalize_approvals,
    normalize_diffs,
    normalize_mr_data,
    normalize_notes,
)
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE

logger = logging.getLogger(__name__)


class GitLabMRIncrBackfillProjectExtractor(BaseExtractor[GitLabMRIncrBackfillProjectConfig]):
    """
    Extracts only MRs that have changed since the last sync for a project.
    """

    source_name = "gitlab_mr_incr_backfill_project"

    def __init__(self, ssm_client: SSMClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: GitLabMRIncrBackfillProjectConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Processing GitLab MR incremental backfill for project {config.project_path}")

        sync_service = GitLabSyncService(db_pool)
        gitlab_client = await get_gitlab_client_for_tenant(
            config.tenant_id, self.ssm_client, per_page=100
        )

        try:
            # Get last sync timestamp for this project
            synced_until = await sync_service.get_mr_synced_until(config.project_id)

            # If no previous sync, skip incremental - user should run full backfill first
            # This prevents the hourly cron from setting a cursor before full backfill runs,
            # which would cause all historical MRs to be permanently skipped
            if synced_until is None:
                logger.info(
                    f"No previous MR sync for project {config.project_path}, "
                    "skipping incremental (use full backfill first)"
                )
                return

            logger.info(f"Last MR sync for project {config.project_id} was at: {synced_until}")

            # Query MRs updated after the last sync
            updated_after_str = synced_until.isoformat()
            updated_mrs = await gitlab_client.get_project_merge_requests(
                config.project_id,
                state="all",
                scope="all",
                order_by="updated_at",
                sort="asc",  # Ascending so we process oldest first
                updated_after=updated_after_str,
            )

            if not updated_mrs:
                logger.info(f"No MRs updated since {synced_until} in {config.project_path}")
                return

            logger.info(
                f"Found {len(updated_mrs)} MRs updated since {synced_until} "
                f"in {config.project_path}"
            )

            # Process MRs and create artifacts
            artifacts: list[GitLabMRArtifact] = []
            entity_ids: list[str] = []
            latest_updated_at: datetime | None = None

            for mr in updated_mrs:
                try:
                    artifact = await self._create_mr_artifact(
                        job_id, gitlab_client, config.project_id, config.project_path, mr
                    )
                    if artifact:
                        artifacts.append(artifact)
                        entity_ids.append(artifact.entity_id)

                        # Track the latest updated_at for cursor
                        mr_updated_at = mr.get("updated_at")
                        if mr_updated_at:
                            updated_dt = datetime.fromisoformat(
                                mr_updated_at.replace("Z", "+00:00")
                            )
                            if latest_updated_at is None or updated_dt > latest_updated_at:
                                latest_updated_at = updated_dt

                except Exception as e:
                    logger.error(f"Failed to process MR !{mr.get('iid')}: {e}")
                    continue

            # Store artifacts in batches
            if artifacts:
                for i in range(0, len(artifacts), 50):
                    batch = artifacts[i : i + 50]
                    await self.store_artifacts_batch(db_pool, batch)
                    logger.info(f"Stored {len(batch)} MR artifacts")

            # Trigger indexing
            for i in range(0, len(entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch_ids = entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch_ids,
                    DocumentSource.GITLAB_MR,
                    config.tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

            # Update sync cursor for this project (with small overlap to avoid missing edge cases)
            if latest_updated_at:
                # Subtract 1 second to ensure we don't miss items at the boundary
                new_cursor = latest_updated_at - timedelta(seconds=1)
                await sync_service.set_mr_synced_until(config.project_id, new_cursor)
                logger.info(
                    f"Updated MR sync cursor for project {config.project_id} to: {new_cursor}"
                )

            logger.info(
                f"Completed incremental MR sync for {config.project_path}: "
                f"{len(entity_ids)} MRs processed"
            )

        finally:
            await gitlab_client.aclose()

    async def _create_mr_artifact(
        self,
        job_id: str,
        gitlab_client,
        project_id: int,
        project_path: str,
        mr: dict,
    ) -> GitLabMRArtifact | None:
        """Create a GitLabMRArtifact from MR data."""
        try:
            mr_iid = mr["iid"]

            # Fetch additional MR details
            notes = await gitlab_client.get_merge_request_notes(project_id, mr_iid)
            diffs = await gitlab_client.get_merge_request_diffs(project_id, mr_iid)
            approvals = await gitlab_client.get_merge_request_approvals(project_id, mr_iid)

            entity_id = get_gitlab_mr_entity_id(project_id=project_id, mr_iid=mr_iid)

            # Normalize the MR data
            normalized_mr = normalize_mr_data(mr)
            normalized_notes = normalize_notes(notes)
            normalized_diffs = normalize_diffs(diffs)
            normalized_approvals = normalize_approvals(approvals)

            # Determine if merged
            merged = normalized_mr.merged or normalized_mr.state == "merged"

            artifact = GitLabMRArtifact(
                entity_id=entity_id,
                ingest_job_id=UUID(job_id),
                content=GitLabMRArtifactContent(
                    mr_data=normalized_mr,
                    notes=normalized_notes,
                    diffs=normalized_diffs,
                    approvals=normalized_approvals,
                ),
                metadata=GitLabMRArtifactMetadata(
                    mr_iid=mr_iid,
                    mr_title=normalized_mr.title,
                    project_path=project_path,
                    project_id=project_id,
                    state=normalized_mr.state,
                    merged=merged,
                    author=normalized_mr.author.username if normalized_mr.author else None,
                    assignees=[a.username for a in normalized_mr.assignees],
                    reviewers=[r.username for r in normalized_mr.reviewers],
                    labels=normalized_mr.labels,
                ),
                source_updated_at=datetime.now(UTC),
            )

            return artifact

        except Exception as e:
            logger.error(f"Error creating MR artifact for !{mr.get('iid')}: {e}")
            return None
