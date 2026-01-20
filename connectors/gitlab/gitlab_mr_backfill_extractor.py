"""GitLab MR backfill extractor.

This extractor processes specific batches of MRs, fetching their full data
including notes, approvals, and diffs.
"""

import logging
from datetime import UTC, datetime
from typing import Any
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
from connectors.gitlab.gitlab_models import GitLabMRBackfillConfig, GitLabMRBatch
from connectors.gitlab.gitlab_utils import (
    normalize_approvals,
    normalize_diffs,
    normalize_mr_data,
    normalize_notes,
)
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE

logger = logging.getLogger(__name__)


class GitLabMRBackfillExtractor(BaseExtractor[GitLabMRBackfillConfig]):
    """
    Extracts GitLab MRs from specific batches of MR IIDs.
    This is a child job of GitLabMRBackfillProjectExtractor.
    """

    source_name = "gitlab_mr_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: GitLabMRBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Processing {len(config.mr_batches)} MR batches for job {job_id}")

        # Get GitLab client for this tenant
        gitlab_client = await get_gitlab_client_for_tenant(config.tenant_id, self.ssm_client)

        try:
            # Process all MR batches
            all_mr_entity_ids: list[str] = []

            for batch_idx, mr_batch in enumerate(config.mr_batches):
                logger.info(
                    f"Processing batch {batch_idx + 1}/{len(config.mr_batches)}: "
                    f"{len(mr_batch.mr_iids)} MRs from {mr_batch.project_path}"
                )

                batch_entity_ids = await self._process_mr_batch(
                    job_id, gitlab_client, mr_batch, db_pool
                )
                all_mr_entity_ids.extend(batch_entity_ids)

            logger.info(
                f"Successfully processed {len(all_mr_entity_ids)} MR artifacts for job {job_id}"
            )

            # Trigger indexing in batches
            for i in range(0, len(all_mr_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batched_entity_ids = all_mr_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batched_entity_ids,
                    DocumentSource.GITLAB_MR,
                    config.tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

            logger.info(
                f"Successfully triggered index job for {len(all_mr_entity_ids)} MRs from job {job_id}"
            )

        finally:
            await gitlab_client.aclose()

    async def _process_mr_batch(
        self,
        job_id: str,
        gitlab_client,
        mr_batch: GitLabMRBatch,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Process a specific batch of MRs from a project."""
        try:
            project_id = mr_batch.project_id
            project_path = mr_batch.project_path
            mr_iids = mr_batch.mr_iids

            # Fetch full MR data with notes, approvals, and diffs
            mr_data_list: list[dict[str, Any]] = []

            for mr_iid in mr_iids:
                try:
                    mr_data = await self._fetch_full_mr_data(gitlab_client, project_id, mr_iid)
                    if mr_data:
                        mr_data_list.append(mr_data)
                except Exception as e:
                    logger.error(f"Failed to fetch MR !{mr_iid} from {project_path}: {e}")
                    # Continue with other MRs rather than failing the whole batch
                    continue

            logger.info(f"Fetched {len(mr_data_list)} MRs with notes and diffs from {project_path}")

            # Log note and approval distribution
            mrs_with_notes = sum(1 for mr in mr_data_list if mr.get("notes"))
            total_notes = sum(len(mr.get("notes", [])) for mr in mr_data_list)
            mrs_with_approvals = sum(1 for mr in mr_data_list if mr.get("approvals"))
            logger.info(
                f"Distribution: {mrs_with_notes}/{len(mr_data_list)} MRs have notes "
                f"(total: {total_notes}), {mrs_with_approvals}/{len(mr_data_list)} MRs have approvals"
            )

            # Create and store artifacts
            entity_ids = []
            artifacts_batch = []

            for mr_data in mr_data_list:
                artifact = self._create_mr_artifact(
                    job_id,
                    mr_data,
                    project_id,
                    project_path,
                )

                if artifact:
                    artifacts_batch.append(artifact)
                    entity_ids.append(artifact.entity_id)

                    # Store artifacts in batches
                    if len(artifacts_batch) >= 50:
                        await self.store_artifacts_batch(db_pool, artifacts_batch)
                        logger.info(f"Stored {len(artifacts_batch)} MR artifacts")
                        artifacts_batch = []

            if artifacts_batch:
                await self.store_artifacts_batch(db_pool, artifacts_batch)
                logger.info(f"Stored {len(artifacts_batch)} MR artifacts")

            logger.info(
                f"Completed processing batch from {project_path} with {len(entity_ids)} MRs"
            )
            return entity_ids

        except Exception as e:
            logger.error(f"Failed to process MR batch from {mr_batch.project_path}: {e}")
            raise

    async def _fetch_full_mr_data(
        self,
        gitlab_client,
        project_id: int,
        mr_iid: int,
    ) -> dict[str, Any] | None:
        """Fetch full MR data including notes, approvals, and diffs."""
        try:
            # Get basic MR data
            mr_data = await gitlab_client.get_merge_request(project_id, mr_iid)
            if not mr_data:
                return None

            # Get notes (comments)
            notes = await gitlab_client.get_merge_request_notes(project_id, mr_iid)
            mr_data["notes"] = notes

            # Get approvals
            try:
                approvals = await gitlab_client.get_merge_request_approvals(project_id, mr_iid)
                mr_data["approvals"] = approvals
            except Exception as e:
                # Approvals endpoint may not be available on all GitLab editions
                logger.debug(f"Could not fetch approvals for MR !{mr_iid}: {e}")
                mr_data["approvals"] = {}

            # Get diffs (file changes)
            try:
                diffs = await gitlab_client.get_merge_request_diffs(project_id, mr_iid)
                mr_data["diffs"] = diffs
            except Exception as e:
                logger.warning(f"Could not fetch diffs for MR !{mr_iid}: {e}")
                mr_data["diffs"] = []

            return mr_data

        except Exception as e:
            logger.error(f"Failed to fetch MR !{mr_iid}: {e}")
            return None

    def _create_mr_artifact(
        self,
        job_id: str,
        mr_data: dict[str, Any],
        project_id: int,
        project_path: str,
    ) -> GitLabMRArtifact | None:
        """Create a GitLabMRArtifact from MR data."""
        try:
            mr_id = mr_data.get("id")
            mr_iid = mr_data.get("iid")
            if not mr_id or not mr_iid:
                return None

            entity_id = get_gitlab_mr_entity_id(project_id=project_id, mr_iid=mr_iid)

            # Extract and normalize notes
            raw_notes = mr_data.pop("notes", [])
            normalized_notes = normalize_notes(raw_notes)

            # Extract and normalize approvals
            raw_approvals = mr_data.pop("approvals", {})
            normalized_approvals = normalize_approvals(raw_approvals)

            # Extract and normalize diffs
            raw_diffs = mr_data.pop("diffs", [])
            normalized_diffs = normalize_diffs(raw_diffs)

            # Normalize the MR data
            normalized_mr = normalize_mr_data(mr_data)

            # Determine if merged
            merged = normalized_mr.merged or normalized_mr.state == "merged"

            artifact = GitLabMRArtifact(
                entity_id=entity_id,
                ingest_job_id=UUID(job_id),
                content=GitLabMRArtifactContent(
                    mr_data=normalized_mr,
                    notes=normalized_notes,
                    approvals=normalized_approvals,
                    diffs=normalized_diffs,
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
                source_updated_at=datetime.now(tz=UTC),
            )

            return artifact

        except Exception as e:
            logger.error(f"Error creating MR artifact for MR !{mr_data.get('iid', 'unknown')}: {e}")
            return None
