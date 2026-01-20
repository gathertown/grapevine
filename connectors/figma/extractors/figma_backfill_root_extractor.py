"""Root extractor for Figma full backfill.

Orchestrates the full backfill by:
1. Setting incremental sync cursors to "now"
2. Collecting all file keys from teams
3. Enqueuing file-specific backfill jobs for batch processing
"""

import secrets
from datetime import UTC, datetime

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.figma.client import get_figma_client_for_tenant
from connectors.figma.figma_models import FigmaBackfillRootConfig, FigmaFileBackfillConfig
from connectors.figma.figma_sync_service import FigmaSyncService
from src.clients.sqs import SQSClient
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)

# Batch size for file processing jobs
BATCH_SIZE = 10  # Figma has stricter rate limits, so smaller batches


class FigmaBackfillRootExtractor(BaseExtractor[FigmaBackfillRootConfig]):
    """Root extractor that discovers all files and splits into batch jobs.

    This extractor:
    1. Sets incremental sync cursors to "now" (so incremental picks up changes during backfill)
    2. Discovers all files from selected teams
    3. Splits them into batches and enqueues child jobs for file + comment processing
    """

    source_name = "figma_backfill_root"

    def __init__(self, sqs_client: SQSClient):
        super().__init__()
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: FigmaBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or secrets.token_hex(8)
        tenant_id = config.tenant_id

        logger.info(
            "Starting Figma backfill root job",
            backfill_id=backfill_id,
            tenant_id=tenant_id,
            team_ids_to_sync=config.team_ids_to_sync,
        )

        # Initialize services
        sync_service = FigmaSyncService(db_pool, tenant_id)

        # Step 1: Set incremental sync cursors to "now"
        sync_start_time = datetime.now(UTC)
        await sync_service.set_files_synced_until(sync_start_time)
        await sync_service.set_comments_synced_until(sync_start_time)

        logger.info(
            "Set incremental sync cursors",
            tenant_id=tenant_id,
            sync_start_time=sync_start_time.isoformat(),
        )

        # Step 2: Determine which team IDs to sync
        # If team_ids_to_sync is provided, only sync those specific teams
        # Otherwise, fall back to syncing all selected teams
        if config.team_ids_to_sync:
            team_ids = config.team_ids_to_sync
            logger.info(
                "Syncing specific teams from config",
                tenant_id=tenant_id,
                team_ids=team_ids,
            )
        else:
            team_ids = await sync_service.get_selected_team_ids()
            logger.info(
                "Syncing all selected teams",
                tenant_id=tenant_id,
                team_ids=team_ids,
            )

        if not team_ids:
            logger.warning(
                "No team IDs selected for Figma backfill",
                tenant_id=tenant_id,
            )
            return

        # Step 3: Collect all file keys from teams
        all_files: list[tuple[str, str | None, str | None]] = []  # (file_key, project_id, team_id)
        successfully_synced_teams: list[str] = []

        try:
            async with await get_figma_client_for_tenant(tenant_id) as client:
                for team_id in team_ids:
                    try:
                        team_files = await client.iter_team_files(team_id)
                        files_for_team = 0
                        for project, file_meta in team_files:
                            all_files.append((file_meta.key, project.id, team_id))
                            files_for_team += 1
                        # Mark team as successfully synced (even if it has 0 files)
                        successfully_synced_teams.append(team_id)
                        logger.info(
                            f"Collected {files_for_team} files from team {team_id}",
                            tenant_id=tenant_id,
                            team_id=team_id,
                            files_count=files_for_team,
                        )
                    except Exception as e:
                        logger.error(
                            f"Failed to get files for team {team_id}: {e}",
                            tenant_id=tenant_id,
                            team_id=team_id,
                        )
                        continue
        except Exception as e:
            logger.error(f"Failed to get Figma client: {e}")
            raise

        logger.info(
            "Collected all Figma file keys",
            backfill_id=backfill_id,
            total_files=len(all_files),
            teams_synced=len(successfully_synced_teams),
            teams_requested=len(team_ids),
        )

        # Step 4: Mark successfully synced teams
        if successfully_synced_teams:
            await sync_service.add_synced_team_ids(successfully_synced_teams)
            logger.info(
                "Updated synced_team_ids in external_metadata",
                tenant_id=tenant_id,
                newly_synced_teams=successfully_synced_teams,
            )

        if not all_files:
            logger.warning(
                "No files found for Figma backfill",
                tenant_id=tenant_id,
            )
            return

        # Step 5: Create batches of files
        batches = self._create_batches(all_files)

        # Track total jobs for backfill progress tracking
        total_jobs = len(batches)
        await increment_backfill_total_ingest_jobs(backfill_id, tenant_id, total_jobs)

        # Step 6: Schedule batch jobs
        for batch in batches:
            file_keys = [f[0] for f in batch]
            # All files in a batch share the same project_id and team_id
            # (batches are grouped by these values in _create_batches)
            batch_project_id: str | None = batch[0][1] if batch else None
            batch_team_id: str | None = batch[0][2] if batch else None

            file_config = FigmaFileBackfillConfig(
                tenant_id=tenant_id,
                file_keys=file_keys,
                project_id=batch_project_id,
                team_id=batch_team_id,
                backfill_id=backfill_id,
            )

            await self.sqs_client.send_backfill_ingest_message(file_config)

        logger.info(
            "Figma root backfill complete - batch jobs enqueued",
            tenant_id=tenant_id,
            backfill_id=backfill_id,
            total_batches=total_jobs,
            total_files=len(all_files),
            teams_synced=successfully_synced_teams,
        )

    def _create_batches(
        self, files: list[tuple[str, str | None, str | None]]
    ) -> list[list[tuple[str, str | None, str | None]]]:
        """Split files into batches, grouped by project_id and team_id.

        Files are first grouped by (project_id, team_id) to ensure all files
        in a batch share the same metadata, then split into batches of BATCH_SIZE.
        """
        from collections import defaultdict

        # Group files by (project_id, team_id)
        groups: dict[tuple[str | None, str | None], list[tuple[str, str | None, str | None]]] = (
            defaultdict(list)
        )
        for file_key, project_id, team_id in files:
            groups[(project_id, team_id)].append((file_key, project_id, team_id))

        # Create batches within each group
        batches: list[list[tuple[str, str | None, str | None]]] = []
        for group_files in groups.values():
            for i in range(0, len(group_files), BATCH_SIZE):
                batches.append(group_files[i : i + BATCH_SIZE])

        return batches
