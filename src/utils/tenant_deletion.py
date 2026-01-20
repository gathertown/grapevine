"""
Tenant deletion utilities.

Provides helper functions to check if a tenant has been marked as deleted.
"""

import asyncpg

from src.utils.logging import get_logger
from src.utils.redis_cache import get_or_compute

logger = get_logger(__name__)

# Redis cache TTL for deleted_at checks (10 minutes)
DELETED_AT_CACHE_TTL_SECONDS = 600


async def is_tenant_deleted(control_db_pool: asyncpg.Pool, tenant_id: str) -> bool:
    """Check if a tenant has been marked as deleted.

    Uses Redis caching with 10-minute TTL to reduce database connection pool pressure.
    Falls back to database if Redis is unavailable.

    Args:
        control_db_pool: Control database connection pool
        tenant_id: The tenant ID to check

    Returns:
        bool: True if tenant is deleted (deleted_at is not null), False otherwise
    """
    cache_key = f"tenant:deleted:{tenant_id}"

    async def fetch_from_db() -> bool:
        """Query database for tenant deletion status."""
        async with control_db_pool.acquire() as conn:
            deleted_at = await conn.fetchval(
                "SELECT deleted_at FROM tenants WHERE id = $1", tenant_id
            )

        is_deleted = deleted_at is not None

        if is_deleted:
            logger.warning(f"Tenant {tenant_id} is marked as deleted (deleted at {deleted_at})")

        return is_deleted

    # Use cache helper to get or compute the value
    return await get_or_compute(
        cache_key=cache_key,
        compute_fn=fetch_from_db,
        serialize_fn=lambda val: "1" if val else "0",
        deserialize_fn=lambda s: s == "1",
        ttl_seconds=DELETED_AT_CACHE_TTL_SECONDS,
    )
