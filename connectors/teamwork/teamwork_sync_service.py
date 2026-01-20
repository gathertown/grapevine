"""Teamwork sync service for managing sync state."""

from datetime import datetime

import asyncpg

from connectors.teamwork.teamwork_models import (
    TEAMWORK_FULL_BACKFILL_COMPLETE_KEY,
    TEAMWORK_TASKS_CURSOR_KEY,
    TEAMWORK_TASKS_SYNCED_UNTIL_KEY,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TeamworkSyncService:
    """Service for managing Teamwork sync state in tenant config."""

    def __init__(self, db_pool: asyncpg.Pool, tenant_id: str):
        self.db_pool = db_pool
        self.tenant_id = tenant_id

    async def _get_config_value(self, key: str) -> str | None:
        """Get a config value from the tenant config table."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT value FROM config WHERE key = $1",
                key,
            )
            return row["value"] if row else None

    async def _set_config_value(self, key: str, value: str) -> None:
        """Set a config value in the tenant config table."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO config (key, value)
                VALUES ($1, $2)
                ON CONFLICT (key) DO UPDATE SET value = $2
                """,
                key,
                value,
            )

    async def _delete_config_value(self, key: str) -> None:
        """Delete a config value from the tenant config table."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM config WHERE key = $1",
                key,
            )

    # Tasks sync cursor
    async def get_tasks_synced_until(self) -> datetime | None:
        """Get the tasks sync cursor (last synced timestamp)."""
        value = await self._get_config_value(TEAMWORK_TASKS_SYNCED_UNTIL_KEY)
        if value:
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                logger.warning(f"Invalid timestamp in {TEAMWORK_TASKS_SYNCED_UNTIL_KEY}: {value}")
        return None

    async def set_tasks_synced_until(self, timestamp: datetime) -> None:
        """Set the tasks sync cursor."""
        await self._set_config_value(
            TEAMWORK_TASKS_SYNCED_UNTIL_KEY,
            timestamp.isoformat(),
        )

    async def clear_tasks_synced_until(self) -> None:
        """Clear the tasks sync cursor."""
        await self._delete_config_value(TEAMWORK_TASKS_SYNCED_UNTIL_KEY)

    # Tasks pagination cursor
    async def get_tasks_cursor(self) -> int | None:
        """Get the current pagination cursor for tasks."""
        value = await self._get_config_value(TEAMWORK_TASKS_CURSOR_KEY)
        if value:
            try:
                return int(value)
            except ValueError:
                logger.warning(f"Invalid cursor in {TEAMWORK_TASKS_CURSOR_KEY}: {value}")
        return None

    async def set_tasks_cursor(self, page: int) -> None:
        """Set the tasks pagination cursor."""
        await self._set_config_value(TEAMWORK_TASKS_CURSOR_KEY, str(page))

    async def clear_tasks_cursor(self) -> None:
        """Clear the tasks pagination cursor."""
        await self._delete_config_value(TEAMWORK_TASKS_CURSOR_KEY)

    # Full backfill complete flag
    async def is_full_backfill_complete(self) -> bool:
        """Check if full backfill is complete."""
        value = await self._get_config_value(TEAMWORK_FULL_BACKFILL_COMPLETE_KEY)
        return value == "true"

    async def set_full_backfill_complete(self, complete: bool) -> None:
        """Set the full backfill complete flag."""
        await self._set_config_value(
            TEAMWORK_FULL_BACKFILL_COMPLETE_KEY,
            "true" if complete else "false",
        )

    async def clear_full_backfill_complete(self) -> None:
        """Clear the full backfill complete flag."""
        await self._delete_config_value(TEAMWORK_FULL_BACKFILL_COMPLETE_KEY)

    # Reset all sync state (for reconnecting)
    async def reset_all_sync_state(self) -> None:
        """Reset all sync state when reconnecting."""
        await self.clear_tasks_synced_until()
        await self.clear_tasks_cursor()
        await self.clear_full_backfill_complete()
        logger.info(
            "Reset all Teamwork sync state",
            tenant_id=self.tenant_id,
        )
