"""Figma sync service for managing backfill state and sync cursors."""

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
FIGMA_FULL_BACKFILL_COMPLETE_KEY = "FIGMA_FULL_BACKFILL_COMPLETE"
FIGMA_FILES_SYNCED_UNTIL_KEY = "FIGMA_FILES_SYNCED_UNTIL"
FIGMA_COMMENTS_SYNCED_UNTIL_KEY = "FIGMA_COMMENTS_SYNCED_UNTIL"


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


class FigmaSyncService:
    """Service for managing Figma sync state and cursors."""

    def __init__(self, db_pool: asyncpg.Pool, tenant_id: str):
        self.db_pool = db_pool
        self.tenant_id = tenant_id
        self._connector_repo = ConnectorInstallationsRepository()

    # Full backfill complete flag
    async def is_full_backfill_complete(self) -> bool:
        """Check if full backfill has completed."""
        value = await get_config_value_with_pool(FIGMA_FULL_BACKFILL_COMPLETE_KEY, self.db_pool)
        return value == "true"

    async def set_full_backfill_complete(self, complete: bool = True) -> None:
        """Set the full backfill complete flag."""
        await set_config_value_with_pool(
            FIGMA_FULL_BACKFILL_COMPLETE_KEY,
            "true" if complete else "false",
            self.db_pool,
        )

    async def clear_full_backfill_complete(self) -> None:
        """Clear the full backfill complete flag."""
        await delete_config_value_with_pool(FIGMA_FULL_BACKFILL_COMPLETE_KEY, self.db_pool)

    # Files sync cursor
    async def get_files_synced_until(self) -> datetime | None:
        """Get the timestamp until which files have been synced."""
        value = await get_config_value_with_pool(FIGMA_FILES_SYNCED_UNTIL_KEY, self.db_pool)
        if value:
            return datetime.fromisoformat(value)
        return None

    async def set_files_synced_until(self, timestamp: datetime) -> None:
        """Set the timestamp until which files have been synced."""
        await set_config_value_with_pool(
            FIGMA_FILES_SYNCED_UNTIL_KEY,
            timestamp.isoformat(),
            self.db_pool,
        )

    async def clear_files_synced_until(self) -> None:
        """Clear the files sync cursor."""
        await delete_config_value_with_pool(FIGMA_FILES_SYNCED_UNTIL_KEY, self.db_pool)

    # Comments sync cursor
    async def get_comments_synced_until(self) -> datetime | None:
        """Get the timestamp until which comments have been synced."""
        value = await get_config_value_with_pool(FIGMA_COMMENTS_SYNCED_UNTIL_KEY, self.db_pool)
        if value:
            return datetime.fromisoformat(value)
        return None

    async def set_comments_synced_until(self, timestamp: datetime) -> None:
        """Set the timestamp until which comments have been synced."""
        await set_config_value_with_pool(
            FIGMA_COMMENTS_SYNCED_UNTIL_KEY,
            timestamp.isoformat(),
            self.db_pool,
        )

    async def clear_comments_synced_until(self) -> None:
        """Clear the comments sync cursor."""
        await delete_config_value_with_pool(FIGMA_COMMENTS_SYNCED_UNTIL_KEY, self.db_pool)

    # Selected team IDs (stored in connector_installations.external_metadata)
    async def get_selected_team_ids(self) -> list[str]:
        """Get the list of selected team IDs from connector_installations.external_metadata."""
        connector = await self._connector_repo.get_by_tenant_and_type(
            self.tenant_id, ConnectorType.FIGMA
        )
        if connector:
            metadata = _parse_external_metadata(connector.external_metadata)
            team_ids = metadata.get("selected_team_ids", [])
            if isinstance(team_ids, list):
                return [str(tid) for tid in team_ids if tid]
        return []

    # Synced team IDs (stored in connector_installations.external_metadata)
    async def get_synced_team_ids(self) -> list[str]:
        """Get the list of already synced team IDs from connector_installations.external_metadata."""
        connector = await self._connector_repo.get_by_tenant_and_type(
            self.tenant_id, ConnectorType.FIGMA
        )
        if connector:
            metadata = _parse_external_metadata(connector.external_metadata)
            team_ids = metadata.get("synced_team_ids", [])
            if isinstance(team_ids, list):
                return [str(tid) for tid in team_ids if tid]
        return []

    async def add_synced_team_ids(self, team_ids: list[str]) -> None:
        """Add team IDs to the list of synced teams in connector_installations.external_metadata.

        This merges the provided team IDs with existing synced_team_ids (deduped).
        """
        connector = await self._connector_repo.get_by_tenant_and_type(
            self.tenant_id, ConnectorType.FIGMA
        )
        if not connector:
            return

        existing_synced = set(await self.get_synced_team_ids())
        updated_synced = list(existing_synced | set(team_ids))

        existing_metadata = _parse_external_metadata(connector.external_metadata)
        updated_metadata = {
            **existing_metadata,
            "synced_team_ids": updated_synced,
        }

        await self._connector_repo.update_metadata(connector.id, updated_metadata)

    async def clear_all_sync_state(self) -> None:
        """Clear all sync state for a fresh backfill."""
        await self.clear_full_backfill_complete()
        await self.clear_files_synced_until()
        await self.clear_comments_synced_until()
