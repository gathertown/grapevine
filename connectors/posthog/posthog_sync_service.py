"""PostHog sync service for managing backfill state and sync cursors."""

import json
from datetime import datetime
from typing import Any

import asyncpg

from src.database.connector_installations import (
    ConnectorInstallationsRepository,
    ConnectorType,
)
from src.utils.tenant_config import (
    delete_config_value_with_pool,
    get_config_value_with_pool,
    set_config_value_with_pool,
)

# Config keys
POSTHOG_FULL_BACKFILL_COMPLETE_KEY = "POSTHOG_FULL_BACKFILL_COMPLETE"
POSTHOG_LAST_SYNCED_AT_KEY = "POSTHOG_LAST_SYNCED_AT"


def _parse_external_metadata(metadata: Any) -> dict[str, Any]:
    """Parse external_metadata, handling string/dict formats.

    Sometimes external_metadata comes back as a JSON string instead of a dict,
    depending on how it was stored and which database driver is used.
    """
    if metadata is None:
        return {}
    if isinstance(metadata, dict):
        return metadata
    if isinstance(metadata, str):
        try:
            parsed = json.loads(metadata)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


class PostHogSyncService:
    """Service for managing PostHog sync state and cursors."""

    def __init__(self, db_pool: asyncpg.Pool, tenant_id: str):
        self.db_pool = db_pool
        self.tenant_id = tenant_id
        self._connector_repo = ConnectorInstallationsRepository()

    # Full backfill complete flag
    async def is_full_backfill_complete(self) -> bool:
        """Check if full backfill has completed."""
        value = await get_config_value_with_pool(POSTHOG_FULL_BACKFILL_COMPLETE_KEY, self.db_pool)
        return value == "true"

    async def set_full_backfill_complete(self, complete: bool = True) -> None:
        """Set the full backfill complete flag."""
        await set_config_value_with_pool(
            POSTHOG_FULL_BACKFILL_COMPLETE_KEY,
            "true" if complete else "false",
            self.db_pool,
        )

    async def clear_full_backfill_complete(self) -> None:
        """Clear the full backfill complete flag."""
        await delete_config_value_with_pool(POSTHOG_FULL_BACKFILL_COMPLETE_KEY, self.db_pool)

    # Last synced timestamp
    async def get_last_synced_at(self) -> datetime | None:
        """Get the timestamp of the last successful sync."""
        value = await get_config_value_with_pool(POSTHOG_LAST_SYNCED_AT_KEY, self.db_pool)
        if value:
            return datetime.fromisoformat(value)
        return None

    async def set_last_synced_at(self, timestamp: datetime) -> None:
        """Set the timestamp of the last successful sync."""
        await set_config_value_with_pool(
            POSTHOG_LAST_SYNCED_AT_KEY,
            timestamp.isoformat(),
            self.db_pool,
        )

    async def clear_last_synced_at(self) -> None:
        """Clear the last synced timestamp."""
        await delete_config_value_with_pool(POSTHOG_LAST_SYNCED_AT_KEY, self.db_pool)

    # Selected project IDs (stored in connector_installations.external_metadata)
    async def get_selected_project_ids(self) -> list[int]:
        """Get the list of selected project IDs from connector_installations.external_metadata."""
        connector = await self._connector_repo.get_by_tenant_and_type(
            self.tenant_id, ConnectorType.POSTHOG
        )
        if connector:
            metadata = _parse_external_metadata(connector.external_metadata)
            project_ids = metadata.get("selected_project_ids", [])
            if isinstance(project_ids, list):
                return [int(pid) for pid in project_ids if pid]
        return []

    # Synced project IDs (stored in connector_installations.external_metadata)
    async def get_synced_project_ids(self) -> list[int]:
        """Get the list of already synced project IDs from connector_installations.external_metadata."""
        connector = await self._connector_repo.get_by_tenant_and_type(
            self.tenant_id, ConnectorType.POSTHOG
        )
        if connector:
            metadata = _parse_external_metadata(connector.external_metadata)
            project_ids = metadata.get("synced_project_ids", [])
            if isinstance(project_ids, list):
                return [int(pid) for pid in project_ids if pid]
        return []

    async def add_synced_project_ids(self, project_ids: list[int]) -> None:
        """Add project IDs to the list of synced projects in connector_installations.external_metadata.

        This merges the provided project IDs with existing synced_project_ids (deduped).
        """
        connector = await self._connector_repo.get_by_tenant_and_type(
            self.tenant_id, ConnectorType.POSTHOG
        )
        if not connector:
            return

        existing_synced = set(await self.get_synced_project_ids())
        updated_synced = list(existing_synced | set(project_ids))

        existing_metadata = _parse_external_metadata(connector.external_metadata)
        updated_metadata = {
            **existing_metadata,
            "synced_project_ids": updated_synced,
        }

        await self._connector_repo.update_metadata(connector.id, updated_metadata)

    async def clear_all_sync_state(self) -> None:
        """Clear all sync state for a fresh backfill."""
        await self.clear_full_backfill_complete()
        await self.clear_last_synced_at()
