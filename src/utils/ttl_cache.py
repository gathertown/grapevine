"""TTL (Time-To-Live) cache decorator for caching function results with expiration."""

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple TTL cache implementation for storing function results."""

    def __init__(self, ttl: float):
        """Initialize TTL cache.

        Args:
            ttl: Time-to-live in seconds
        """
        self.ttl = ttl
        self.cache: dict[tuple, tuple[float, Any]] = {}
        self.lock = asyncio.Lock()

    async def get(self, key: tuple) -> Any | None:
        """Get value from cache if not expired."""
        async with self.lock:
            if key in self.cache:
                timestamp, value = self.cache[key]
                if time.time() - timestamp < self.ttl:
                    return value
                else:
                    # Remove expired entry
                    del self.cache[key]
            return None

    async def set(self, key: tuple, value: Any) -> None:
        """Set value in cache with current timestamp."""
        async with self.lock:
            self.cache[key] = (time.time(), value)

    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self.lock:
            self.cache.clear()

    async def cleanup_expired(self) -> None:
        """Remove all expired entries from cache."""
        async with self.lock:
            current_time = time.time()
            expired_keys = [
                key
                for key, (timestamp, _) in self.cache.items()
                if current_time - timestamp >= self.ttl
            ]
            for key in expired_keys:
                del self.cache[key]


def ttl_cache(ttl: float) -> Callable:
    """Decorator to cache function results with TTL expiration.

    Args:
        ttl: Time-to-live in seconds (default: 900 = 15 minutes)

    Returns:
        Decorated function with caching
    """
    cache = TTLCache(ttl=ttl)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def sync_wrapper(self, *args, **kwargs):
            # For sync functions, we need to create a simple key
            cache_key = (id(self), func.__name__, args, tuple(sorted(kwargs.items())))

            # Check cache synchronously (simplified version)
            if cache_key in cache.cache:
                timestamp, value = cache.cache[cache_key]
                if time.time() - timestamp < cache.ttl:
                    logger.debug(f"Cache hit for {func.__name__} with args {args}")
                    return value
                else:
                    del cache.cache[cache_key]

            # Call the original function
            result = func(self, *args, **kwargs)

            # Store in cache
            cache.cache[cache_key] = (time.time(), result)
            logger.debug(f"Cached result for {func.__name__} with args {args}")

            return result

        @functools.wraps(func)
        async def async_wrapper(self, *args, **kwargs):
            # Create a cache key from function name and arguments
            cache_key = (id(self), func.__name__, args, tuple(sorted(kwargs.items())))

            # Check cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {func.__name__} with args {args}")
                return cached_value

            # Call the original function
            result = await func(self, *args, **kwargs)

            # Store in cache
            await cache.set(cache_key, result)
            logger.debug(f"Cached result for {func.__name__} with args {args}")

            return result

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
