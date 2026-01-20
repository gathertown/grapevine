"""Tests for TTL cache implementation."""

import asyncio
import time
from unittest.mock import patch

import pytest

from src.utils.ttl_cache import TTLCache, ttl_cache


class TestTTLCache:
    """Test the TTLCache class."""

    @pytest.mark.asyncio
    async def test_get_set_basic(self):
        """Test basic get and set operations."""
        cache = TTLCache(ttl=60)

        # Test setting and getting a value
        await cache.set(("key1",), "value1")
        result = await cache.get(("key1",))
        assert result == "value1"

        # Test getting non-existent key
        result = await cache.get(("key2",))
        assert result is None

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = TTLCache(ttl=0.1)  # 100ms TTL

        # Set a value
        await cache.set(("key1",), "value1")

        # Should exist immediately
        result = await cache.get(("key1",))
        assert result == "value1"

        # Wait for expiration
        await asyncio.sleep(0.2)

        # Should be expired now
        result = await cache.get(("key1",))
        assert result is None

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clearing the cache."""
        cache = TTLCache(ttl=60)

        # Add multiple entries
        await cache.set(("key1",), "value1")
        await cache.set(("key2",), "value2")
        await cache.set(("key3",), "value3")

        # Verify they exist
        assert await cache.get(("key1",)) == "value1"
        assert await cache.get(("key2",)) == "value2"
        assert await cache.get(("key3",)) == "value3"

        # Clear cache
        await cache.clear()

        # Verify all are gone
        assert await cache.get(("key1",)) is None
        assert await cache.get(("key2",)) is None
        assert await cache.get(("key3",)) is None

    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = TTLCache(ttl=0.2)  # 200ms TTL

        # Add entries at different times
        await cache.set(("key1",), "value1")
        await asyncio.sleep(0.1)
        await cache.set(("key2",), "value2")
        await asyncio.sleep(0.15)  # key1 should be expired, key2 still valid
        await cache.set(("key3",), "value3")

        # Before cleanup, expired entry still in cache dict
        assert len(cache.cache) == 3

        # Run cleanup
        await cache.cleanup_expired()

        # After cleanup, only non-expired entries remain
        assert len(cache.cache) == 2
        assert await cache.get(("key2",)) == "value2"
        assert await cache.get(("key3",)) == "value3"
        assert await cache.get(("key1",)) is None


class TestTTLCacheDecorator:
    """Test the ttl_cache decorator."""

    def test_sync_function_caching(self):
        """Test caching of synchronous functions."""
        call_count = 0

        class TestClass:
            @ttl_cache(ttl=60)
            def get_value(self, key):
                nonlocal call_count
                call_count += 1
                return f"value_{key}_{call_count}"

        obj = TestClass()

        # First call should execute function
        result1 = obj.get_value("test")
        assert result1 == "value_test_1"
        assert call_count == 1

        # Second call should use cache
        result2 = obj.get_value("test")
        assert result2 == "value_test_1"
        assert call_count == 1  # No additional call

        # Different argument should execute function
        result3 = obj.get_value("other")
        assert result3 == "value_other_2"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_function_caching(self):
        """Test caching of asynchronous functions."""
        call_count = 0

        class TestClass:
            @ttl_cache(ttl=60)
            async def get_value(self, key):
                nonlocal call_count
                call_count += 1
                await asyncio.sleep(0.01)  # Simulate async work
                return f"async_value_{key}_{call_count}"

        obj = TestClass()

        # First call should execute function
        result1 = await obj.get_value("test")
        assert result1 == "async_value_test_1"
        assert call_count == 1

        # Second call should use cache
        result2 = await obj.get_value("test")
        assert result2 == "async_value_test_1"
        assert call_count == 1  # No additional call

        # Different argument should execute function
        result3 = await obj.get_value("other")
        assert result3 == "async_value_other_2"
        assert call_count == 2

    def test_sync_function_ttl_expiration(self):
        """Test TTL expiration for sync functions."""
        call_count = 0

        class TestClass:
            @ttl_cache(ttl=0.1)  # 100ms TTL
            def get_value(self, key):
                nonlocal call_count
                call_count += 1
                return f"value_{key}_{call_count}"

        obj = TestClass()

        # First call
        result1 = obj.get_value("test")
        assert result1 == "value_test_1"
        assert call_count == 1

        # Wait for expiration
        time.sleep(0.2)

        # Should execute function again
        result2 = obj.get_value("test")
        assert result2 == "value_test_2"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_async_function_ttl_expiration(self):
        """Test TTL expiration for async functions."""
        call_count = 0

        class TestClass:
            @ttl_cache(ttl=0.1)  # 100ms TTL
            async def get_value(self, key):
                nonlocal call_count
                call_count += 1
                return f"async_value_{key}_{call_count}"

        obj = TestClass()

        # First call
        result1 = await obj.get_value("test")
        assert result1 == "async_value_test_1"
        assert call_count == 1

        # Wait for expiration
        await asyncio.sleep(0.2)

        # Should execute function again
        result2 = await obj.get_value("test")
        assert result2 == "async_value_test_2"
        assert call_count == 2

    def test_multiple_instances(self):
        """Test that cache is separate for different instances."""

        class TestClass:
            def __init__(self, prefix):
                self.prefix = prefix

            @ttl_cache(ttl=60)
            def get_value(self, key):
                return f"{self.prefix}_{key}"

        obj1 = TestClass("obj1")
        obj2 = TestClass("obj2")

        # Each instance should have its own cache
        result1 = obj1.get_value("test")
        assert result1 == "obj1_test"

        result2 = obj2.get_value("test")
        assert result2 == "obj2_test"

        # Verify they don't share cache
        assert result1 != result2

    def test_function_with_kwargs(self):
        """Test caching with keyword arguments."""
        call_count = 0

        class TestClass:
            @ttl_cache(ttl=60)
            def get_value(self, key, prefix="default"):
                nonlocal call_count
                call_count += 1
                return f"{prefix}_{key}_{call_count}"

        obj = TestClass()

        # Different kwargs should result in different cache entries
        result1 = obj.get_value("test", prefix="a")
        assert result1 == "a_test_1"
        assert call_count == 1

        result2 = obj.get_value("test", prefix="b")
        assert result2 == "b_test_2"
        assert call_count == 2

        # Same kwargs should use cache
        result3 = obj.get_value("test", prefix="a")
        assert result3 == "a_test_1"
        assert call_count == 2  # No additional call

    @patch("src.utils.ttl_cache.logger")
    def test_logging(self, mock_logger):
        """Test that cache hits and misses are logged."""

        class TestClass:
            @ttl_cache(ttl=60)
            def get_value(self, key):
                return f"value_{key}"

        obj = TestClass()

        # First call (cache miss)
        obj.get_value("test")
        mock_logger.debug.assert_called_with("Cached result for get_value with args ('test',)")

        # Second call (cache hit)
        obj.get_value("test")
        mock_logger.debug.assert_called_with("Cache hit for get_value with args ('test',)")
