"""Figma file backfill extractor.

Processes a batch of file keys:
1. Fetches full file data for each file
2. Fetches comments for each file
3. Creates artifacts and triggers indexing
"""

import math
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.figma.client import FigmaClient, get_figma_client_for_tenant
from connectors.figma.figma_models import (
    FigmaCommentArtifact,
    FigmaFileArtifact,
    FigmaFileBackfillConfig,
)
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.logging import get_logger
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = get_logger(__name__)


class FigmaFileBackfillExtractor(BaseExtractor[FigmaFileBackfillConfig]):
    """Extractor for processing Figma file backfill batch jobs.

    Each job processes a batch of file keys provided by the root extractor.
    """

    source_name = "figma_file_backfill"

    async def process_job(
        self,
        job_id: str,
        config: FigmaFileBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process a batch of Figma files for a tenant."""
        tenant_id = config.tenant_id
        file_keys = config.file_keys

        logger.info(
            f"Processing batch of {len(file_keys)} Figma files",
            tenant_id=tenant_id,
            backfill_id=config.backfill_id,
        )

        try:
            async with await get_figma_client_for_tenant(tenant_id) as client:
                await self._process_batch(
                    client=client,
                    db_pool=db_pool,
                    job_id=job_id,
                    trigger_indexing=trigger_indexing,
                    config=config,
                )
        except ExtendVisibilityException:
            raise
        except Exception as e:
            logger.error(f"Failed to process Figma files batch: {e}", exc_info=True)
            raise
        finally:
            # Always track that we attempted this job
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(config.backfill_id, tenant_id, 1)

    async def _process_batch(
        self,
        client: FigmaClient,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        config: FigmaFileBackfillConfig,
    ) -> None:
        """Process a batch of file keys."""
        tenant_id = config.tenant_id
        file_keys = config.file_keys
        project_id = config.project_id
        team_id = config.team_id
        ingest_job_id = UUID(job_id)

        file_artifacts: list[FigmaFileArtifact] = []
        comment_artifacts: list[FigmaCommentArtifact] = []
        file_entity_ids: list[str] = []
        comment_entity_ids: list[str] = []

        for file_key in file_keys:
            try:
                # Fetch full file data
                file_data = await client.get_file(file_key)

                # Convert Pydantic model to dict for artifact creation
                file_dict = file_data.model_dump(by_alias=False)
                file_dict["lastModified"] = file_data.last_modified
                file_dict["editorType"] = file_data.editor_type
                file_dict["thumbnailUrl"] = file_data.thumbnail_url
                file_dict["componentSets"] = file_data.component_sets

                # Create file artifact
                file_artifact = FigmaFileArtifact.from_api_response(
                    file_key=file_key,
                    file_data=file_dict,
                    ingest_job_id=ingest_job_id,
                    project_id=project_id,
                    team_id=team_id,
                )
                file_artifacts.append(file_artifact)
                file_entity_ids.append(file_artifact.entity_id)

                # Fetch comments for this file
                try:
                    comments = await client.get_file_comments(file_key)

                    # Build parent->reply count map
                    reply_counts: dict[str, int] = {}
                    for comment in comments:
                        if comment.parent_id:
                            reply_counts[comment.parent_id] = (
                                reply_counts.get(comment.parent_id, 0) + 1
                            )

                    # Create comment artifacts
                    for comment in comments:
                        comment_dict = comment.model_dump()
                        reply_count = reply_counts.get(comment.id, 0)

                        comment_artifact = FigmaCommentArtifact.from_api_response(
                            comment_data=comment_dict,
                            file_name=file_data.name,
                            ingest_job_id=ingest_job_id,
                            reply_count=reply_count,
                            editor_type=file_data.editor_type,
                        )
                        comment_artifacts.append(comment_artifact)
                        comment_entity_ids.append(comment_artifact.entity_id)

                except Exception as e:
                    logger.warning(
                        f"Failed to fetch comments for file {file_key}: {e}",
                        tenant_id=tenant_id,
                        file_key=file_key,
                    )

            except Exception as e:
                logger.error(
                    f"Failed to fetch file {file_key}: {e}",
                    tenant_id=tenant_id,
                    file_key=file_key,
                )
                continue

        # Store all artifacts in batch
        if file_artifacts:
            logger.info(f"Storing {len(file_artifacts)} file artifacts")
            await self.store_artifacts_batch(db_pool, file_artifacts)

        if comment_artifacts:
            logger.info(f"Storing {len(comment_artifacts)} comment artifacts")
            await self.store_artifacts_batch(db_pool, comment_artifacts)

        # Trigger indexing for files
        if file_entity_ids:
            logger.info(f"Triggering indexing for {len(file_entity_ids)} files")

            total_file_batches = math.ceil(len(file_entity_ids) / DEFAULT_INDEX_BATCH_SIZE)
            if config.backfill_id and total_file_batches > 0:
                await increment_backfill_total_index_jobs(
                    config.backfill_id, tenant_id, total_file_batches
                )

            for i in range(0, len(file_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch = file_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    DocumentSource.FIGMA_FILE,
                    tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

        # Trigger indexing for comments
        if comment_entity_ids:
            logger.info(f"Triggering indexing for {len(comment_entity_ids)} comments")

            total_comment_batches = math.ceil(len(comment_entity_ids) / DEFAULT_INDEX_BATCH_SIZE)
            if config.backfill_id and total_comment_batches > 0:
                await increment_backfill_total_index_jobs(
                    config.backfill_id, tenant_id, total_comment_batches
                )

            for i in range(0, len(comment_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batch = comment_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batch,
                    DocumentSource.FIGMA_COMMENT,
                    tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

        logger.info(
            f"Completed Figma files batch: {len(file_artifacts)} files, {len(comment_artifacts)} comments",
            tenant_id=tenant_id,
            files_processed=len(file_artifacts),
            comments_processed=len(comment_artifacts),
            files_failed=len(file_keys) - len(file_artifacts),
        )

        if config.backfill_id:
            await increment_backfill_done_ingest_jobs(config.backfill_id, tenant_id, 1)
