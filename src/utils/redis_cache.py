"""
Redis caching utilities.

Provides helper functions for caching values in Redis with automatic fallback.
"""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from src.clients.redis import get_client as get_redis_client
from src.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


async def get_or_compute(
    cache_key: str,
    compute_fn: Callable[[], Awaitable[T]],
    serialize_fn: Callable[[T], str],
    deserialize_fn: Callable[[str], T],
    ttl_seconds: int,
) -> T:
    """Get a value from Redis cache or compute it if not found.

    This function implements a standard cache-aside pattern:
    1. Try to get the value from Redis
    2. If not found, compute the value using the provided function
    3. Store the computed value in Redis with the specified TTL
    4. Return the value

    Args:
        cache_key: Redis key to use for caching
        compute_fn: Async function to compute the value if cache miss
        serialize_fn: Function to serialize the value to a string for Redis
        deserialize_fn: Function to deserialize the Redis string back to value
        ttl_seconds: Time-to-live in seconds for the cached value

    Returns:
        The cached or computed value

    Example:
        >>> async def fetch_user(user_id: str) -> User:
        ...     # Expensive database query
        ...     return await db.get_user(user_id)
        >>>
        >>> user = await get_or_compute(
        ...     cache_key=f"user:{user_id}",
        ...     compute_fn=lambda: fetch_user(user_id),
        ...     serialize_fn=lambda u: u.json(),
        ...     deserialize_fn=lambda s: User.parse_raw(s),
        ...     ttl_seconds=60,
        ... )
    """
    # Try Redis cache first
    try:
        redis_client = await get_redis_client()
        cached_value = await redis_client.get(cache_key)

        if cached_value is not None:
            # Cache hit - deserialize and return
            logger.debug(f"Cache hit for key: {cache_key}")
            return deserialize_fn(cached_value)
    except Exception as e:
        logger.debug(f"Redis unavailable for cache lookup: {e}")
        # Fall through to compute

    # Cache miss or Redis unavailable - compute value
    logger.debug(f"Cache miss for key: {cache_key}")
    value = await compute_fn()

    # Populate cache for future requests
    try:
        redis_client = await get_redis_client()
        serialized_value = serialize_fn(value)
        await redis_client.setex(cache_key, ttl_seconds, serialized_value)
        logger.debug(f"Cached value for key: {cache_key} (TTL: {ttl_seconds}s)")
    except Exception as e:
        logger.debug(f"Failed to cache value: {e}")
        # Not critical - continue without caching

    return value


async def invalidate(cache_key: str) -> bool:
    """Invalidate a cache entry by deleting it from Redis.

    Args:
        cache_key: Redis key to invalidate

    Returns:
        True if the key was deleted, False otherwise
    """
    try:
        redis_client = await get_redis_client()
        result = await redis_client.delete(cache_key)
        if result:
            logger.debug(f"Invalidated cache key: {cache_key}")
        return result > 0
    except Exception as e:
        logger.debug(f"Failed to invalidate cache key {cache_key}: {e}")
        return False
