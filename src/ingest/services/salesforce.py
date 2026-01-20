"""Salesforce service for managing tenant installations and sync state."""

from dataclasses import dataclass
from datetime import datetime

import asyncpg

from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SalesforceInstallation:
    """Represents a Salesforce installation for a tenant."""

    tenant_id: str
    org_id: str
    instance_url: str
    created_at: datetime
    updated_at: datetime


class SalesforceInstallationService:
    """Service for managing Salesforce installations."""

    async def get_installation(
        self, tenant_id: str, conn: asyncpg.Connection
    ) -> SalesforceInstallation | None:
        """Get the Salesforce installation for a given tenant."""
        # Get org_id and instance_url from tenant config table
        rows = await conn.fetch(
            "SELECT key, value FROM config WHERE key IN ($1, $2)",
            "SALESFORCE_ORG_ID",
            "SALESFORCE_INSTANCE_URL",
        )

        if not rows or len(rows) < 2:
            return None

        config = {row["key"]: row["value"] for row in rows}
        org_id = config.get("SALESFORCE_ORG_ID")
        instance_url = config.get("SALESFORCE_INSTANCE_URL")

        if not org_id or not instance_url:
            return None

        # Get created_at and updated_at from config table (if available)
        timestamp_row = await conn.fetchrow(
            "SELECT value FROM config WHERE key = $1",
            "SALESFORCE_CONNECTED_AT",
        )

        connected_at = datetime.fromisoformat(timestamp_row["value"]) if timestamp_row else None

        return SalesforceInstallation(
            tenant_id=tenant_id,
            org_id=org_id,
            instance_url=instance_url,
            created_at=connected_at or datetime.now(),
            updated_at=connected_at or datetime.now(),
        )

    async def get_all_installations(
        self, control_conn: asyncpg.Connection
    ) -> list[SalesforceInstallation]:
        """Get all Salesforce installations from control database."""
        # Query control database for tenants with Salesforce connected
        rows = await control_conn.fetch(
            "SELECT id FROM public.tenants WHERE has_salesforce_connected = true"
        )

        installations = []
        for row in rows:
            tenant_id = row["id"]
            try:
                # Get tenant database connection to fetch installation details
                from src.clients.tenant_db import tenant_db_manager

                async with (
                    tenant_db_manager.acquire_pool(tenant_id) as tenant_pool,
                    tenant_pool.acquire() as tenant_conn,
                ):
                    installation = await self.get_installation(tenant_id, tenant_conn)
                    if installation:
                        installations.append(installation)
            except Exception as e:
                logger.warning(f"Failed to get Salesforce installation for tenant {tenant_id}: {e}")
                continue

        return installations


class SalesforceObjectSyncService:
    """Service for tracking last sync timestamps for Salesforce objects."""

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
        return f"SALESFORCE_OBJECT_SYNC_LAST_SYNCED_AT_{object_type.upper()}"


# Singleton instances
salesforce_installation_service = SalesforceInstallationService()
salesforce_object_sync_service = SalesforceObjectSyncService()
