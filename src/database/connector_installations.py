"""Repository for managing connector installations in the control database."""

import json
from datetime import datetime
from enum import Enum
from uuid import UUID

import asyncpg

from src.utils.config import get_control_database_url


class ConnectorType(str, Enum):
    """Valid connector types matching TypeScript ConnectorType enum."""

    SLACK = "slack"
    GITHUB = "github"
    LINEAR = "linear"
    NOTION = "notion"
    GOOGLE_DRIVE = "google_drive"
    GOOGLE_EMAIL = "google_email"
    HUBSPOT = "hubspot"
    SALESFORCE = "salesforce"
    JIRA = "jira"
    CONFLUENCE = "confluence"
    GONG = "gong"
    GATHER = "gather"
    TRELLO = "trello"
    ZENDESK = "zendesk"
    ASANA = "asana"
    INTERCOM = "intercom"
    SNOWFLAKE = "snowflake"
    FIREFLIES = "fireflies"
    ATTIO = "attio"
    PIPEDRIVE = "pipedrive"
    CLICKUP = "clickup"
    PYLON = "pylon"
    MONDAY = "monday"
    FIGMA = "figma"
    POSTHOG = "posthog"
    CANVA = "canva"
    TEAMWORK = "teamwork"


class ConnectorStatus(str, Enum):
    """Valid connector statuses."""

    PENDING = "pending"
    ACTIVE = "active"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class Connector:
    """Connector data model."""

    def __init__(self, row: asyncpg.Record):
        self.id: UUID = row["id"]
        self.tenant_id: str = row["tenant_id"]
        self.type: str = row["type"]
        self.external_id: str = row["external_id"]
        self.external_metadata: dict = row["external_metadata"] or {}
        self.status: str = row["status"]
        self.created_at: datetime = row["created_at"]
        self.updated_at: datetime = row["updated_at"]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": str(self.id),
            "tenant_id": self.tenant_id,
            "type": self.type,
            "external_id": self.external_id,
            "external_metadata": self.external_metadata,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class ConnectorInstallationsRepository:
    """Repository for connector installation CRUD operations."""

    def __init__(self):
        self.control_db_url = get_control_database_url()

    async def _get_connection(self) -> asyncpg.Connection:
        """Get database connection."""
        return await asyncpg.connect(self.control_db_url)

    async def get_by_id(self, connector_id: UUID) -> Connector | None:
        """Get connector by ID."""
        conn = await self._get_connection()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, type, external_id, external_metadata,
                       status, created_at, updated_at
                FROM connector_installations
                WHERE id = $1
                """,
                connector_id,
            )
            return Connector(row) if row else None
        finally:
            await conn.close()

    async def get_by_tenant(self, tenant_id: str) -> list[Connector]:
        """Get all connectors for a tenant."""
        conn = await self._get_connection()
        try:
            rows = await conn.fetch(
                """
                SELECT id, tenant_id, type, external_id, external_metadata,
                       status, created_at, updated_at
                FROM connector_installations
                WHERE tenant_id = $1
                ORDER BY created_at DESC
                """,
                tenant_id,
            )
            return [Connector(row) for row in rows]
        finally:
            await conn.close()

    async def get_by_tenant_and_type(
        self, tenant_id: str, connector_type: ConnectorType
    ) -> Connector | None:
        """Get connector by tenant and type."""
        conn = await self._get_connection()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, type, external_id, external_metadata,
                       status, created_at, updated_at
                FROM connector_installations
                WHERE tenant_id = $1 AND type = $2
                """,
                tenant_id,
                connector_type,
            )
            return Connector(row) if row else None
        finally:
            await conn.close()

    async def get_by_tenant_type_and_external_id(
        self, tenant_id: str, connector_type: ConnectorType, external_id: str
    ) -> Connector | None:
        """Get connector by tenant, type, and external ID (unique constraint)."""
        conn = await self._get_connection()
        try:
            row = await conn.fetchrow(
                """
                SELECT id, tenant_id, type, external_id, external_metadata,
                       status, created_at, updated_at
                FROM connector_installations
                WHERE tenant_id = $1 AND type = $2 AND external_id = $3
                """,
                tenant_id,
                connector_type,
                external_id,
            )
            return Connector(row) if row else None
        finally:
            await conn.close()

    async def create(
        self,
        tenant_id: str,
        connector_type: ConnectorType,
        external_id: str,
        external_metadata: dict | None = None,
        status: ConnectorStatus = ConnectorStatus.PENDING,
    ) -> Connector:
        """Create a new connector."""
        conn = await self._get_connection()
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO connector_installations (tenant_id, type, external_id, external_metadata, status)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, tenant_id, type, external_id, external_metadata,
                          status, created_at, updated_at
                """,
                tenant_id,
                connector_type,
                external_id,
                json.dumps(external_metadata) if external_metadata else None,
                status,
            )
            return Connector(row)
        finally:
            await conn.close()

    async def update_status(self, connector_id: UUID, status: ConnectorStatus) -> None:
        """Update connector status."""
        conn = await self._get_connection()
        try:
            await conn.execute(
                """
                UPDATE connector_installations
                SET status = $1, updated_at = NOW()
                WHERE id = $2
                """,
                status,
                connector_id,
            )
        finally:
            await conn.close()

    async def update_metadata(self, connector_id: UUID, metadata: dict) -> None:
        """Update connector metadata."""
        conn = await self._get_connection()
        try:
            await conn.execute(
                """
                UPDATE connector_installations
                SET external_metadata = $1, updated_at = NOW()
                WHERE id = $2
                """,
                json.dumps(metadata) if metadata else None,
                connector_id,
            )
        finally:
            await conn.close()

    async def delete(self, connector_id: UUID) -> None:
        """Delete a connector (hard delete)."""
        conn = await self._get_connection()
        try:
            await conn.execute(
                """
                DELETE FROM connector_installations
                WHERE id = $1
                """,
                connector_id,
            )
        finally:
            await conn.close()

    async def mark_disconnected(self, connector_id: UUID) -> None:
        """Mark connector as disconnected (soft delete)."""
        await self.update_status(connector_id, ConnectorStatus.DISCONNECTED)

    async def get_by_type_and_external_id(
        self, connector_type: ConnectorType, external_id: str, exclude_disconnected: bool = True
    ) -> Connector | None:
        """Get connector by type and external_id (for webhook routing without tenant_id)."""
        conn = await self._get_connection()
        try:
            query = """
                SELECT id, tenant_id, type, external_id, external_metadata,
                       status, created_at, updated_at
                FROM connector_installations
                WHERE type = $1 AND external_id = $2
            """
            if exclude_disconnected:
                query += " AND status != 'disconnected'"

            row = await conn.fetchrow(query, connector_type, external_id)
            return Connector(row) if row else None
        finally:
            await conn.close()

    async def get_active_tenant_ids_by_type(self, connector_type: str) -> list[str]:
        """Get all tenant IDs that have an active connector of the given type.

        Only returns provisioned tenants with connectors that are not 'disconnected'.
        """
        conn = await self._get_connection()
        try:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ci.tenant_id
                FROM connector_installations ci
                JOIN tenants t ON ci.tenant_id = t.id
                WHERE ci.type = $1
                  AND ci.status = 'active'
                  AND t.state = 'provisioned'
                """,
                connector_type,
            )
            return [row["tenant_id"] for row in rows]
        finally:
            await conn.close()

    async def get_all_tenant_ids_with_connectors(self) -> list[str]:
        """Get all tenant IDs that have any connector installations.

        Only returns provisioned tenants.
        """
        conn = await self._get_connection()
        try:
            rows = await conn.fetch(
                """
                SELECT DISTINCT ci.tenant_id
                FROM connector_installations ci
                JOIN tenants t ON ci.tenant_id = t.id
                WHERE t.state = 'provisioned'
                ORDER BY ci.tenant_id
                """,
            )
            return [row["tenant_id"] for row in rows]
        finally:
            await conn.close()

    async def get_figma_connector_by_team_id(
        self, team_id: str, exclude_disconnected: bool = True
    ) -> Connector | None:
        """Get Figma connector by team_id (searches external_metadata.synced_team_ids).

        Figma webhooks include team_id, which we need to map to a tenant.
        The team_id is stored in external_metadata.synced_team_ids array.
        """
        conn = await self._get_connection()
        try:
            # Use the ? operator to check if a JSONB array contains a string element
            query = """
                SELECT id, tenant_id, type, external_id, external_metadata,
                       status, created_at, updated_at
                FROM connector_installations
                WHERE type = 'figma'
                  AND (
                    external_metadata->'synced_team_ids' ? $1
                    OR external_metadata->'selected_team_ids' ? $1
                  )
            """
            if exclude_disconnected:
                query += " AND status != 'disconnected'"

            row = await conn.fetchrow(query, team_id)
            return Connector(row) if row else None
        finally:
            await conn.close()
