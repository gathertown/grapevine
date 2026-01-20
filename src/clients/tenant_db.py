import asyncio
import contextlib
import json
import os
from collections import OrderedDict
from collections.abc import AsyncIterator
from dataclasses import dataclass

import asyncpg

from src.clients.ssm import SSMClient
from src.utils.config import get_control_database_url
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Default pool limits
DEFAULT_MAX_POOLS = 10
DEFAULT_MAX_READONLY_POOLS = 10


async def init_connection(conn: asyncpg.Connection) -> None:
    """An initializer run on every new connection from any DB pool created by TenantDBManager."""
    await conn.set_type_codec(
        "jsonb",
        # We don't automatically json.dumps() largely for safety reasons.
        # It's not always obvious whether a db_pool came from this file or not, so
        # for now we always explicitly json.dumps() everywhere regardless to mitigate
        # risk of double-encoding (e.g. AIVP-301) or not encoding at all.
        encoder=lambda x: x,  # no-op. callsites must explicitly json.dumps() their objects
        decoder=json.loads,
        schema="pg_catalog",
    )


@dataclass
class PoolInfo:
    """Information about a connection pool."""

    pool: asyncpg.Pool
    tenant_id: str = ""


class TenantDBManager:
    """Manage asyncpg connection pools per tenant (organization).

    Provides context managers for acquiring pools and connections.
    Supports both tenant-specific and control database pools.
    Uses LRU caching to automatically close least recently used pools.
    """

    def __init__(
        self,
        max_pools: int = DEFAULT_MAX_POOLS,
        max_readonly_pools: int = DEFAULT_MAX_READONLY_POOLS,
    ) -> None:
        self._pool_info: OrderedDict[str, PoolInfo] = OrderedDict()
        self._readonly_pool_info: OrderedDict[str, PoolInfo] = OrderedDict()
        self._max_pools = max_pools
        self._max_readonly_pools = max_readonly_pools
        # Locks are lazily initialized to avoid event loop binding issues
        # when using multiple asyncio.run() calls in CLI tools
        self._lock: asyncio.Lock | None = None
        self._control_db_lock: asyncio.Lock | None = None
        self._ssm = SSMClient()
        self.control_db_pool: asyncpg.Pool | None = None

    @property
    def _pool_lock(self) -> asyncio.Lock:
        """Lazily initialize the pool lock for the current event loop."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    @property
    def _control_lock(self) -> asyncio.Lock:
        """Lazily initialize the control DB lock for the current event loop."""
        if self._control_db_lock is None:
            self._control_db_lock = asyncio.Lock()
        return self._control_db_lock

    async def get_control_db(self) -> asyncpg.Pool:
        """Get the control database pool, initializing it if needed."""
        if self.control_db_pool is None:
            async with self._control_lock:
                # Double-check in case control_db_pool was created while acquiring the lock
                if self.control_db_pool is None:
                    self.control_db_pool = await asyncpg.create_pool(
                        get_control_database_url(),
                        min_size=0,
                        max_size=3,
                        timeout=30,  # connection acquisition timeout
                        command_timeout=10,
                        init=init_connection,
                    )
                    logger.info("Control database pool initialized")
        return self.control_db_pool

    async def _get_connection_params(self, org_id: str, readonly: bool = False) -> dict[str, str]:
        """Get connection params for the given org suitable for passing to `asyncpg.connect`
        (or `asyncpg.create_pool`). Queries SSM to retrieve db/username/pass.

        Expects these SSM parameters (created by tenant provisioner):
          /{org_id}/credentials/postgresql/db_name
          /{org_id}/credentials/postgresql/db_rw_user
          /{org_id}/credentials/postgresql/db_rw_pass

        And these env vars for host/port:
          PG_TENANT_DATABASE_HOST (for read-write)
          PG_TENANT_DATABASE_HOST_READONLY (for read-only)
          PG_TENANT_DATABASE_PORT (default 5432)

        Args:
            org_id: Organization ID
            readonly: Whether to use readonly database host
        """
        logger.info(f"Fetching database credentials from SSM for org {org_id}")
        db_name, db_rw_user, db_rw_pass = await asyncio.gather(
            self._ssm.get_parameter(f"/{org_id}/credentials/postgresql/db_name"),
            self._ssm.get_parameter(f"/{org_id}/credentials/postgresql/db_rw_user"),
            self._ssm.get_parameter(f"/{org_id}/credentials/postgresql/db_rw_pass"),
        )

        missing: list[str] = []
        if not db_name:
            missing.append("db_name")
        if not db_rw_user:
            missing.append("db_rw_user")
        if not db_rw_pass:
            missing.append("db_rw_pass")
        if missing:
            raise ValueError(f"Missing SSM credentials for org {org_id}: {', '.join(missing)}")

        host_env_var = "PG_TENANT_DATABASE_HOST_READONLY" if readonly else "PG_TENANT_DATABASE_HOST"
        host = os.environ.get(host_env_var)
        if not host:
            raise ValueError(
                f"{host_env_var} environment variable is required for tenant {'readonly' if readonly else 'read-write'} DB connections"
            )

        port = os.environ.get("PG_TENANT_DATABASE_PORT", "5432")
        sslmode = os.environ.get("PG_TENANT_DATABASE_SSLMODE", "require")

        # escape all URL components
        return {
            "host": host,
            "port": port,
            "user": db_rw_user or "",
            "password": db_rw_pass or "",
            "database": db_name or "",
            "ssl": sslmode,
        }

    async def _evict_lru_pool(self, readonly: bool = False) -> None:
        """Evict the least recently used pool to make room for a new one.

        Args:
            readonly: Whether to evict from readonly pools or read-write pools
        """
        pool_dict = self._readonly_pool_info if readonly else self._pool_info
        pool_type = "readonly" if readonly else "read-write"

        if not pool_dict:
            return

        # Get least recently used (first item in OrderedDict)
        lru_org_id, lru_pool_info = next(iter(pool_dict.items()))

        logger.info(f"Evicting LRU {pool_type} pool for org {lru_org_id}")
        try:
            await lru_pool_info.pool.close()
        except Exception as e:
            logger.error(f"Error closing {pool_type} pool for org {lru_org_id}: {e}")
        finally:
            del pool_dict[lru_org_id]

    async def _get_or_create_pool(self, org_id: str, readonly: bool = False) -> PoolInfo:
        """Internal method to get or create a pool for a tenant.

        Args:
            org_id: Organization ID
            readonly: Whether to create a readonly pool

        Returns PoolInfo object containing the pool.
        """
        if not org_id:
            raise ValueError("org_id is required to get tenant DB pool")

        pool_dict = self._readonly_pool_info if readonly else self._pool_info
        max_pools = self._max_readonly_pools if readonly else self._max_pools

        async with self._pool_lock:
            # Check if pool exists and mark as most recently used
            pool_info = pool_dict.get(org_id)
            if pool_info is not None:
                # Move to end (mark as most recently used)
                pool_dict.move_to_end(org_id)
                return pool_info

            # Check if we need to evict before creating new pool
            if len(pool_dict) >= max_pools:
                await self._evict_lru_pool(readonly=readonly)

            connection_params = await self._get_connection_params(org_id, readonly=readonly)

            # Create pool with SSL but without certificate verification
            pool = await asyncpg.create_pool(
                **connection_params, min_size=0, max_size=3, init=init_connection, timeout=30
            )
            pool_info = PoolInfo(pool=pool, tenant_id=org_id)
            pool_dict[org_id] = pool_info

            pool_type = "readonly" if readonly else "read-write"
            logger.info(
                f"Created {pool_type} pool for org {org_id}, new total {len(pool_dict)} {pool_type} pools"
            )
            return pool_info

    @contextlib.asynccontextmanager
    async def acquire_pool(
        self, tenant_id: str, readonly: bool = False
    ) -> AsyncIterator[asyncpg.Pool]:
        """Context manager to acquire a database pool for a tenant.

        Usage:
            async with tenant_db_manager.acquire_pool(tenant_id) as pool:
                # Use pool
            async with tenant_db_manager.acquire_pool(tenant_id, readonly=True) as pool:
                # Use pool for read-only operations

        The pool is managed by an LRU cache and will be closed when evicted.
        """
        pool_type = "readonly" if readonly else "read-write"
        try:
            pool_info = await self._get_or_create_pool(tenant_id, readonly=readonly)
        except Exception as e:
            logger.error(
                f"Failed to acquire {pool_type} pool for tenant {tenant_id}: {e}", exc_info=True
            )
            raise

        logger.info(f"Acquired {pool_type} pool for tenant {tenant_id}")
        yield pool_info.pool

    @contextlib.asynccontextmanager
    async def acquire_connection(
        self, tenant_id: str, readonly: bool = False
    ) -> AsyncIterator[asyncpg.Connection]:
        """Context manager to acquire a database connection for a tenant.

        Usage:
            async with tenant_db_manager.acquire_connection(tenant_id) as conn:
                # Use connection
            async with tenant_db_manager.acquire_connection(tenant_id, readonly=True) as conn:
                # Use connection for read-only operations

        The pool will be automatically closed when reference count reaches zero.
        """
        async with self.acquire_pool(tenant_id, readonly=readonly) as pool, pool.acquire() as conn:
            yield conn

    async def cleanup(self) -> None:
        """Close all connection pools and reset event-loop-bound state.

        This method should be called before the event loop is destroyed,
        especially when using multiple asyncio.run() calls in CLI tools.
        After cleanup, the manager can be safely used in a new event loop.
        """
        # Close tenant read-write pools
        for pool_info in list(self._pool_info.values()):
            logger.info(f"Closing read-write pool for org {pool_info.tenant_id}")
            with contextlib.suppress(Exception):
                await pool_info.pool.close()
        self._pool_info.clear()

        # Close tenant readonly pools
        for pool_info in list(self._readonly_pool_info.values()):
            logger.info(f"Closing readonly pool for org {pool_info.tenant_id}")
            with contextlib.suppress(Exception):
                await pool_info.pool.close()
        self._readonly_pool_info.clear()

        # Close control pool
        if self.control_db_pool:
            with contextlib.suppress(Exception):
                await self.control_db_pool.close()
            self.control_db_pool = None
            logger.info("Control database pool closed")

        # Reset locks to None so they can be lazily recreated in the new event loop
        # This is necessary when using multiple asyncio.run() calls - creating new
        # Lock() objects here would bind them to the closing event loop
        self._lock = None
        self._control_db_lock = None


# Singleton manager
# Session token is automatically used if AWS_SESSION_TOKEN env var is set (matches JS pattern)
_tenant_db_manager = TenantDBManager()

# Export the singleton for external use
tenant_db_manager = _tenant_db_manager
