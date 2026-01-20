"""Monday.com sync service for tracking backfill progress."""

from datetime import datetime

import asyncpg

_incr_items_synced_until = "MONDAY_INCR_BACKFILL_ITEMS_SYNCED_UNTIL"


class MondaySyncService:
    """Service to track Monday.com sync progress in the database."""

    pool: asyncpg.Pool

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_incr_items_synced_until(self) -> datetime | None:
        """Get the timestamp we've synced items until during incremental backfill."""
        return await self._get_datetime(_incr_items_synced_until)

    async def set_incr_items_synced_until(self, synced_until: datetime | None) -> None:
        """Set the timestamp we've synced items until during incremental backfill."""
        return await self._set_datetime(_incr_items_synced_until, synced_until)

    async def _get_datetime(self, key: str) -> datetime | None:
        value = await self._get_str(key)
        return datetime.fromisoformat(value) if value else None

    async def _set_datetime(self, key: str, value: datetime | None) -> None:
        str_value = value.astimezone().isoformat() if value else None
        return await self._set_str(key, str_value)

    async def _get_str(self, key: str) -> str | None:
        async with self.pool.acquire() as conn:
            config_row = await conn.fetchrow(
                "SELECT value FROM config WHERE key = $1",
                key,
            )

        if not config_row:
            return None

        return config_row["value"]

    async def _set_str(self, key: str, value: str | None) -> None:
        if value is None:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM config WHERE key = $1",
                    key,
                )
        else:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO config (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2",
                    key,
                    value,
                )
