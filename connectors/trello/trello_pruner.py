"""Trello pruner for handling complete deletion flow (cards and boards)."""

import logging

import asyncpg

from connectors.base import ArtifactEntity, BasePruner
from connectors.base.doc_ids import get_trello_board_doc_id, get_trello_card_doc_id

logger = logging.getLogger(__name__)


class TrelloPruner(BasePruner):
    """Singleton class for handling Trello card and board deletions across all data stores."""

    async def delete_card(self, card_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete a Trello card from all data stores using the standardized template method.

        Args:
            card_id: The Trello card ID
            tenant_id: The tenant ID
            db_pool: Database connection pool (required)

        Returns:
            True if deletion was successful, False otherwise
        """
        if not card_id:
            logger.warning("No card_id provided for Trello card deletion")
            return False

        logger.info(f"Deleting Trello card: {card_id}")

        # Use the template method from BasePruner
        # Pass the trello document ID resolver directly
        return await self.delete_entity(
            entity_id=card_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_trello_card_doc_id,
            entity_type=ArtifactEntity.TRELLO_CARD.value,
        )

    async def delete_board(self, board_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete a Trello board and all its associated cards from all data stores.

        This method:
        1. Finds all cards belonging to the board (by querying metadata)
        2. Deletes each card individually
        3. Deletes the board itself

        Args:
            board_id: The Trello board ID
            tenant_id: The tenant ID
            db_pool: Database connection pool (required)

        Returns:
            True if deletion was successful, False otherwise
        """
        if not board_id:
            logger.warning("No board_id provided for Trello board deletion")
            return False

        logger.info(f"Deleting Trello board: {board_id} and all associated cards")

        try:
            async with db_pool.acquire() as conn:
                # Find all card artifacts for this board by querying metadata
                # The metadata JSONB column contains id_board field
                card_rows = await conn.fetch(
                    """
                    SELECT entity_id
                    FROM ingest_artifact
                    WHERE entity = $1
                    AND metadata->>'id_board' = $2
                    """,
                    ArtifactEntity.TRELLO_CARD.value,
                    board_id,
                )

                card_ids = [row["entity_id"] for row in card_rows]
                logger.info(f"Found {len(card_ids)} cards to delete for board {board_id}")

                # Delete each card individually
                failed_deletions = []
                for card_id in card_ids:
                    success = await self.delete_card(card_id, tenant_id, db_pool)
                    if not success:
                        failed_deletions.append(card_id)

                if failed_deletions:
                    logger.warning(
                        f"Failed to delete {len(failed_deletions)} cards from board {board_id}: {failed_deletions}"
                    )

                # Delete the board itself
                board_success = await self.delete_entity(
                    entity_id=board_id,
                    tenant_id=tenant_id,
                    db_pool=db_pool,
                    document_id_resolver=get_trello_board_doc_id,
                    entity_type=ArtifactEntity.TRELLO_BOARD.value,
                )

                if board_success:
                    logger.info(
                        f"Successfully deleted board {board_id} and {len(card_ids) - len(failed_deletions)}/{len(card_ids)} cards"
                    )
                else:
                    logger.error(f"Failed to delete board {board_id}")

                return board_success and len(failed_deletions) == 0

        except Exception as e:
            logger.error(f"Error deleting board {board_id}: {e}", exc_info=True)
            return False


# Singleton instance
trello_pruner = TrelloPruner()
