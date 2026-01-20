import asyncio
import functools
import time

from tqdm import tqdm

from src.jobs.exceptions import ExtendVisibilityException


class RateLimitedError(Exception):
    """Exception to indicate a function was rate limited."""

    def __init__(self, retry_after=None, message="Rate limited", logger=tqdm.write):
        self.retry_after = retry_after
        self.logger = logger
        super().__init__(message)


def _handle_rate_limit_error(
    e: RateLimitedError, attempt: int, max_retries: int, base_delay: int, func_name: str
):
    """Handle a rate limit error - calculate delay, log, and handle extensions."""
    logger_func = e.logger or tqdm.write

    if attempt >= max_retries - 1:
        logger_func(f"[ERROR] Max retries reached for {func_name}")
        raise e

    # Determine delay: use server-provided retry_after or exponential backoff
    delay = e.retry_after if e.retry_after else base_delay * (2**attempt)
    delay_source = "server says" if e.retry_after else "calculated delay"

    # Handle long delays with SQS visibility extension
    if delay > 30:
        logger_func(
            f"[WARN] Rate limited, {delay_source} wait {delay} seconds - extending SQS visibility timeout"
        )
        raise ExtendVisibilityException(
            visibility_timeout_seconds=int(delay) + 5,
            message=f"Rate limited for {delay} seconds, extend SQS visibility timeout",
        )

    # Log retry attempt
    logger_func(
        f"[WARN] Rate limited, {delay_source} wait {delay} seconds before retry {attempt + 1}/{max_retries}"
    )

    return delay


async def _async_retry_with_rate_limiting(func, args, kwargs, max_retries: int, base_delay: int):
    """Shared retry logic for async rate limiting."""
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except RateLimitedError as e:
            delay = _handle_rate_limit_error(e, attempt, max_retries, base_delay, func.__name__)
            await asyncio.sleep(delay)

    raise Exception(f"[ERROR] Unexpected error in retry logic for {func.__name__}")


def _sync_retry_with_rate_limiting(func, args, kwargs, max_retries: int, base_delay: int):
    """Shared retry logic for sync rate limiting."""
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except RateLimitedError as e:
            delay = _handle_rate_limit_error(e, attempt, max_retries, base_delay, func.__name__)
            time.sleep(delay)

    raise Exception(f"[ERROR] Unexpected error in retry logic for {func.__name__}")


def rate_limited(max_retries=5, base_delay=5):
    """
    Decorator to add exponential backoff retry logic for rate limiting to any function or coroutine.
    The decorated function should raise RateLimitedError when rate limited.

    Supports both async and sync functions.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff

    Usage:
        @rate_limited()
        def api_call():
            try:
                return some_api_call()
            except SomeAPIError as e:
                if is_rate_limited(e):
                    raise RateLimitedError(retry_after=get_retry_after(e))
                raise
    """

    def decorator(func):
        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await _async_retry_with_rate_limiting(
                    func, args, kwargs, max_retries, base_delay
                )

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                return _sync_retry_with_rate_limiting(func, args, kwargs, max_retries, base_delay)

            return sync_wrapper

    return decorator
