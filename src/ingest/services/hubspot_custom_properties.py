import json
from dataclasses import asdict

import asyncpg

from src.clients.hubspot.hubspot_client import HubSpotClient, HubSpotProperty
from src.utils.logging import get_logger

logger = get_logger(__name__)

HUBSPOT_OBJECT_TYPES = [
    "company",
    "deal",
    "contact",
    "ticket",
]


class HubspotCustomProperties:
    async def get_all(self, conn: asyncpg.Connection) -> dict[str, list[HubSpotProperty]]:
        """Get all custom properties."""
        custom_properties: dict[str, list[HubSpotProperty]] = {}
        for object_type in HUBSPOT_OBJECT_TYPES:
            custom_properties[object_type] = await self.get_by_object_type(object_type, conn)
        return custom_properties

    async def load_all(self, client: HubSpotClient, conn: asyncpg.Connection) -> None:
        """Refresh all custom properties."""
        for object_type in HUBSPOT_OBJECT_TYPES:
            await self.load_by_object_type(object_type, client, conn)

    async def load_by_object_type(
        self, object_type: str, client: HubSpotClient, conn: asyncpg.Connection
    ) -> None:
        """Refresh custom properties for a given object type."""

        if object_type not in HUBSPOT_OBJECT_TYPES:
            logger.warning(f"Object type {object_type} not in HUBSPOT_OBJECT_TYPES")
            return

        custom_properties = await client.get_custom_properties(object_type)
        await self.set_by_object_type(object_type, custom_properties, conn)

    async def get_by_object_type(
        self, object_type: str, conn: asyncpg.Connection
    ) -> list[HubSpotProperty]:
        """Get custom properties for a given object type."""

        if object_type not in HUBSPOT_OBJECT_TYPES:
            logger.warning(f"Object type {object_type} not in HUBSPOT_OBJECT_TYPES")
            return []

        config_row = await conn.fetchrow(
            "SELECT value FROM config WHERE key = $1",
            self.get_key(object_type),
        )
        if not config_row:
            return []
        results = json.loads(config_row["value"])
        return [HubSpotProperty(**r) for r in results]

    async def set_by_object_type(
        self, object_type: str, properties: list[HubSpotProperty], conn: asyncpg.Connection
    ) -> None:
        """Set custom properties for a given object type."""
        if object_type not in HUBSPOT_OBJECT_TYPES:
            logger.warning(f"Object type {object_type} not in HUBSPOT_OBJECT_TYPES")
            return

        await conn.execute(
            """
            INSERT INTO config (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key)
            DO UPDATE SET
                value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            """,
            self.get_key(object_type),
            json.dumps([asdict(p) for p in properties]),
        )

    def get_key(self, object_type: str) -> str:
        """Get the key for a given object type."""
        return f"HUBSPOT_CUSTOM_PROPERTIES_{object_type.upper()}"


hubspot_custom_properties = HubspotCustomProperties()
