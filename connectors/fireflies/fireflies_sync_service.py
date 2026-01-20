from datetime import datetime

import asyncpg

_full_transcripts_synced_after_key = "FIREFLIES_FULL_BACKFILL_TRANSCRIPTS_SYNCED_AFTER"
_full_transcripts_complete_key = "FIREFLIES_FULL_BACKFILL_TRANSCRIPTS_COMPLETE"
_incr_transcripts_synced_until = "FIREFLIES_INCR_BACKFILL_TRANSCRIPTS_SYNCED_UNTIL"


class FirefliesSyncService:
    pool: asyncpg.Pool

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_full_transcripts_synced_after(self) -> datetime | None:
        return await self._get_datetime(_full_transcripts_synced_after_key)

    async def set_full_transcripts_synced_after(self, synced_after: datetime | None) -> None:
        return await self._set_datetime(_full_transcripts_synced_after_key, synced_after)

    async def get_full_transcripts_backfill_complete(self) -> bool:
        return await self._get_bool(_full_transcripts_complete_key) or False

    async def set_full_transcripts_backfill_complete(self, complete: bool) -> None:
        return await self._set_bool(_full_transcripts_complete_key, complete)

    async def get_incr_transcripts_synced_until(self) -> datetime | None:
        return await self._get_datetime(_incr_transcripts_synced_until)

    async def set_incr_transcripts_synced_until(self, synced_until: datetime | None) -> None:
        return await self._set_datetime(_incr_transcripts_synced_until, synced_until)

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
