"""Error handling utilities for consistent exception recording and metrics."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import TypedDict

import newrelic.agent
import structlog

# Support both standard Logger and structlog BoundLogger
LoggerType = logging.Logger | structlog.BoundLogger


class ErrorCounter(TypedDict, total=False):
    """Counter dict for tracking success/failure metrics."""

    successful: int
    failed: int


@contextmanager
def record_exception_and_ignore(
    logger: LoggerType, context: str, counter: ErrorCounter
) -> Generator[None]:
    """Context manager that records both successes and failures for metrics.

    On success: increments counter["successful"]
    On exception: logs error, records to New Relic, increments counter["failed"], continues execution

    Args:
        logger: Logger instance to use for error logging
        context: Description of what operation failed (e.g. "Failed to transform artifact ABC123")
        counter: Dict to track success/failure counts (will be modified in-place)

    Example:
        counter = {}
        with record_exception_and_ignore(logger, f"Failed to process item {item.id}", counter):
            result = process_item(item)
            items.append(result)

        logger.info(f"Processed items: {counter.get('successful', 0)} successful, {counter.get('failed', 0)} failed")
    """
    try:
        yield
        counter["successful"] = counter.get("successful", 0) + 1
    except Exception as e:
        logger.error(f"{context}: {e}")
        newrelic.agent.record_exception()
        counter["failed"] = counter.get("failed", 0) + 1


def extract_first_exception[TErr: Exception](
    exc: ExceptionGroup, target_type: type[TErr]
) -> TErr | None:
    """
    Extract the first exception of the specified type from a nested ExceptionGroup.
    99.9% of the time we are just going to be handling a single exception, but for correctness we
    should probably handle nested exception groups. This is useful if we want to extract something
    out of the exception like say a visibility extension or rate limit timeout.
    """
    for sub_exc in exc.exceptions:
        if isinstance(sub_exc, BaseExceptionGroup):
            result = extract_first_exception(sub_exc, target_type)
            if result is not None:
                return result

        if isinstance(sub_exc, target_type):
            return sub_exc

    return None
