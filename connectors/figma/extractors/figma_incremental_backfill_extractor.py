"""Figma incremental backfill extractor.

Performs incremental sync by checking file versions since last sync.
Figma doesn't have a direct "updated since" API, so we need to:
1. Get all files from teams
2. Check each file's lastModified timestamp
3. Only process files modified since last sync
"""

import math
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.figma.client import FigmaClient, get_figma_client_for_tenant
from connectors.figma.figma_models import (
    FigmaCommentArtifact,
    FigmaFileArtifact,
    FigmaIncrementalBackfillConfig,
)
from connectors.figma.figma_sync_service import FigmaSyncService
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_index_jobs

logger = get_logger(__name__)

# Default lookback window for incremental sync
DEFAULT_LOOKBACK_HOURS = 24


class FigmaIncrementalBackfillExtractor(BaseExtractor[FigmaIncrementalBackfillConfig]):
    """Extractor for incremental Figma sync.

    Checks file modification timestamps and only syncs changed files.
    """

    source_name = "figma_incremental_backfill"

    async def process_job(
        self,
        job_id: str,
        config: FigmaIncrementalBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process incremental sync for Figma."""
        tenant_id = config.tenant_id
        lookback_hours = config.lookback_hours or DEFAULT_LOOKBACK_HOURS

        logger.info(
            "Starting Figma incremental backfill",
            tenant_id=tenant_id,
            lookback_hours=lookback_hours,
        )

        sync_service = FigmaSyncService(db_pool, tenant_id)

        # Determine the sync window
        # Use synced_until cursor or fall back to lookback window
        files_synced_until = await sync_service.get_files_synced_until()

        if files_synced_until:
            since = files_synced_until - timedelta(seconds=1)  # Small overlap
        else:
            since = datetime.now(UTC) - timedelta(hours=lookback_hours)

        logger.info(
            "Incremental sync since",
            tenant_id=tenant_id,
            since=since.isoformat(),
        )

        # Get selected team IDs
        team_ids = await sync_service.get_selected_team_ids()

        if not team_ids:
            logger.warning(
                "No team IDs selected for Figma incremental sync",
                tenant_id=tenant_id,
            )
            return

        try:
            async with await get_figma_client_for_tenant(tenant_id) as client:
                # Collect modified files
                modified_files: list[
                    tuple[str, str | None, str | None]
                ] = []  # (file_key, project_id, team_id)

                for team_id in team_ids:
                    try:
                        team_files = await client.iter_team_files(team_id)
                        for project, file_meta in team_files:
                            # Parse the file's last_modified timestamp
                            try:
                                file_modified = datetime.fromisoformat(
                                    file_meta.last_modified.replace("Z", "+00:00")
                                )
                                if file_modified > since:
                                    modified_files.append((file_meta.key, project.id, team_id))
                            except (ValueError, AttributeError):
                                # If we can't parse timestamp, include it to be safe
                                modified_files.append((file_meta.key, project.id, team_id))

                    except Exception as e:
                        logger.error(
                            f"Failed to get files for team {team_id}: {e}",
                            tenant_id=tenant_id,
                            team_id=team_id,
                        )
                        continue

                logger.info(
                    f"Found {len(modified_files)} modified files since {since.isoformat()}",
                    tenant_id=tenant_id,
                )

                if not modified_files:
                    # Update sync cursor even if no changes
                    await sync_service.set_files_synced_until(datetime.now(UTC))
                    await sync_service.set_comments_synced_until(datetime.now(UTC))
                    return

                # Process modified files
                await self._process_modified_files(
                    client=client,
                    db_pool=db_pool,
                    job_id=job_id,
                    trigger_indexing=trigger_indexing,
                    config=config,
                    modified_files=modified_files,
                )

                # Update sync cursors
                await sync_service.set_files_synced_until(datetime.now(UTC))
                await sync_service.set_comments_synced_until(datetime.now(UTC))

                logger.info(
                    "Figma incremental backfill complete",
                    tenant_id=tenant_id,
                    files_processed=len(modified_files),
                )
        except Exception as e:
            logger.error(f"Failed to get Figma client: {e}")
            raise

    async def _process_modified_files(
        self,
        client: FigmaClient,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        config: FigmaIncrementalBackfillConfig,
        modified_files: list[tuple[str, str | None, str | None]],
    ) -> None:
        """Process modified files and their comments."""
        tenant_id = config.tenant_id
        ingest_job_id = UUID(job_id)

        file_artifacts: list[FigmaFileArtifact] = []
        comment_artifacts: list[FigmaCommentArtifact] = []
        file_entity_ids: list[str] = []
        comment_entity_ids: list[str] = []

        for file_key, project_id, team_id in modified_files:
            try:
                # Fetch full file data
                file_data = await client.get_file(file_key)

                # Convert to dict
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

                # Fetch comments
                try:
                    comments = await client.get_file_comments(file_key)

                    reply_counts: dict[str, int] = {}
                    for comment in comments:
                        if comment.parent_id:
                            reply_counts[comment.parent_id] = (
                                reply_counts.get(comment.parent_id, 0) + 1
                            )

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
                    )

            except ExtendVisibilityException:
                raise
            except Exception as e:
                logger.error(
                    f"Failed to fetch file {file_key}: {e}",
                    tenant_id=tenant_id,
                )
                continue

        # Store artifacts
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
