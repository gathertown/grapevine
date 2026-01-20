"""
Canva sync service for managing backfill state.
"""

from datetime import datetime

import asyncpg

from connectors.canva.canva_models import (
    CANVA_DESIGNS_SYNCED_UNTIL_KEY,
    CANVA_FULL_BACKFILL_COMPLETE_KEY,
)
from src.utils.logging import get_logger
from src.utils.tenant_config import get_config_value_with_pool, set_config_value_with_pool

logger = get_logger(__name__)


class CanvaSyncService:
    """Service for managing Canva sync state."""

    def __init__(self, db_pool: asyncpg.Pool, tenant_id: str):
        self.db_pool = db_pool
        self.tenant_id = tenant_id

    # =============================================================================
    # Designs Sync State
    # =============================================================================

    async def get_designs_synced_until(self) -> datetime | None:
        """Get the timestamp until which designs have been synced."""
        value = await get_config_value_with_pool(CANVA_DESIGNS_SYNCED_UNTIL_KEY, self.db_pool)
        if value:
            try:
                return datetime.fromisoformat(str(value))
            except (ValueError, TypeError):
                return None
        return None

    async def set_designs_synced_until(self, timestamp: datetime) -> None:
        """Set the timestamp until which designs have been synced."""
        await set_config_value_with_pool(
            CANVA_DESIGNS_SYNCED_UNTIL_KEY,
            timestamp.isoformat(),
            self.db_pool,
        )

    # =============================================================================
    # Full Backfill State
    # =============================================================================

    async def is_full_backfill_complete(self) -> bool:
        """Check if full backfill has been completed."""
        value = await get_config_value_with_pool(CANVA_FULL_BACKFILL_COMPLETE_KEY, self.db_pool)
        return str(value).lower() == "true" if value else False

    async def set_full_backfill_complete(self, complete: bool = True) -> None:
        """Set the full backfill complete flag."""
        await set_config_value_with_pool(
            CANVA_FULL_BACKFILL_COMPLETE_KEY,
            str(complete).lower(),
            self.db_pool,
        )

    # =============================================================================
    # Utility Methods
    # =============================================================================

    async def clear_sync_state(self) -> None:
        """Clear all sync state (used when reconnecting)."""
        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM config
                WHERE key IN ($1, $2)
                """,
                CANVA_DESIGNS_SYNCED_UNTIL_KEY,
                CANVA_FULL_BACKFILL_COMPLETE_KEY,
            )
        logger.info("Cleared Canva sync state", tenant_id=self.tenant_id)
