"""Attio sync service for cursor and checkpoint persistence.

This service manages cursor positions for resumable backfills.
Cursors are stored in the tenant's config table and updated after each page
is processed, allowing jobs to resume from where they left off if interrupted.
"""

from datetime import datetime

import asyncpg

from src.utils.logging import get_logger

logger = get_logger(__name__)


def _get_backfill_cursor_key(object_slug: str) -> str:
    """Get config key for storing backfill cursor."""
    return f"ATTIO_BACKFILL_CURSOR_{object_slug}"


def _get_backfill_complete_key(object_slug: str) -> str:
    """Get config key for marking backfill as complete."""
    return f"ATTIO_BACKFILL_COMPLETE_{object_slug}"


def _get_last_sync_time_key(object_slug: str) -> str:
    """Get config key for storing last successful sync time."""
    return f"ATTIO_LAST_SYNC_TIME_{object_slug}"


class AttioSyncService:
    """Service for managing Attio sync state and cursors.

    Stores cursor positions in the tenant's config table to enable
    resumable backfills. If a backfill job is interrupted, it can
    resume from the last saved cursor position.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # Cursor management for resumable backfills
    async def get_backfill_cursor(self, object_slug: str) -> str | None:
        """Get the current cursor position for a backfill.

        Args:
            object_slug: The object type (e.g., "companies", "people", "deals")

        Returns:
            The cursor string if one exists, None otherwise
        """
        return await self._get_str(_get_backfill_cursor_key(object_slug))

    async def set_backfill_cursor(self, object_slug: str, cursor: str | None) -> None:
        """Save the current cursor position for a backfill.

        Called after each page is successfully processed to enable resume.

        Args:
            object_slug: The object type
            cursor: The cursor to save, or None to clear
        """
        await self._set_str(_get_backfill_cursor_key(object_slug), cursor)

    async def clear_backfill_cursor(self, object_slug: str) -> None:
        """Clear the cursor when backfill completes successfully."""
        await self._set_str(_get_backfill_cursor_key(object_slug), None)

    # Backfill completion tracking
    async def is_backfill_complete(self, object_slug: str) -> bool:
        """Check if initial backfill has completed for an object type."""
        value = await self._get_str(_get_backfill_complete_key(object_slug))
        return value == "true"

    async def set_backfill_complete(self, object_slug: str, complete: bool) -> None:
        """Mark backfill as complete or incomplete."""
        await self._set_str(
            _get_backfill_complete_key(object_slug), "true" if complete else "false"
        )

    # Last sync time for incremental updates
    async def get_last_sync_time(self, object_slug: str) -> datetime | None:
        """Get the last successful sync time for incremental updates."""
        return await self._get_datetime(_get_last_sync_time_key(object_slug))

    async def set_last_sync_time(self, object_slug: str, sync_time: datetime | None) -> None:
        """Set the last successful sync time."""
        await self._set_datetime(_get_last_sync_time_key(object_slug), sync_time)

    # Internal helpers
    async def _get_str(self, key: str) -> str | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM config WHERE key = $1", key)
        return row["value"] if row else None

    async def _set_str(self, key: str, value: str | None) -> None:
        async with self.pool.acquire() as conn:
            if value is None:
                await conn.execute("DELETE FROM config WHERE key = $1", key)
            else:
                await conn.execute(
                    "INSERT INTO config (key, value) VALUES ($1, $2) "
                    "ON CONFLICT (key) DO UPDATE SET value = $2",
                    key,
                    value,
                )

    async def _get_datetime(self, key: str) -> datetime | None:
        value = await self._get_str(key)
        return datetime.fromisoformat(value) if value else None

    async def _set_datetime(self, key: str, value: datetime | None) -> None:
        str_value = value.astimezone().isoformat() if value else None
        await self._set_str(key, str_value)
