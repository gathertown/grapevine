"""Trello API backfill extractor for batch processing boards and cards."""

import logging

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.trello.trello_base import TrelloExtractor
from connectors.trello.trello_models import TrelloApiBackfillConfig
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
)

logger = logging.getLogger(__name__)

# Store and trigger indexing in batches of 10 to avoid memory issues
ARTIFACT_BATCH_SIZE = 10


class TrelloApiBackfillExtractor(TrelloExtractor[TrelloApiBackfillConfig]):
    """Extractor for Trello API backfill jobs.

    This extractor processes batches of Trello boards, fetching all cards from each board
    and creating TrelloCardArtifacts for indexing.
    """

    source_name = "trello_api_backfill"

    async def process_job(
        self,
        job_id: str,
        config: TrelloApiBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process Trello API backfill job for specified boards.

        Args:
            job_id: The job ID
            config: Backfill configuration with board batches
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing after artifacts are stored

        Raises:
            Exception: If job processing fails
        """
        logger.info(
            f"Processing Trello API backfill job {job_id} for tenant {config.tenant_id} "
            f"with {len(config.board_batches)} board batches"
        )

        try:
            trello_client = await self.get_trello_client(config.tenant_id)

            artifact_batch = []
            entity_ids_batch: list[str] = []

            for board_batch in config.board_batches:
                logger.info(
                    f"Processing Trello board: {board_batch.board_name} ({board_batch.board_id})"
                )

                try:
                    # Fetch board details to get permission level
                    board_data = trello_client.get_board(board_batch.board_id)
                    board_permission_level = board_data.get("prefs", {}).get(
                        "permissionLevel", "org"
                    )

                    # Fetch board members for permission resolution
                    board_members = trello_client.get_members_on_board(board_batch.board_id)
                    board_member_emails = [
                        member.get("email", "").lower()
                        for member in board_members
                        if member.get("email")
                    ]

                    logger.info(
                        f"Board {board_batch.board_name} permission level: {board_permission_level}, "
                        f"members: {len(board_member_emails)}"
                    )

                    # Fetch all cards for this board
                    cards = trello_client.get_cards_on_board(board_batch.board_id)

                    # Fetch lists for this board to resolve list names
                    lists_on_board = trello_client.get_lists_on_board(board_batch.board_id)
                    list_id_to_name = {lst["id"]: lst["name"] for lst in lists_on_board}

                    logger.info(
                        f"Processing {len(cards)} cards from board {board_batch.board_name} "
                        f"with {len(list_id_to_name)} lists"
                    )

                    for card_data in cards:
                        card_id = card_data.get("id", "")
                        card_name = card_data.get("name", "Untitled")

                        batch_flushed = False
                        try:
                            # Resolve list name from list_id
                            list_id = card_data.get("idList", "")
                            list_name = list_id_to_name.get(list_id)

                            # Process card into artifact with permission data
                            artifacts = await self._process_card(
                                job_id,
                                card_data,
                                config.tenant_id,
                                board_name=board_batch.board_name,
                                list_name=list_name,
                                board_permission_level=board_permission_level,
                                board_member_emails=board_member_emails,
                            )

                            # Add to batch
                            artifact_batch.extend(artifacts)
                            # Collect entity IDs from artifacts for indexing
                            entity_ids_batch.extend([artifact.entity_id for artifact in artifacts])

                            # Store and trigger indexing in batches
                            if len(artifact_batch) >= ARTIFACT_BATCH_SIZE:
                                logger.info(
                                    f"Storing batch of {len(artifact_batch)} Trello artifacts"
                                )
                                # Use force update if specified (e.g., for GDPR profile updates)
                                if config.force_update:
                                    await self.force_store_artifacts_batch(db_pool, artifact_batch)
                                else:
                                    await self.store_artifacts_batch(db_pool, artifact_batch)

                                if entity_ids_batch:
                                    await trigger_indexing(
                                        entity_ids_batch,
                                        DocumentSource.TRELLO,
                                        config.tenant_id,
                                        config.backfill_id,
                                        config.suppress_notification,
                                    )
                                    logger.info(
                                        f"Triggered indexing for batch of {len(entity_ids_batch)} cards"
                                    )

                                # Mark that batch was successfully flushed
                                batch_flushed = True

                        except Exception as e:
                            logger.error(
                                f"Failed to process card {card_id} ({card_name}): {e}",
                                exc_info=True,
                            )
                            continue

                        finally:
                            # Reset batches after successful flush to prevent duplicate processing
                            if batch_flushed:
                                artifact_batch = []
                                entity_ids_batch = []

                except Exception as e:
                    logger.error(
                        f"Failed to process board {board_batch.board_id} ({board_batch.board_name}): {e}",
                        exc_info=True,
                    )
                    continue

            # Store final batch
            if artifact_batch:
                logger.info(f"Storing final batch of {len(artifact_batch)} Trello artifacts")
                # Use force update if specified (e.g., for GDPR profile updates)
                if config.force_update:
                    await self.force_store_artifacts_batch(db_pool, artifact_batch)
                else:
                    await self.store_artifacts_batch(db_pool, artifact_batch)

                if entity_ids_batch:
                    await trigger_indexing(
                        entity_ids_batch,
                        DocumentSource.TRELLO,
                        config.tenant_id,
                        config.backfill_id,
                        config.suppress_notification,
                    )
                    logger.info(
                        f"Triggered indexing for final batch of {len(entity_ids_batch)} cards"
                    )

            # Update backfill progress
            if config.backfill_id:
                await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

        except Exception as e:
            logger.error(f"Trello API backfill job {job_id} failed: {e}", exc_info=True)
            raise
        finally:
            # Always increment attempted count
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )
