"""Trello incremental sync extractor for periodic backfill without webhooks.

This extractor implements an action-based incremental sync strategy using
action IDs as cursors (similar to Asana's sync token pattern):

1. For each organization, gets all boards
2. For each board, fetches actions since the last processed action ID
3. Identifies cards that were modified (created, updated, moved, etc.)
4. Identifies cards and boards that were deleted
5. Re-indexes modified cards and prunes deleted cards/boards
6. Stores the newest action ID per board as cursor for next sync

Key design decisions:
- Uses board actions endpoint (`/boards/{id}/actions`) which captures ALL actions
  from ALL members on that board (not just the authenticated user)
- Iterates through all boards in all organizations to get comprehensive coverage
- This solves the limitation of webhooks which only captured actions by the
  authenticated member
- Uses action ID as cursor (not timestamp) for reliable pagination
  - Trello accepts action IDs in the 'since' parameter
  - Avoids edge cases with actions created in the same second
- First sync looks back 24 hours using ISO timestamp
- Cursors are stored per board to handle incremental updates efficiently
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.trello.trello_action_router import TrelloActionHandler, TrelloActionRouter
from connectors.trello.trello_base import TrelloExtractor
from connectors.trello.trello_models import TrelloIncrementalSyncConfig
from connectors.trello.trello_pruner import trello_pruner
from src.ingest.services.trello import trello_sync_service

logger = logging.getLogger(__name__)

# Default lookback period when no previous sync exists (24 hours)
DEFAULT_LOOKBACK_HOURS = 24

# Store and trigger indexing in batches
ARTIFACT_BATCH_SIZE = 10

# Maximum actions to fetch per sync (pagination limit)
MAX_ACTIONS_PER_SYNC = 5000

# Action types that indicate a card was deleted
CARD_DELETE_ACTIONS = {"deleteCard"}

# Action types that indicate a board was deleted/closed
BOARD_DELETE_ACTIONS = {"closeBoard", "deleteBoard"}


@dataclass
class ActionProcessingResult:
    """Result of processing organization/member actions."""

    card_ids_to_refresh: set[str]
    card_ids_to_delete: set[str]
    board_ids_to_delete: set[str]
    newest_action_id: str | None  # For cursor update


@dataclass
class BoardSyncResult:
    """Result of processing actions for a single board."""

    cards_refreshed: int
    cards_deleted: int
    board_deleted: bool


class TrelloIncrementalSyncExtractor(TrelloExtractor[TrelloIncrementalSyncConfig]):
    """Extractor for Trello incremental sync jobs.

    This extractor processes BOARD actions since the last sync to identify
    cards that need to be refreshed or deleted. It uses action IDs as cursors
    for reliable pagination (similar to Asana's sync token pattern).

    Iterates through all boards in all organizations to capture ALL actions from
    ALL members on each board. This solves the limitation of webhooks which only
    captured actions by the member who installed the integration.
    """

    source_name = "trello_incremental_sync"

    async def process_job(
        self,
        job_id: str,
        config: TrelloIncrementalSyncConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process Trello incremental sync job.

        Iterates through all organizations and their boards, fetching actions
        from each board to identify cards that need to be refreshed or deleted.

        Args:
            job_id: The job ID
            config: Incremental sync configuration
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing after artifacts are stored
        """
        logger.info(
            f"[trello] Processing incremental sync job {job_id} for tenant {config.tenant_id}"
        )

        try:
            trello_client = await self.get_trello_client(config.tenant_id)

            # Collect all boards to process (from organizations + personal boards)
            all_boards: list[dict] = []
            board_ids_seen: set[str] = set()

            # Get boards from organizations
            organizations = trello_client.get_organizations()
            if organizations:
                logger.info(
                    f"[trello] Found {len(organizations)} organizations for tenant {config.tenant_id}"
                )
                for org in organizations:
                    org_id = org.get("id")
                    org_name = org.get("displayName") or org.get("name", "Unknown")
                    if not org_id:
                        continue

                    org_boards = trello_client.get_organization_boards(org_id)
                    for board in org_boards:
                        board_id = board.get("id")
                        if board_id and board_id not in board_ids_seen:
                            board["_org_name"] = org_name  # Add org context for logging
                            all_boards.append(board)
                            board_ids_seen.add(board_id)

                    logger.info(f"[trello] Found {len(org_boards)} boards in org '{org_name}'")

            # Also get member's personal boards (not in any org)
            member_boards = trello_client.get_boards()
            for member_board in member_boards:
                board_id = member_board.id
                if board_id and board_id not in board_ids_seen:
                    all_boards.append(
                        {"id": board_id, "name": member_board.name, "_org_name": None}
                    )
                    board_ids_seen.add(board_id)

            if not all_boards:
                logger.info(f"[trello] No boards found for tenant {config.tenant_id}")
                return

            logger.info(
                f"[trello] Processing {len(all_boards)} boards for tenant {config.tenant_id}"
            )

            # Aggregate results across all boards
            total_cards_refreshed = 0
            total_cards_deleted = 0
            total_boards_deleted = 0

            # Process each board
            for board in all_boards:
                board_id = board.get("id")
                board_name = board.get("name", "Unknown")
                org_name = board.get("_org_name")

                if not board_id:
                    continue

                location = f" in org '{org_name}'" if org_name else " (personal)"
                logger.info(f"[trello] Processing board '{board_name}'{location}")

                result = await self._process_board_actions(
                    trello_client=trello_client,
                    board_id=board_id,
                    board_name=board_name,
                    job_id=job_id,
                    config=config,
                    db_pool=db_pool,
                    trigger_indexing=trigger_indexing,
                )

                total_cards_refreshed += result.cards_refreshed
                total_cards_deleted += result.cards_deleted
                if result.board_deleted:
                    total_boards_deleted += 1

            logger.info(
                f"[trello] Incremental sync complete for tenant {config.tenant_id}: "
                f"{total_cards_refreshed} cards refreshed, "
                f"{total_cards_deleted} cards deleted, "
                f"{total_boards_deleted} boards deleted across {len(all_boards)} boards"
            )

        except Exception as e:
            logger.error(
                f"[trello] Incremental sync job {job_id} failed: {e}",
                exc_info=True,
            )
            raise

    async def _process_board_actions(
        self,
        trello_client,
        board_id: str,
        board_name: str,
        job_id: str,
        config: TrelloIncrementalSyncConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> BoardSyncResult:
        """Process actions for a single board.

        Args:
            trello_client: Trello API client
            board_id: Board ID
            board_name: Board display name for logging
            job_id: The job ID
            config: Incremental sync configuration
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing

        Returns:
            BoardSyncResult with counts of cards processed
        """
        # Get the cursor (last action ID) for this board
        last_action_id = await trello_sync_service.get_last_action_id(db_pool, board_id=board_id)

        # Determine the 'since' parameter for the API call
        if last_action_id:
            since_param = last_action_id
            logger.info(f"[trello] Board '{board_name}': resuming from action {last_action_id}")
        else:
            # First run for this board - use ISO timestamp for lookback
            lookback_time = datetime.now(UTC) - timedelta(hours=DEFAULT_LOOKBACK_HOURS)
            since_param = lookback_time.isoformat()
            logger.info(
                f"[trello] First sync for board '{board_name}', looking back {DEFAULT_LOOKBACK_HOURS} hours"
            )

        # Fetch ALL board actions since cursor
        actions = trello_client.get_board_actions_paginated(
            board_id=board_id,
            since=since_param,
            max_actions=MAX_ACTIONS_PER_SYNC,
        )

        if not actions:
            logger.info(f"[trello] No new actions found for board '{board_name}'")
            return BoardSyncResult(cards_refreshed=0, cards_deleted=0, board_deleted=False)

        logger.info(f"[trello] Processing {len(actions)} actions for board '{board_name}'")

        # Process actions to identify cards/boards to refresh/delete
        result = self._process_actions(actions)

        # Remove deleted cards from refresh set
        result.card_ids_to_refresh -= result.card_ids_to_delete

        logger.info(
            f"[trello] Board '{board_name}' sync summary: "
            f"{len(result.card_ids_to_refresh)} cards to refresh, "
            f"{len(result.card_ids_to_delete)} cards to delete, "
            f"{len(result.board_ids_to_delete)} boards to delete"
        )

        # Process deletions first
        await self._process_deletions(
            card_ids=result.card_ids_to_delete,
            board_ids=result.board_ids_to_delete,
            tenant_id=config.tenant_id,
            db_pool=db_pool,
        )

        # Process card refreshes
        if result.card_ids_to_refresh:
            await self._refresh_cards(
                card_ids=result.card_ids_to_refresh,
                tenant_id=config.tenant_id,
                job_id=job_id,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
                config=config,
            )

        # Update cursor for this board with the newest action ID
        if result.newest_action_id:
            await trello_sync_service.set_last_action_id(
                result.newest_action_id, db_pool, board_id=board_id
            )
            logger.info(
                f"[trello] Board '{board_name}' sync complete, cursor updated to action {result.newest_action_id}"
            )

        return BoardSyncResult(
            cards_refreshed=len(result.card_ids_to_refresh),
            cards_deleted=len(result.card_ids_to_delete),
            board_deleted=len(result.board_ids_to_delete) > 0,
        )

    def _process_actions(self, actions: list[dict]) -> ActionProcessingResult:
        """Process a list of member actions to identify cards needing refresh/deletion.

        Actions are returned newest-first by the API, so the first action's ID
        becomes our cursor for the next sync.

        Args:
            actions: List of Trello action dicts from the member actions API

        Returns:
            ActionProcessingResult with sets of card/board IDs and newest action ID
        """
        card_ids_to_refresh: set[str] = set()
        card_ids_to_delete: set[str] = set()
        board_ids_to_delete: set[str] = set()

        # Actions are newest-first, so first action is our cursor
        newest_action_id = actions[0].get("id") if actions else None

        for action in actions:
            action_type = action.get("type", "")
            action_data = action.get("data", {})

            # Get the handler type for this action
            handler = TrelloActionRouter.get_handler(action_type)

            # Extract card ID from action data if present
            card_data = action_data.get("card", {})
            card_id = card_data.get("id") if card_data else None

            # Handle card refresh actions
            if handler in (
                TrelloActionHandler.CARD_CONTENT,
                TrelloActionHandler.CARD_METADATA,
                TrelloActionHandler.CARD_MOVEMENT,
            ):
                if card_id:
                    card_ids_to_refresh.add(card_id)

            # Handle card deletion actions
            elif handler == TrelloActionHandler.DELETION:
                if action_type in CARD_DELETE_ACTIONS and card_id:
                    card_ids_to_delete.add(card_id)
                elif action_type in BOARD_DELETE_ACTIONS:
                    board_data = action_data.get("board", {})
                    board_id = board_data.get("id") if board_data else None
                    if board_id:
                        board_ids_to_delete.add(board_id)
                        logger.info(
                            f"[trello] Board deletion detected: {action_type} for board {board_id}"
                        )

            # Handle card movement between boards
            if action_type == "moveCardFromBoard" and card_id:
                # Card moved away - we might need to delete it from this board's context
                # But the card still exists, so we should refresh it
                card_ids_to_refresh.add(card_id)

            if action_type == "moveCardToBoard" and card_id:
                # Card moved to this board - refresh it
                card_ids_to_refresh.add(card_id)

        return ActionProcessingResult(
            card_ids_to_refresh=card_ids_to_refresh,
            card_ids_to_delete=card_ids_to_delete,
            board_ids_to_delete=board_ids_to_delete,
            newest_action_id=newest_action_id,
        )

    async def _process_deletions(
        self,
        card_ids: set[str],
        board_ids: set[str],
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> None:
        """Process card and board deletions.

        Args:
            card_ids: Set of card IDs to delete
            board_ids: Set of board IDs to delete (will also delete their cards)
            tenant_id: The tenant ID
            db_pool: Database connection pool
        """
        # Delete boards first (this also deletes their cards)
        for board_id in board_ids:
            try:
                success = await trello_pruner.delete_board(board_id, tenant_id, db_pool)
                if success:
                    logger.info(f"[trello] Deleted board {board_id} and associated cards")
                else:
                    logger.warning(f"[trello] Failed to delete board {board_id}")
            except Exception as e:
                logger.error(f"[trello] Error deleting board {board_id}: {e}")

        # Delete individual cards (that weren't part of deleted boards)
        for card_id in card_ids:
            try:
                success = await trello_pruner.delete_card(card_id, tenant_id, db_pool)
                if success:
                    logger.debug(f"[trello] Deleted card {card_id}")
                else:
                    logger.warning(f"[trello] Failed to delete card {card_id}")
            except Exception as e:
                logger.error(f"[trello] Error deleting card {card_id}: {e}")

    async def _refresh_cards(
        self,
        card_ids: set[str],
        tenant_id: str,
        job_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
        config: TrelloIncrementalSyncConfig,
    ) -> None:
        """Refresh a set of cards by fetching their full data and re-indexing.

        Args:
            card_ids: Set of card IDs to refresh
            tenant_id: The tenant ID
            job_id: The job ID
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
            config: The job config
        """
        trello_client = await self.get_trello_client(tenant_id)

        artifact_batch = []
        entity_ids_batch: list[str] = []

        # Pre-fetch board data cache to avoid repeated API calls
        board_cache: dict[str, dict] = {}
        board_members_cache: dict[str, list[str]] = {}
        board_lists_cache: dict[str, dict[str, str]] = {}

        for card_id in card_ids:
            try:
                # Fetch full card data with board and list info included
                card_data = trello_client.get_card(card_id)
                if not card_data:
                    logger.warning(f"[trello] Card {card_id} not found, may have been deleted")
                    continue

                # Skip archived/closed cards
                if card_data.get("closed", False):
                    logger.debug(f"[trello] Skipping archived card {card_id}")
                    continue

                board_id = card_data.get("idBoard", "")
                list_id = card_data.get("idList", "")

                # Get board info from cache or API
                if board_id and board_id not in board_cache:
                    try:
                        board_data = trello_client.get_board(board_id)
                        board_cache[board_id] = board_data

                        # Get board members
                        members = trello_client.get_members_on_board(board_id)
                        board_members_cache[board_id] = [
                            m.get("email", "").lower() for m in members if m.get("email")
                        ]

                        # Get board lists
                        lists = trello_client.get_lists_on_board(board_id)
                        board_lists_cache[board_id] = {lst["id"]: lst["name"] for lst in lists}
                    except Exception as e:
                        logger.error(f"[trello] Failed to fetch board {board_id} info: {e}")
                        board_cache[board_id] = {}
                        board_members_cache[board_id] = []
                        board_lists_cache[board_id] = {}

                board_data = board_cache.get(board_id, {})
                board_name = board_data.get("name")
                board_permission_level = board_data.get("prefs", {}).get("permissionLevel", "org")
                board_member_emails = board_members_cache.get(board_id, [])
                list_name = board_lists_cache.get(board_id, {}).get(list_id)

                # Process card into artifact
                artifacts = await self._process_card(
                    job_id,
                    card_data,
                    tenant_id,
                    board_name=board_name,
                    list_name=list_name,
                    board_permission_level=board_permission_level,
                    board_member_emails=board_member_emails,
                )

                artifact_batch.extend(artifacts)
                entity_ids_batch.extend([a.entity_id for a in artifacts])

                # Store and trigger indexing in batches
                if len(artifact_batch) >= ARTIFACT_BATCH_SIZE:
                    await self._flush_batch(
                        artifact_batch,
                        entity_ids_batch,
                        db_pool,
                        trigger_indexing,
                        config,
                    )
                    artifact_batch = []
                    entity_ids_batch = []

            except Exception as e:
                logger.error(f"[trello] Failed to refresh card {card_id}: {e}", exc_info=True)
                continue

        # Flush remaining batch
        if artifact_batch:
            await self._flush_batch(
                artifact_batch,
                entity_ids_batch,
                db_pool,
                trigger_indexing,
                config,
            )

    async def _flush_batch(
        self,
        artifacts: list,
        entity_ids: list[str],
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
        config: TrelloIncrementalSyncConfig,
    ) -> None:
        """Store artifacts and trigger indexing for a batch.

        Args:
            artifacts: List of artifacts to store
            entity_ids: List of entity IDs for indexing
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing
            config: The job config
        """
        logger.info(f"[trello] Storing batch of {len(artifacts)} artifacts")
        await self.store_artifacts_batch(db_pool, artifacts)

        if entity_ids:
            await trigger_indexing(
                entity_ids,
                DocumentSource.TRELLO,
                config.tenant_id,
                config.backfill_id,
                config.suppress_notification,
            )
            logger.info(f"[trello] Triggered indexing for batch of {len(entity_ids)} cards")
