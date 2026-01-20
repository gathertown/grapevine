"""Redis client wrapper for Corporate Context.

This module provides a centralized Redis client with:
- Configuration from REDIS_PRIMARY_ENDPOINT environment variable
- Connection management and health checks
- Async-first API following project patterns
"""

import logging

import redis.asyncio as redis

from src.utils.config import get_config_value

logger = logging.getLogger(__name__)


class RedisClient:
    """Centralized Redis client manager."""

    def __init__(self):
        self._client = None
        self._connection_url = None

    @property
    def connection_url(self) -> str:
        """Get Redis connection URL from environment."""
        if not self._connection_url:
            endpoint = get_config_value("REDIS_PRIMARY_ENDPOINT", "localhost:6379")
            # Add redis:// prefix if not present
            if not endpoint.startswith(("redis://", "rediss://", "unix://")):
                endpoint = f"redis://{endpoint}"
            self._connection_url = endpoint
        return self._connection_url

    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client (internal use only)."""
        if not self._client:
            self._client = redis.from_url(
                self.connection_url,
                decode_responses=True,
                retry_on_error=[redis.ConnectionError, redis.TimeoutError],
                retry_on_timeout=True,
                health_check_interval=30,
            )
        return self._client

    async def ping(self) -> bool:
        """Health check - ping Redis server.

        Returns:
            True if Redis is accessible, False otherwise
        """
        try:
            client = await self._get_client()
            result = await client.ping()
            logger.debug("Redis ping successful: %s", result)
            return result
        except Exception as e:
            logger.warning("Redis ping failed: %s", e)
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
_redis_client = RedisClient()


# ============================================================================
# Public API
# ============================================================================


async def ping() -> bool:
    """Ping Redis server for health checks.

    Returns:
        True if Redis is accessible, False otherwise
    """
    return await _redis_client.ping()


async def get_client() -> redis.Redis:
    """Get Redis client instance.

    Returns:
        Configured Redis client
    """
    return await _redis_client._get_client()


async def close() -> None:
    """Close Redis connection."""
    await _redis_client.close()


# ============================================================================
# Helper Functions
# ============================================================================


def get_connection_url() -> str:
    """Get Redis connection URL.

    Returns:
        Redis connection URL from environment
    """
    return _redis_client.connection_url
