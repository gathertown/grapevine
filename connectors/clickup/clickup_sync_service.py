from datetime import datetime

import asyncpg


# Track how far we've backfilled as it marches backwards in time
def _get_full_tasks_synced_after_key(workspace_id: str) -> str:
    return f"CLICKUP_FULL_BACKFILL_TASKS_SYNCED_AFTER_workspace:{workspace_id}"


# Track how far we've incrementally backfilled as it marches forwards in time
def _get_incr_tasks_synced_until_key(workspace_id: str) -> str:
    return f"CLICKUP_INCR_BACKFILL_TASKS_SYNCED_UNTIL_workspace:{workspace_id}"


_full_tasks_complete_key = "CLICKUP_FULL_BACKFILL_TASKS_COMPLETE"
_permissions_latest_sync_completion = "CLICKUP_PERMISSIONS_LATEST_SYNC_COMPLETION"


class ClickupSyncService:
    pool: asyncpg.Pool

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_full_tasks_synced_after(self, workspace_id: str) -> datetime | None:
        return await self._get_datetime(_get_full_tasks_synced_after_key(workspace_id))

    async def set_full_tasks_synced_after(
        self, workspace_id: str, synced_after: datetime | None
    ) -> None:
        return await self._set_datetime(
            _get_full_tasks_synced_after_key(workspace_id), synced_after
        )

    async def get_full_tasks_backfill_complete(self) -> bool:
        return await self._get_bool(_full_tasks_complete_key) or False

    async def set_full_tasks_backfill_complete(self, complete: bool) -> None:
        return await self._set_bool(_full_tasks_complete_key, complete)

    async def get_incr_tasks_synced_until(self, workspace_id: str) -> datetime | None:
        return await self._get_datetime(_get_incr_tasks_synced_until_key(workspace_id))

    async def set_incr_tasks_synced_until(
        self, workspace_id: str, synced_until: datetime | None
    ) -> None:
        return await self._set_datetime(
            _get_incr_tasks_synced_until_key(workspace_id), synced_until
        )

    async def get_permissions_latest_sync_completion(self) -> datetime | None:
        return await self._get_datetime(_permissions_latest_sync_completion)

    async def set_permissions_latest_sync_completion(
        self, latest_sync_completion: datetime | None
    ) -> None:
        return await self._set_datetime(_permissions_latest_sync_completion, latest_sync_completion)

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
