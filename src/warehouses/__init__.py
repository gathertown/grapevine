"""
Warehouse integrations for structured data queries.

This package provides generic interfaces and service implementations
for querying data warehouses (Snowflake, BigQuery, Redshift, PostHog, etc.)
using natural language or SQL.
"""

from src.warehouses.models import (
    DEFAULT_SQL_TIMEOUT_SECONDS,
    CortexAnalystRequest,
    CortexAnalystResponse,
    QueryResult,
    QueryType,
    WarehouseQueryLog,
    WarehouseSource,
)
from src.warehouses.posthog_service import PostHogService
from src.warehouses.posthog_strategy import PostHogStrategy
from src.warehouses.snowflake_service import SnowflakeService
from src.warehouses.snowflake_strategy import SnowflakeStrategy
from src.warehouses.strategy import WarehouseStrategy, WarehouseStrategyFactory

# Register available warehouse strategies
WarehouseStrategyFactory.register(WarehouseSource.SNOWFLAKE, SnowflakeStrategy)
WarehouseStrategyFactory.register(WarehouseSource.POSTHOG, PostHogStrategy)

__all__ = [
    "PostHogService",
    "PostHogStrategy",
    "SnowflakeService",
    "SnowflakeStrategy",
    "WarehouseStrategy",
    "WarehouseStrategyFactory",
    "WarehouseSource",
    "QueryType",
    "WarehouseQueryLog",
    "QueryResult",
    "CortexAnalystRequest",
    "CortexAnalystResponse",
    "DEFAULT_SQL_TIMEOUT_SECONDS",
]
