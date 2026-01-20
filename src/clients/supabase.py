"""Supabase client utility for database and storage access."""

import asyncpg
import psycopg2

from src.utils.config import get_database_url


class SupabaseDB:
    """Centralized database connection manager for Supabase PostgreSQL."""

    def __init__(self):
        self._connection_string = None
        self._pool = None

    @property
    def connection_string(self) -> str:
        """Get PostgreSQL connection string."""
        if not self._connection_string:
            self._connection_string = _get_db_connection_string()
        return self._connection_string

    async def _get_connection(self) -> asyncpg.Connection:
        """Get a new async PostgreSQL connection (internal use only)."""
        return await asyncpg.connect(self.connection_string)

    async def _get_pool(self, min_size=10, max_size=20) -> asyncpg.Pool:
        """Get or create async connection pool (internal use only)."""
        if not self._pool:
            self._pool = await asyncpg.create_pool(
                self.connection_string, min_size=min_size, max_size=max_size, timeout=30
            )
        return self._pool

    def _get_sync_connection(self):
        """Get synchronous PostgreSQL connection (internal use only)."""
        return psycopg2.connect(self.connection_string)


# Singleton instance
_db = SupabaseDB()

# ============================================================================
# Public API - Document Operations
# ============================================================================


# ============================================================================
# Helper Functions
# ============================================================================


def _get_db_connection_string() -> str:
    """Get PostgreSQL connection string using config utility.

    Returns:
        PostgreSQL connection string

    Raises:
        ValueError: If connection details cannot be found
    """
    return get_database_url()


# ============================================================================
# Legacy Functions (for backward compatibility)
# ============================================================================


def get_db_connection_string() -> str:
    """Legacy function - use internal methods instead."""
    return _get_db_connection_string()


async def get_global_db_connection() -> asyncpg.Connection:
    """Get a new connection to the global (non-tenant) database."""
    return await _db._get_connection()


async def get_control_db_connection() -> asyncpg.Connection:
    """Get a new connection to the control database for health checks and tenant management."""
    from src.utils.config import get_control_database_url

    control_db_url = get_control_database_url()
    return await asyncpg.connect(control_db_url)
