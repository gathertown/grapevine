"""Pylon sync service for tracking backfill progress."""

from datetime import datetime

import asyncpg

_full_issues_synced_after_key = "PYLON_FULL_BACKFILL_ISSUES_SYNCED_AFTER"
_full_issues_complete_key = "PYLON_FULL_BACKFILL_ISSUES_COMPLETE"
_full_issues_cursor_key = "PYLON_FULL_BACKFILL_ISSUES_CURSOR"
_incr_issues_synced_until = "PYLON_INCR_BACKFILL_ISSUES_SYNCED_UNTIL"
_reference_data_synced_at_key = "PYLON_REFERENCE_DATA_SYNCED_AT"


class PylonSyncService:
    """Service to track Pylon sync progress in the database."""

    pool: asyncpg.Pool

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_full_issues_synced_after(self) -> datetime | None:
        """Get the timestamp we've synced issues after during full backfill."""
        return await self._get_datetime(_full_issues_synced_after_key)

    async def set_full_issues_synced_after(self, synced_after: datetime | None) -> None:
        """Set the timestamp we've synced issues after during full backfill."""
        return await self._set_datetime(_full_issues_synced_after_key, synced_after)

    async def get_full_issues_backfill_complete(self) -> bool:
        """Check if full issue backfill is complete."""
        return await self._get_bool(_full_issues_complete_key) or False

    async def set_full_issues_backfill_complete(self, complete: bool) -> None:
        """Mark full issue backfill as complete or incomplete."""
        return await self._set_bool(_full_issues_complete_key, complete)

    async def get_full_issues_cursor(self) -> str | None:
        """Get the pagination cursor for the current time window during full backfill."""
        return await self._get_str(_full_issues_cursor_key)

    async def set_full_issues_cursor(self, cursor: str | None) -> None:
        """Set the pagination cursor for the current time window during full backfill."""
        return await self._set_str(_full_issues_cursor_key, cursor)

    async def get_incr_issues_synced_until(self) -> datetime | None:
        """Get the timestamp we've synced issues until during incremental backfill."""
        return await self._get_datetime(_incr_issues_synced_until)

    async def set_incr_issues_synced_until(self, synced_until: datetime | None) -> None:
        """Set the timestamp we've synced issues until during incremental backfill."""
        return await self._set_datetime(_incr_issues_synced_until, synced_until)

    async def get_reference_data_synced_at(self) -> datetime | None:
        """Get the timestamp when reference data (users, accounts, teams) was last synced."""
        return await self._get_datetime(_reference_data_synced_at_key)

    async def set_reference_data_synced_at(self, synced_at: datetime | None) -> None:
        """Set the timestamp when reference data (users, accounts, teams) was synced."""
        return await self._set_datetime(_reference_data_synced_at_key, synced_at)

    async def _get_datetime(self, key: str) -> datetime | None:
        value = await self._get_str(key)
        return datetime.fromisoformat(value) if value else None

    async def _set_datetime(self, key: str, value: datetime | None) -> None:
        str_value = value.astimezone().isoformat() if value else None
        return await self._set_str(key, str_value)

    async def _get_bool(self, key: str) -> bool | None:
        value = await self._get_str(key)
        if value is None:
            return None
        return value.lower() == "true"

    async def _set_bool(self, key: str, value: bool | None) -> None:
        str_value: str | None = None
        match value:
            case True:
                str_value = "true"
            case False:
                str_value = "false"
            case None:
                str_value = None

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
