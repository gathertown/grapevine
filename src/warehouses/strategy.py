"""
Base warehouse strategy interface and factory for multi-warehouse support.

This module provides the abstract base class that all warehouse implementations
must follow, along with a factory for instantiating the correct strategy.
"""

from abc import ABC, abstractmethod

from src.warehouses.models import QueryResult, SemanticModel, WarehouseSource


class WarehouseStrategy(ABC):
    """Abstract base class for warehouse query strategies."""

    @property
    @abstractmethod
    def supports_natural_language(self) -> bool:
        """
        Whether this warehouse supports natural language to SQL translation.

        Returns:
            True if the warehouse can translate natural language questions to SQL,
            False if only direct SQL/query language is supported.
        """
        pass

    @abstractmethod
    async def execute_natural_language_query(
        self,
        tenant_id: str,
        question: str,
        semantic_model_id: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """
        Execute a natural language query against the warehouse.

        Args:
            tenant_id: Tenant identifier
            question: Natural language question
            semantic_model_id: Optional specific semantic model to use
            limit: Maximum rows to return

        Returns:
            QueryResult with structured data
        """
        pass

    @abstractmethod
    async def execute_sql(
        self,
        tenant_id: str,
        sql: str,
        warehouse: str | None = None,
        database: str | None = None,
        schema: str | None = None,
        limit: int = 100,
    ) -> QueryResult:
        """
        Execute a direct SQL query against the warehouse.

        Args:
            tenant_id: Tenant identifier
            sql: SQL query to execute
            warehouse: Optional warehouse/compute cluster
            database: Optional database to use
            schema: Optional schema to use
            limit: Maximum rows to return

        Returns:
            QueryResult with structured data
        """
        pass

    @abstractmethod
    async def has_configuration(self, tenant_id: str) -> bool:
        """
        Check if this warehouse is configured and available for the tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            True if warehouse is configured with semantic models/views
        """
        pass

    @abstractmethod
    async def get_semantic_models(self, tenant_id: str) -> list[SemanticModel]:
        """
        Get available semantic models for the tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of available semantic models with their IDs, names, and descriptions
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources (HTTP clients, connections, etc.)."""
        pass


class WarehouseStrategyFactory:
    """Factory for creating warehouse strategy instances."""

    _strategies: dict[WarehouseSource, type[WarehouseStrategy]] = {}

    @classmethod
    def register(cls, source: WarehouseSource, strategy_class: type[WarehouseStrategy]) -> None:
        """
        Register a warehouse strategy implementation.

        Args:
            source: Warehouse source enum value
            strategy_class: Strategy class to instantiate
        """
        cls._strategies[source] = strategy_class

    @classmethod
    def get_strategy(cls, source: WarehouseSource) -> WarehouseStrategy:
        """
        Get a strategy instance for the given warehouse source.

        Args:
            source: Warehouse source enum value

        Returns:
            Strategy instance

        Raises:
            ValueError: If no strategy is registered for the source
        """
        strategy_class = cls._strategies.get(source)
        if not strategy_class:
            available = ", ".join([s.value for s in cls._strategies])
            raise ValueError(
                f"No strategy registered for {source.value}. Available: {available or 'none'}"
            )
        return strategy_class()

    @classmethod
    def get_available_sources(cls) -> list[WarehouseSource]:
        """Get list of registered warehouse sources."""
        return list(cls._strategies.keys())

    @classmethod
    async def has_any_configuration(cls, tenant_id: str) -> bool:
        """
        Check if any warehouse is configured for the given tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            True if at least one warehouse is configured, False otherwise
        """
        for source in cls.get_available_sources():
            strategy = cls.get_strategy(source)
            try:
                has_config = await strategy.has_configuration(tenant_id)
                if has_config:
                    return True
            except Exception:
                # Skip this warehouse if there's an error checking configuration
                continue
            finally:
                await strategy.close()
        return False

    @classmethod
    async def get_all_semantic_models(cls, tenant_id: str) -> list[SemanticModel]:
        """
        Get all semantic models from all configured warehouses for the tenant.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of semantic models from all warehouses
        """
        all_models: list[SemanticModel] = []
        for source in cls.get_available_sources():
            strategy = cls.get_strategy(source)
            try:
                models = await strategy.get_semantic_models(tenant_id)
                all_models.extend(models)
            except Exception:
                # Skip this warehouse if there's an error fetching models
                continue
            finally:
                await strategy.close()
        return all_models

    @classmethod
    async def has_natural_language_configuration(cls, tenant_id: str) -> bool:
        """
        Check if any warehouse supporting natural language queries is configured.

        This only checks warehouses that support NL-to-SQL translation (e.g., Snowflake
        with Cortex Analyst). Warehouses like PostHog that only support direct SQL/HogQL
        are excluded.

        Args:
            tenant_id: Tenant identifier

        Returns:
            True if at least one NL-supporting warehouse is configured, False otherwise
        """
        for source in cls.get_available_sources():
            strategy = cls.get_strategy(source)
            try:
                # Only check warehouses that support natural language
                if not strategy.supports_natural_language:
                    continue
                has_config = await strategy.has_configuration(tenant_id)
                if has_config:
                    return True
            except Exception:
                # Skip this warehouse if there's an error checking configuration
                continue
            finally:
                await strategy.close()
        return False

    @classmethod
    async def get_natural_language_semantic_models(cls, tenant_id: str) -> list[SemanticModel]:
        """
        Get semantic models only from warehouses that support natural language queries.

        Args:
            tenant_id: Tenant identifier

        Returns:
            List of semantic models from NL-supporting warehouses only
        """
        all_models: list[SemanticModel] = []
        for source in cls.get_available_sources():
            strategy = cls.get_strategy(source)
            try:
                # Only include models from warehouses that support natural language
                if not strategy.supports_natural_language:
                    continue
                models = await strategy.get_semantic_models(tenant_id)
                all_models.extend(models)
            except Exception:
                # Skip this warehouse if there's an error fetching models
                continue
            finally:
                await strategy.close()
        return all_models
