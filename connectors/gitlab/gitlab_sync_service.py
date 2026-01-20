"""GitLab sync service for managing incremental backfill state."""

from datetime import datetime

import asyncpg

# Config keys for tracking sync progress (per-project to avoid race conditions)
_MR_SYNCED_UNTIL_PREFIX = "GITLAB_MR_SYNCED_UNTIL_"
_FILE_SYNCED_COMMIT_PREFIX = "GITLAB_FILE_SYNCED_COMMIT_"


class GitLabSyncService:
    """Service for managing GitLab incremental sync state in the config table."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    # ========== MR Sync State (per project) ==========

    def _get_mr_synced_until_key(self, project_id: int) -> str:
        """Get the config key for a project's last MR sync timestamp."""
        return f"{_MR_SYNCED_UNTIL_PREFIX}{project_id}"

    async def get_mr_synced_until(self, project_id: int) -> datetime | None:
        """Get the timestamp of the last MR sync for a project."""
        key = self._get_mr_synced_until_key(project_id)
        return await self._get_datetime(key)

    async def set_mr_synced_until(self, project_id: int, synced_until: datetime | None) -> None:
        """Set the timestamp of the last MR sync for a project."""
        key = self._get_mr_synced_until_key(project_id)
        await self._set_datetime(key, synced_until)

    async def clear_mr_synced_until(self, project_id: int) -> None:
        """Clear the MR sync state for a project."""
        key = self._get_mr_synced_until_key(project_id)
        await self._delete_key(key)

    async def clear_all_mr_synced_until(self) -> None:
        """Clear all MR sync state (for fresh backfill)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM config WHERE key LIKE $1",
                f"{_MR_SYNCED_UNTIL_PREFIX}%",
            )

    # ========== File Sync State (per project) ==========

    def _get_file_synced_commit_key(self, project_id: int) -> str:
        """Get the config key for a project's last synced commit."""
        return f"{_FILE_SYNCED_COMMIT_PREFIX}{project_id}"

    async def get_file_synced_commit(self, project_id: int) -> str | None:
        """Get the last synced commit SHA for a project."""
        key = self._get_file_synced_commit_key(project_id)
        return await self._get_str(key)

    async def set_file_synced_commit(self, project_id: int, commit_sha: str | None) -> None:
        """Set the last synced commit SHA for a project."""
        key = self._get_file_synced_commit_key(project_id)
        await self._set_str(key, commit_sha)

    async def clear_file_synced_commit(self, project_id: int) -> None:
        """Clear the file sync state for a project."""
        key = self._get_file_synced_commit_key(project_id)
        await self._delete_key(key)

    async def clear_all_file_synced_commits(self) -> None:
        """Clear all file sync state (for fresh backfill)."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM config WHERE key LIKE $1",
                f"{_FILE_SYNCED_COMMIT_PREFIX}%",
            )

    # ========== Helper Methods ==========

    async def _get_datetime(self, key: str) -> datetime | None:
        """Get a datetime value from config."""
        value = await self._get_str(key)
        return datetime.fromisoformat(value) if value else None

    async def _set_datetime(self, key: str, value: datetime | None) -> None:
        """Set a datetime value in config."""
        str_value = value.astimezone().isoformat() if value else None
        await self._set_str(key, str_value)

    async def _get_str(self, key: str) -> str | None:
        """Get a string value from config."""
        async with self.pool.acquire() as conn:
            config_row = await conn.fetchrow(
                "SELECT value FROM config WHERE key = $1",
                key,
            )

        if not config_row:
            return None

        return config_row["value"]

    async def _set_str(self, key: str, value: str | None) -> None:
        """Set a string value in config."""
        if value is None:
            await self._delete_key(key)
        else:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO config (key, value) VALUES ($1, $2) "
                    "ON CONFLICT (key) DO UPDATE SET value = $2",
                    key,
                    value,
                )

    async def _delete_key(self, key: str) -> None:
        """Delete a key from config."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM config WHERE key = $1",
                key,
            )
