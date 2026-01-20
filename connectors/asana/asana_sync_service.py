from datetime import datetime

import asyncpg


# Track how far we've backfilled as it marches backwards in time
def _get_full_tasks_synced_after_key(workspace_gid: str) -> str:
    return f"ASANA_FULL_BACKFILL_TASKS_SYNCED_AFTER_workspace:{workspace_gid}"


def _get_full_tasks_backfill_complete_key(workspace_gid: str) -> str:
    return f"ASANA_FULL_BACKFILL_TASKS_COMPLETE_workspace:{workspace_gid}"


def _get_incr_workspace_sync_token_key(workspace_gid: str) -> str:
    return f"ASANA_INCR_WORKSPACE_SYNC_TOKEN_workspace:{workspace_gid}"


def _get_incr_project_sync_token_key(project_gid: str) -> str:
    return f"ASANA_INCR_PROJECT_SYNC_TOKEN_project:{project_gid}"


class AsanaSyncService:
    pool: asyncpg.Pool

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_incr_workspace_sync_token(self, workspace_gid: str) -> str | None:
        return await self._get_str(_get_incr_workspace_sync_token_key(workspace_gid))

    async def set_incr_workspace_sync_token(
        self, workspace_gid: str, sync_token: str | None
    ) -> None:
        return await self._set_str(_get_incr_workspace_sync_token_key(workspace_gid), sync_token)

    async def get_incr_project_sync_token(self, project_gid: str) -> str | None:
        return await self._get_str(_get_incr_project_sync_token_key(project_gid))

    async def set_incr_project_sync_token(self, project_gid: str, sync_token: str | None) -> None:
        return await self._set_str(_get_incr_project_sync_token_key(project_gid), sync_token)

    async def get_full_tasks_synced_after(self, workspace_gid: str) -> datetime | None:
        return await self._get_datetime(_get_full_tasks_synced_after_key(workspace_gid))

    async def set_full_tasks_synced_after(
        self, workspace_gid: str, modified_at: datetime | None
    ) -> None:
        return await self._set_datetime(
            _get_full_tasks_synced_after_key(workspace_gid), modified_at
        )

    async def is_full_tasks_backfill_complete(self, workspace_gid: str) -> bool | None:
        return await self._get_bool(_get_full_tasks_backfill_complete_key(workspace_gid))

    async def set_full_tasks_backfill_complete(
        self, workspace_gid: str, complete: bool | None
    ) -> None:
        return await self._set_bool(_get_full_tasks_backfill_complete_key(workspace_gid), complete)

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
