from datetime import datetime

import asyncpg

from connectors.zendesk.client.zendesk_models import DateWindow

# Incremental update cursors
_incremental_tickets_cursor_key = "ZENDESK_INCREMENTAL_BACKFILL_TICKETS_CURSOR"
_incremental_ticket_events_start_time_key = "ZENDESK_INCREMENTAL_BACKFILL_TICKET_EVENTS_START_TIME"
_incremental_articles_start_time_key = "ZENDESK_INCREMENTAL_BACKFILL_ARTICLES_START_TIME"

# Track how far we've backfilled as it marches backwards in time - update once per window
_synced_after_key = "ZENDESK_SYNCED_AFTER"


def _window_to_key(window: DateWindow) -> str:
    start_str = int(window.start.timestamp()) if window.start else "none"
    end_str = int(window.end.timestamp()) if window.end else "none"
    return f"{start_str}_{end_str}"


# Save mid-window progress
def _window_tickets_end_key(window: DateWindow) -> str:
    return f"ZENDESK_WINDOW_BACKFILL_TICKETS_END_TIME_{_window_to_key(window)}"


def _window_ticket_events_start_key(window: DateWindow) -> str:
    return f"ZENDESK_WINDOW_BACKFILL_TICKET_EVENTS_START_TIME_{_window_to_key(window)}"


def _window_articles_start_key(window: DateWindow) -> str:
    return f"ZENDESK_WINDOW_BACKFILL_ARTICLES_START_TIME_{_window_to_key(window)}"


class ZendeskSyncService:
    pool: asyncpg.Pool

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    async def get_synced_after(self) -> datetime | None:
        return await self._get_datetime(_synced_after_key)

    async def set_synced_after(self, synced_after: datetime | None) -> None:
        return await self._set_datetime(_synced_after_key, synced_after)

    async def get_window_tickets_end_time(self, window: DateWindow) -> datetime | None:
        return await self._get_datetime(_window_tickets_end_key(window))

    async def set_window_tickets_end_time(
        self, window: DateWindow, end_time: datetime | None
    ) -> None:
        return await self._set_datetime(_window_tickets_end_key(window), end_time)

    async def get_window_ticket_events_start_time(self, window: DateWindow) -> int | None:
        return await self._get_int(_window_ticket_events_start_key(window))

    async def set_window_ticket_events_start_time(
        self, window: DateWindow, start_time: int | None
    ) -> None:
        return await self._set_int(_window_ticket_events_start_key(window), start_time)

    async def get_window_articles_start_time(self, window: DateWindow) -> int | None:
        return await self._get_int(_window_articles_start_key(window))

    async def set_window_articles_start_time(
        self, window: DateWindow, start_time: int | None
    ) -> None:
        return await self._set_int(_window_articles_start_key(window), start_time)

    async def get_incremental_tickets_cursor(self) -> str | None:
        return await self._get_str(_incremental_tickets_cursor_key)

    async def set_incremental_tickets_cursor(self, incremental_cursor: str) -> None:
        return await self._set_str(_incremental_tickets_cursor_key, incremental_cursor)

    async def get_incremental_ticket_events_start_time(self) -> int | None:
        return await self._get_int(_incremental_ticket_events_start_time_key)

    async def set_incremental_ticket_events_start_time(self, start_time: int) -> None:
        return await self._set_int(_incremental_ticket_events_start_time_key, start_time)

    async def get_incremental_articles_start_time(self) -> int | None:
        return await self._get_int(_incremental_articles_start_time_key)

    async def set_incremental_articles_start_time(self, start_time: int) -> None:
        return await self._set_int(_incremental_articles_start_time_key, start_time)

    async def _get_datetime(self, key: str) -> datetime | None:
        value = await self._get_str(key)
        return datetime.fromisoformat(value) if value else None

    async def _set_datetime(self, key: str, value: datetime | None) -> None:
        str_value = value.astimezone().isoformat() if value else None
        return await self._set_str(key, str_value)

    async def _get_int(self, key: str) -> int | None:
        value = await self._get_str(key)
        return int(value) if value else None

    async def _set_int(self, key: str, value: int | None) -> None:
        return await self._set_str(key, str(value) if value is not None else None)

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
