"""Utility functions for detecting available data sources for tenants."""

from typing import Any

from src.clients.tenant_db import tenant_db_manager
from src.utils.logging import get_logger
from src.warehouses.strategy import WarehouseStrategyFactory

logger = get_logger(__name__)


class CustomDataTypeInfo:
    """Information about a custom data type for use in prompts."""

    def __init__(
        self,
        slug: str,
        display_name: str,
        description: str | None,
        fields: list[dict[str, Any]],
    ):
        self.slug = slug
        self.display_name = display_name
        self.description = description
        self.fields = fields

    def format_for_prompt(self) -> str:
        """Format this custom data type for inclusion in a prompt."""
        desc = self.description or "No description"
        if len(desc) > 150:
            desc = desc[:147] + "..."

        # Format fields with their types and descriptions
        field_parts = []
        for field in self.fields:
            field_name = field.get("name", "unknown")
            field_type = field.get("type", "text")
            field_desc = field.get("description", "")
            required = field.get("required", False)
            req_marker = " (required)" if required else ""

            if field_desc:
                field_parts.append(f"{field_name} ({field_type}{req_marker}): {field_desc}")
            else:
                field_parts.append(f"{field_name} ({field_type}{req_marker})")

        fields_text = ", ".join(field_parts) if field_parts else "no fields defined"
        return f"  - `{self.slug}` ({self.display_name}): {desc}\n    Fields: {fields_text}"


async def get_tenant_custom_data_types(tenant_id: str) -> list[CustomDataTypeInfo]:
    """Get list of enabled custom data types for this tenant.

    Args:
        tenant_id: The tenant identifier

    Returns:
        List of CustomDataTypeInfo objects with type metadata
    """
    try:
        async with (
            tenant_db_manager.acquire_pool(tenant_id, readonly=True) as db_pool,
            db_pool.acquire() as conn,
        ):
            result = await conn.fetch("""
                SELECT slug, display_name, description, custom_fields
                FROM custom_data_types
                WHERE state = 'enabled'
                ORDER BY display_name
            """)

            custom_types = []
            for row in result:
                custom_fields = row["custom_fields"] or {}
                fields = custom_fields.get("fields", [])

                custom_types.append(
                    CustomDataTypeInfo(
                        slug=row["slug"],
                        display_name=row["display_name"],
                        description=row["description"],
                        fields=fields,
                    )
                )

            return custom_types

    except Exception as e:
        logger.warning(
            "Error fetching custom data types (table may not exist yet)",
            tenant_id=tenant_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        # Return empty list on error to avoid breaking the agent
        return []


async def get_tenant_available_sources(tenant_id: str) -> list[str]:
    """Get list of data sources that have documents for this tenant.

    Also includes data warehouse sources (Snowflake, BigQuery, etc.) if configured.

    Args:
        tenant_id: The tenant identifier

    Returns:
        List of source names that have documents or data warehouse access
    """
    try:
        async with (
            tenant_db_manager.acquire_pool(tenant_id, readonly=True) as db_pool,
            db_pool.acquire() as conn,
        ):
            # Query distinct sources that have documents
            result = await conn.fetch("""
                SELECT DISTINCT source
                FROM documents
                WHERE source IS NOT NULL
                ORDER BY source
            """)

            sources = [row["source"] for row in result]

            # Check configured data warehouses using strategy pattern
            warehouse_sources = await _get_warehouse_sources(tenant_id)
            sources.extend(warehouse_sources)

            return sources

    except Exception as e:
        logger.error(
            "Error fetching available sources",
            tenant_id=tenant_id,
            error=str(e),
            error_type=type(e).__name__,
        )
        # Return empty list on error to avoid breaking the agent
        return []


async def _get_warehouse_sources(tenant_id: str) -> list[str]:
    """Get list of configured data warehouse sources for this tenant.

    Args:
        tenant_id: The tenant identifier

    Returns:
        List of warehouse source names (e.g., "Snowflake (Data Warehouse)")
    """
    warehouse_sources = []
    for warehouse_source in WarehouseStrategyFactory.get_available_sources():
        strategy = WarehouseStrategyFactory.get_strategy(warehouse_source)
        try:
            has_config = await strategy.has_configuration(tenant_id)
            if has_config:
                warehouse_name = warehouse_source.value.title()
                warehouse_sources.append(f"{warehouse_name} (Data Warehouse)")
        except Exception as e:
            # Strategy might not be fully implemented or table doesn't exist yet
            logger.warning(
                "Could not check warehouse configuration",
                tenant_id=tenant_id,
                warehouse=warehouse_source.value,
                error=str(e),
            )
        finally:
            await strategy.close()
    return warehouse_sources
