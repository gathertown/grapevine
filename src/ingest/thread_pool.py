"""
Thread pool utilities for running async job handlers in background threads.

This prevents potentially expensive job processing from blocking
the main asyncio event loop and causing liveness check failures.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

logger = logging.getLogger(__name__)

# Global ThreadPoolExecutor for job handlers
_thread_pool_executor = None


def get_thread_pool_executor() -> ThreadPoolExecutor:
    """Get or create the global ThreadPoolExecutor for job handlers."""
    global _thread_pool_executor
    if _thread_pool_executor is None:
        # Use max_workers=None to let ThreadPoolExecutor determine optimal size
        # Typically min(32, (os.cpu_count() or 1) + 4)
        _thread_pool_executor = ThreadPoolExecutor(
            max_workers=None, thread_name_prefix="ingest-job"
        )
        logger.info(
            f"Created ThreadPoolExecutor with {_thread_pool_executor._max_workers} max workers"
        )
    return _thread_pool_executor


def run_in_thread_pool[**P, T](
    async_func: Callable[P, Awaitable[T]],
) -> Callable[P, Awaitable[T]]:
    """
    Decorator to run async job handlers in a ThreadPoolExecutor.

    This prevents potentially expensive job processing from blocking
    the main asyncio event loop and causing liveness check failures.

    Args:
        async_func: An async function to be executed in the thread pool

    Returns:
        A wrapped async function that executes the original function in a thread pool
    """

    @wraps(async_func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        executor = get_thread_pool_executor()
        loop = asyncio.get_event_loop()

        # Run the async function in the thread pool
        return await loop.run_in_executor(
            executor,
            lambda: asyncio.run(async_func(*args, **kwargs)),  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
        )

    return wrapper


def shutdown_thread_pool() -> None:
    """Shutdown the global ThreadPoolExecutor."""
    global _thread_pool_executor
    if _thread_pool_executor:
        logger.info("⏱️  Shutting down ThreadPoolExecutor...")
        _thread_pool_executor.shutdown(wait=True, cancel_futures=False)
        _thread_pool_executor = None
        logger.info("✅ ThreadPoolExecutor shutdown complete")
