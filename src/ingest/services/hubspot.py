from dataclasses import dataclass
from datetime import datetime

import asyncpg

from src.utils.logging import get_logger

logger = get_logger(__name__)

HUBSPOT_OBJECT_TYPES = [
    "company",
    "deal",
    "contact",
    "ticket",
]


@dataclass
class HubspotInstallation:
    portal_id: int
    tenant_id: str
    created_at: datetime
    updated_at: datetime


class HubspotInstallationService:
    """Service for managing HubSpot installations via connector_installations table."""

    async def get_installation(
        self, tenant_id: str, conn: asyncpg.Connection
    ) -> HubspotInstallation | None:
        """Get the HubSpot installation for a given tenant."""
        installation_row = await conn.fetchrow(
            """SELECT external_id, tenant_id, created_at, updated_at
               FROM connector_installations
               WHERE tenant_id = $1 AND type = 'hubspot' AND status != 'disconnected'""",
            tenant_id,
        )
        if not installation_row:
            return None
        return HubspotInstallation(
            portal_id=int(installation_row["external_id"]),
            tenant_id=installation_row["tenant_id"],
            created_at=installation_row["created_at"],
            updated_at=installation_row["updated_at"],
        )

    async def get_installation_by_portal_id(
        self, portal_id: int, conn: asyncpg.Connection
    ) -> HubspotInstallation | None:
        """Get the HubSpot installation for a given portal ID."""
        installation_row = await conn.fetchrow(
            """SELECT external_id, tenant_id, created_at, updated_at
               FROM connector_installations
               WHERE type = 'hubspot' AND external_id = $1 AND status != 'disconnected'""",
            str(portal_id),
        )
        if not installation_row:
            return None
        return HubspotInstallation(
            portal_id=int(installation_row["external_id"]),
            tenant_id=installation_row["tenant_id"],
            created_at=installation_row["created_at"],
            updated_at=installation_row["updated_at"],
        )

    async def get_all_installations(self, conn: asyncpg.Connection) -> list[HubspotInstallation]:
        """Get all active HubSpot installations."""
        installations_rows = await conn.fetch(
            """SELECT external_id, tenant_id, created_at, updated_at
               FROM connector_installations
               WHERE type = 'hubspot' AND status != 'disconnected'""",
        )
        return [
            HubspotInstallation(
                portal_id=int(row["external_id"]),
                tenant_id=row["tenant_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in installations_rows
        ]


hubspot_installation_service = HubspotInstallationService()


class HubspotObjectSyncService:
    async def get_object_last_synced_at(
        self, object_type: str, conn: asyncpg.Connection
    ) -> datetime | None:
        """Get the last synced at timestamp for a given object type."""
        config_row = await conn.fetchrow(
            "SELECT value FROM config WHERE key = $1",
            self.get_key(object_type),
        )
        if not config_row:
            return None
        return datetime.fromisoformat(config_row["value"])

    async def set_object_last_synced_at(
        self, object_type: str, last_synced_at: datetime, conn: asyncpg.Connection
    ) -> None:
        """Set the last synced at timestamp for a given object type."""
        await conn.execute(
            "INSERT INTO config (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2",
            self.get_key(object_type),
            last_synced_at.isoformat(),
        )

    def get_key(self, object_type: str) -> str:
        """Get the key for a given object type."""
        return f"HUBSPOT_OBJECT_SYNC_LAST_SYNCED_AT_{object_type.upper()}"


hubspot_object_sync_service = HubspotObjectSyncService()
