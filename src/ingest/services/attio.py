"""Attio sync service for managing incremental sync state."""

from datetime import UTC, datetime, timedelta

import asyncpg

from connectors.attio.attio_artifacts import ATTIO_OBJECT_TYPES, AttioObjectType
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Re-export for convenience
__all__ = ["ATTIO_OBJECT_TYPES", "AttioObjectType", "attio_object_sync_service"]

# Full sync interval - run a complete sync every 4 weeks
FULL_SYNC_INTERVAL_DAYS = 28


class AttioObjectSyncService:
    """Service for managing Attio object sync state via config table."""

    async def is_full_sync_due(self, object_type: AttioObjectType, db_pool: asyncpg.Pool) -> bool:
        """Check if a full sync is due for the given object type.

        A full sync is due if:
        - Never synced before, OR
        - Last sync was more than FULL_SYNC_INTERVAL_DAYS ago

        Args:
            object_type: The Attio object type (companies, people, deals)
            db_pool: Database connection pool

        Returns:
            True if full sync is due, False otherwise
        """
        last_synced_at = await self.get_object_last_synced_at(object_type, db_pool)

        if last_synced_at is None:
            logger.info(
                f"Attio {object_type.value} has never been synced - full sync due",
                object_type=object_type.value,
            )
            return True

        # Ensure last_synced_at is timezone-aware
        if last_synced_at.tzinfo is None:
            last_synced_at = last_synced_at.replace(tzinfo=UTC)

        time_since_last_sync = datetime.now(UTC) - last_synced_at
        sync_interval = timedelta(days=FULL_SYNC_INTERVAL_DAYS)

        if time_since_last_sync >= sync_interval:
            logger.info(
                f"Attio {object_type.value} last synced {time_since_last_sync.days} days ago - full sync due",
                object_type=object_type.value,
                last_synced_at=last_synced_at.isoformat(),
                days_since_sync=time_since_last_sync.days,
            )
            return True

        logger.info(
            f"Attio {object_type.value} last synced {time_since_last_sync.days} days ago - skipping",
            object_type=object_type.value,
            last_synced_at=last_synced_at.isoformat(),
            days_since_sync=time_since_last_sync.days,
            next_sync_in_days=(sync_interval - time_since_last_sync).days,
        )
        return False

    async def get_object_last_synced_at(
        self, object_type: AttioObjectType, db_pool: asyncpg.Pool
    ) -> datetime | None:
        """Get the last synced at timestamp for a given object type.

        Args:
            object_type: The Attio object type (companies, people, deals)
            db_pool: Database connection pool

        Returns:
            Last synced timestamp or None if never synced
        """
        async with db_pool.acquire() as conn:
            config_row = await conn.fetchrow(
                "SELECT value FROM config WHERE key = $1",
                self.get_key(object_type),
            )
            if not config_row:
                return None
            return datetime.fromisoformat(config_row["value"])

    async def set_object_last_synced_at(
        self, object_type: AttioObjectType, last_synced_at: datetime, db_pool: asyncpg.Pool
    ) -> None:
        """Set the last synced at timestamp for a given object type.

        Args:
            object_type: The Attio object type (companies, people, deals)
            last_synced_at: Timestamp to store
            db_pool: Database connection pool
        """
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO config (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2",
                self.get_key(object_type),
                last_synced_at.isoformat(),
            )
        logger.info(f"Updated Attio {object_type} last_synced_at to {last_synced_at.isoformat()}")

    def get_key(self, object_type: AttioObjectType) -> str:
        """Get the config key for a given object type.

        Args:
            object_type: The Attio object type

        Returns:
            Config key string
        """
        return f"ATTIO_OBJECT_SYNC_LAST_SYNCED_AT_{object_type.upper()}"


attio_object_sync_service = AttioObjectSyncService()
