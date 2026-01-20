"""
Trello service for installation management and sync tracking.

This module provides services for:
- Tracking Trello installations (member connections to tenants)
- Managing incremental sync cursor (action ID) per tenant
"""

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from src.utils.logging import get_logger
from src.utils.tenant_config import (
    delete_config_value_with_pool,
    delete_config_values_by_prefix_with_pool,
    get_config_value_with_pool,
    set_config_value_with_pool,
)

logger = get_logger(__name__)


@dataclass
class TrelloInstallation:
    """Represents a Trello installation (member connected to a tenant)."""

    member_id: str
    tenant_id: str
    member_username: str | None
    webhook_id: str | None
    created_at: datetime
    updated_at: datetime


class TrelloInstallationService:
    """Service for managing Trello installations via connector_installations table."""

    async def get_installation(
        self, tenant_id: str, conn: asyncpg.Connection
    ) -> TrelloInstallation | None:
        """Get the Trello installation for a given tenant."""
        installation_row = await conn.fetchrow(
            """SELECT external_id as member_id, tenant_id,
                      external_metadata->>'member_username' as member_username,
                      external_metadata->>'webhook_id' as webhook_id,
                      created_at, updated_at
               FROM connector_installations
               WHERE tenant_id = $1 AND type = 'trello' AND status != 'disconnected'
               ORDER BY created_at DESC LIMIT 1""",
            tenant_id,
        )
        if not installation_row:
            return None
        return TrelloInstallation(
            member_id=installation_row["member_id"],
            tenant_id=installation_row["tenant_id"],
            member_username=installation_row["member_username"],
            webhook_id=installation_row["webhook_id"],
            created_at=installation_row["created_at"],
            updated_at=installation_row["updated_at"],
        )

    async def get_all_installations(self, conn: asyncpg.Connection) -> list[TrelloInstallation]:
        """Get all active Trello installations."""
        installations_rows = await conn.fetch(
            """SELECT external_id as member_id, tenant_id,
                      external_metadata->>'member_username' as member_username,
                      external_metadata->>'webhook_id' as webhook_id,
                      created_at, updated_at
               FROM connector_installations
               WHERE type = 'trello' AND status != 'disconnected'""",
        )
        return [
            TrelloInstallation(
                member_id=row["member_id"],
                tenant_id=row["tenant_id"],
                member_username=row["member_username"],
                webhook_id=row["webhook_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in installations_rows
        ]


trello_installation_service = TrelloInstallationService()


class TrelloSyncService:
    """Service for tracking Trello incremental sync cursor per board.

    Uses action ID as cursor instead of timestamp for more reliable pagination.
    Trello's API accepts action IDs in the 'since' parameter and derives the
    timestamp internally, which avoids issues with actions created in the same second.

    Cursors are stored per board to support board-level incremental sync,
    which captures ALL actions from ALL members on that board.

    Similar pattern to Asana's sync token approach, but using Trello's native
    action ID-based cursor mechanism.
    """

    CURSOR_KEY_PREFIX = "TRELLO_INCREMENTAL_SYNC_LAST_ACTION_ID"

    def _get_cursor_key(self, board_id: str) -> str:
        """Get the config key for a board's sync cursor."""
        return f"{self.CURSOR_KEY_PREFIX}:board:{board_id}"

    async def get_last_action_id(
        self, db_pool: asyncpg.Pool, board_id: str | None = None
    ) -> str | None:
        """Get the last processed action ID for Trello incremental sync.

        This action ID serves as a cursor - subsequent syncs will fetch
        actions created after this action.

        Args:
            db_pool: Tenant database connection pool
            board_id: Board ID (required for board-level cursor)

        Returns:
            The last action ID, or None if never synced
        """
        # Use board-specific key if board_id provided, otherwise legacy key for backwards compat
        cursor_key = self._get_cursor_key(board_id) if board_id else self.CURSOR_KEY_PREFIX
        return await get_config_value_with_pool(cursor_key, db_pool)

    async def set_last_action_id(
        self, action_id: str, db_pool: asyncpg.Pool, board_id: str | None = None
    ) -> None:
        """Set the last processed action ID for Trello incremental sync.

        Args:
            action_id: The action ID to store as cursor
            db_pool: Tenant database connection pool
            board_id: Board ID (required for board-level cursor)
        """
        # Use board-specific key if board_id provided, otherwise legacy key for backwards compat
        cursor_key = self._get_cursor_key(board_id) if board_id else self.CURSOR_KEY_PREFIX
        await set_config_value_with_pool(cursor_key, action_id, db_pool)
        board_suffix = f" for board {board_id}" if board_id else ""
        logger.debug(f"[trello] Updated sync cursor to action ID: {action_id}{board_suffix}")

    async def clear_cursor(self, db_pool: asyncpg.Pool, board_id: str | None = None) -> None:
        """Clear the sync cursor, forcing a full lookback on next sync.

        Args:
            db_pool: Tenant database connection pool
            board_id: Board ID. If None, clears ALL cursors (legacy and all boards)
        """
        if board_id:
            # Clear specific board cursor
            cursor_key = self._get_cursor_key(board_id)
            await delete_config_value_with_pool(cursor_key, db_pool)
            logger.info(f"[trello] Cleared sync cursor for board {board_id}")
        else:
            # Clear all Trello cursors (legacy and all boards)
            deleted_count = await delete_config_values_by_prefix_with_pool(
                self.CURSOR_KEY_PREFIX, db_pool
            )
            logger.info(f"[trello] Cleared all sync cursors ({deleted_count} removed)")


trello_sync_service = TrelloSyncService()
