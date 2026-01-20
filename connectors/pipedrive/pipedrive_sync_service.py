"""Pipedrive sync service for managing backfill state.

Handles cursor persistence for incremental syncs and backfill progress tracking.
"""

from datetime import UTC, datetime
from typing import Any

from connectors.pipedrive.pipedrive_models import (
    PIPEDRIVE_DEALS_CURSOR_KEY,
    PIPEDRIVE_DEALS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_FULL_BACKFILL_COMPLETE_KEY,
    PIPEDRIVE_ORGS_CURSOR_KEY,
    PIPEDRIVE_ORGS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_PERSONS_CURSOR_KEY,
    PIPEDRIVE_PERSONS_SYNCED_UNTIL_KEY,
    PIPEDRIVE_PRODUCTS_CURSOR_KEY,
    PIPEDRIVE_PRODUCTS_SYNCED_UNTIL_KEY,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class PipedriveSyncService:
    """Manages Pipedrive sync state in the tenant config table."""

    def __init__(self, db_client: Any, tenant_id: str):
        """Initialize the sync service.

        Args:
            db_client: Database client for the tenant
            tenant_id: Tenant ID for logging
        """
        self.db_client = db_client
        self.tenant_id = tenant_id

    # =========================================================================
    # Sync cursor management (for incremental backfills)
    # =========================================================================

    async def get_deals_synced_until(self) -> datetime | None:
        """Get the last sync timestamp for deals."""
        return await self._get_timestamp(PIPEDRIVE_DEALS_SYNCED_UNTIL_KEY)

    async def set_deals_synced_until(self, timestamp: datetime) -> None:
        """Set the last sync timestamp for deals."""
        await self._set_timestamp(PIPEDRIVE_DEALS_SYNCED_UNTIL_KEY, timestamp)

    async def get_persons_synced_until(self) -> datetime | None:
        """Get the last sync timestamp for persons."""
        return await self._get_timestamp(PIPEDRIVE_PERSONS_SYNCED_UNTIL_KEY)

    async def set_persons_synced_until(self, timestamp: datetime) -> None:
        """Set the last sync timestamp for persons."""
        await self._set_timestamp(PIPEDRIVE_PERSONS_SYNCED_UNTIL_KEY, timestamp)

    async def get_orgs_synced_until(self) -> datetime | None:
        """Get the last sync timestamp for organizations."""
        return await self._get_timestamp(PIPEDRIVE_ORGS_SYNCED_UNTIL_KEY)

    async def set_orgs_synced_until(self, timestamp: datetime) -> None:
        """Set the last sync timestamp for organizations."""
        await self._set_timestamp(PIPEDRIVE_ORGS_SYNCED_UNTIL_KEY, timestamp)

    async def get_products_synced_until(self) -> datetime | None:
        """Get the last sync timestamp for products."""
        return await self._get_timestamp(PIPEDRIVE_PRODUCTS_SYNCED_UNTIL_KEY)

    async def set_products_synced_until(self, timestamp: datetime) -> None:
        """Set the last sync timestamp for products."""
        await self._set_timestamp(PIPEDRIVE_PRODUCTS_SYNCED_UNTIL_KEY, timestamp)

    # =========================================================================
    # Pagination cursor management (for resumable full backfills)
    # =========================================================================

    async def get_deals_cursor(self) -> str | None:
        """Get the pagination cursor for deals backfill."""
        return await self._get_string(PIPEDRIVE_DEALS_CURSOR_KEY)

    async def set_deals_cursor(self, cursor: str | None) -> None:
        """Set the pagination cursor for deals backfill."""
        await self._set_string(PIPEDRIVE_DEALS_CURSOR_KEY, cursor)

    async def clear_deals_cursor(self) -> None:
        """Clear the pagination cursor for deals."""
        await self._delete_key(PIPEDRIVE_DEALS_CURSOR_KEY)

    async def get_persons_cursor(self) -> str | None:
        """Get the pagination cursor for persons backfill."""
        return await self._get_string(PIPEDRIVE_PERSONS_CURSOR_KEY)

    async def set_persons_cursor(self, cursor: str | None) -> None:
        """Set the pagination cursor for persons backfill."""
        await self._set_string(PIPEDRIVE_PERSONS_CURSOR_KEY, cursor)

    async def clear_persons_cursor(self) -> None:
        """Clear the pagination cursor for persons."""
        await self._delete_key(PIPEDRIVE_PERSONS_CURSOR_KEY)

    async def get_orgs_cursor(self) -> str | None:
        """Get the pagination cursor for organizations backfill."""
        return await self._get_string(PIPEDRIVE_ORGS_CURSOR_KEY)

    async def set_orgs_cursor(self, cursor: str | None) -> None:
        """Set the pagination cursor for organizations backfill."""
        await self._set_string(PIPEDRIVE_ORGS_CURSOR_KEY, cursor)

    async def clear_orgs_cursor(self) -> None:
        """Clear the pagination cursor for organizations."""
        await self._delete_key(PIPEDRIVE_ORGS_CURSOR_KEY)

    async def get_products_cursor(self) -> str | None:
        """Get the pagination cursor for products backfill."""
        return await self._get_string(PIPEDRIVE_PRODUCTS_CURSOR_KEY)

    async def set_products_cursor(self, cursor: str | None) -> None:
        """Set the pagination cursor for products backfill."""
        await self._set_string(PIPEDRIVE_PRODUCTS_CURSOR_KEY, cursor)

    async def clear_products_cursor(self) -> None:
        """Clear the pagination cursor for products."""
        await self._delete_key(PIPEDRIVE_PRODUCTS_CURSOR_KEY)

    # =========================================================================
    # Full backfill completion tracking
    # =========================================================================

    async def is_full_backfill_complete(self) -> bool:
        """Check if full backfill has been completed."""
        value = await self._get_string(PIPEDRIVE_FULL_BACKFILL_COMPLETE_KEY)
        return value == "true"

    async def set_full_backfill_complete(self, complete: bool = True) -> None:
        """Mark full backfill as complete or incomplete."""
        await self._set_string(
            PIPEDRIVE_FULL_BACKFILL_COMPLETE_KEY, "true" if complete else "false"
        )

    async def reset_backfill_state(self) -> None:
        """Reset all backfill state for a fresh sync.

        Called when reconnecting Pipedrive to start fresh.
        """
        keys_to_clear = [
            PIPEDRIVE_DEALS_SYNCED_UNTIL_KEY,
            PIPEDRIVE_PERSONS_SYNCED_UNTIL_KEY,
            PIPEDRIVE_ORGS_SYNCED_UNTIL_KEY,
            PIPEDRIVE_PRODUCTS_SYNCED_UNTIL_KEY,
            PIPEDRIVE_FULL_BACKFILL_COMPLETE_KEY,
            PIPEDRIVE_DEALS_CURSOR_KEY,
            PIPEDRIVE_PERSONS_CURSOR_KEY,
            PIPEDRIVE_ORGS_CURSOR_KEY,
            PIPEDRIVE_PRODUCTS_CURSOR_KEY,
        ]
        for key in keys_to_clear:
            await self._delete_key(key)

        logger.info(
            "Reset Pipedrive backfill state",
            tenant_id=self.tenant_id,
        )

    # =========================================================================
    # Private helper methods
    # =========================================================================

    async def _get_string(self, key: str) -> str | None:
        """Get a string value from config."""
        query = "SELECT value FROM config WHERE key = $1"
        result = await self.db_client.fetchrow(query, key)
        if result:
            return result["value"]
        return None

    async def _set_string(self, key: str, value: str | None) -> None:
        """Set a string value in config."""
        if value is None:
            await self._delete_key(key)
            return

        query = """
            INSERT INTO config (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = $2, updated_at = CURRENT_TIMESTAMP
        """
        await self.db_client.execute(query, key, value)

    async def _get_timestamp(self, key: str) -> datetime | None:
        """Get a timestamp value from config."""
        value = await self._get_string(key)
        if value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                return None
        return None

    async def _set_timestamp(self, key: str, timestamp: datetime) -> None:
        """Set a timestamp value in config."""
        # Ensure timezone awareness
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        value = timestamp.isoformat()
        await self._set_string(key, value)

    async def _delete_key(self, key: str) -> None:
        """Delete a key from config."""
        query = "DELETE FROM config WHERE key = $1"
        await self.db_client.execute(query, key)
