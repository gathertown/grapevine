"""Grapevine logging config

## Setup

Logging is automatically configured when this module is imported. It uses structlog for structured logging. Logs are
pretty-printed in local env (GRAPEVINE_ENVIRONMENT='local') and are JSON-formatted in other envs.

Example usage:

```
from src.utils.logging import get_logger

logger = get_logger(__name__)
logger.info("Hello world", user_id="123", action="login")
```

## Log context

Use add_log_context() to add context that will be included in all subsequent log messages within the current async
context:

```
from src.utils.logging import add_log_context, get_logger

# Set context for the entire request
add_log_context(tenant_id="tenant-123", request_id="req-456")

logger = get_logger(__name__)
logger.info("Processing request")  # Includes tenant_id and request_id
logger.error("Request failed", error="validation")  # Also includes tenant_id and request_id
```

Use clear_log_context() to reset all context (useful at request boundaries):

```python
from src.utils.logging import clear_log_context, add_log_context, get_logger

clear_log_context()  # Start fresh
add_log_context(tenant_id="new-tenant")
logger = get_logger(__name__)
logger.info("New request")  # Only includes new context
```

### Standard logging integration

We configure Python's standard `logging` module to route through structlog. This means that library code using
`logging.getLogger()` will automatically include context and be formatted correctly for the env.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import structlog
import structlog.contextvars

from src.utils.config import get_grapevine_environment
from src.utils.newrelic_logging import newrelic_error_processor


def _is_local_environment() -> bool:
    """Check if we're running in a local development environment.

    Returns:
        True if running locally, False otherwise
    """
    return get_grapevine_environment() == "local"


def _get_log_renderer() -> structlog.types.Processor:
    """Get the appropriate console renderer based on environment.

    Can be overridden with LOG_RENDERER environment variable:
    - 'console': Force ConsoleRenderer (human-readable with colors)
    - 'json': Force JSONRenderer (structured JSON output)

    Returns:
        ConsoleRenderer for local dev, JSONRenderer for production
    """
    # Check for explicit override
    log_renderer = os.getenv("LOG_RENDERER", "").lower()
    if log_renderer == "console":
        use_console = True
    elif log_renderer == "json":
        use_console = False
    else:
        # Fall back to environment-based detection
        use_console = _is_local_environment()

    if use_console:
        return structlog.dev.ConsoleRenderer(
            colors=True,
            pad_event=0,  # No padding to prevent wrapping
            force_colors=False,
            repr_native_str=False,
            exception_formatter=structlog.dev.plain_traceback,
            sort_keys=True,  # Sort context keys for consistency
            event_key="message",
        )
    else:
        # Use JSON format for production/New Relic
        return structlog.processors.JSONRenderer()


# Configure structlog with New Relic recommended settings and built-in contextvars support
def configure_logging() -> None:
    """Configure structlog with environment-appropriate settings using built-in contextvars.

    Local development: Human-readable console output with colors
    Production: JSON format for New Relic and log aggregation
    """
    # Common processors for all environments
    common_processors: list[structlog.types.Processor] = [
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.contextvars.merge_contextvars,  # Use structlog's built-in contextvars support
        structlog.processors.EventRenamer("message"),  # Rename 'event' to 'message' for New Relic
        newrelic_error_processor,  # Send error-level logs to New Relic
        structlog.stdlib.filter_by_level,  # Must come after add_log_level
    ]

    # Configure structlog to work with ProcessorFormatter
    # The wrap_for_formatter processor formats messages for standard library compatibility
    structlog.configure(
        processors=common_processors + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Set up a handler that uses structlog formatting for ALL loggers
    # For foreign_pre_chain, we need to exclude filter_by_level since standard library
    # loggers handle their own filtering and the processor expects a structlog logger
    foreign_processors = [p for p in common_processors if p != structlog.stdlib.filter_by_level]
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=_get_log_renderer(),  # This handles final rendering for both structlog and stdlib loggers
            foreign_pre_chain=foreign_processors,
        )
    )

    # Configure the root logger to use our structlog handler
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # Remove any existing handlers
    root_logger.addHandler(stream_handler)

    # Set log level based on LOG_LEVEL environment variable, default to INFO
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()  # TODO: make this a config option
    numeric_log_level = getattr(logging, log_level, logging.INFO)
    root_logger.setLevel(numeric_log_level)

    # Also update the uvicorn logger levels to match if we're in DEBUG mode
    if numeric_log_level <= logging.DEBUG:
        for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
            uvicorn_logger = logging.getLogger(logger_name)
            if uvicorn_logger.level > numeric_log_level:
                uvicorn_logger.setLevel(numeric_log_level)

    # Force our handler on loggers that have their own handlers
    # This catches JWT/library loggers that bypass the root logger, but allows tests to snoop on logs
    for _, logger in logging.Logger.manager.loggerDict.items():
        if isinstance(logger, logging.Logger) and logger.handlers:
            logger.handlers.clear()
            logger.addHandler(stream_handler)
            logger.propagate = False  # Prevent duplicate logs


# Initialize structlog configuration when module is imported
configure_logging()


def add_log_context(**kwargs: Any) -> None:
    """Add values to the logging context. Simple wrapper for structlog's contextvars.

    Args:
        **kwargs: Key-value pairs to add to the logging context
    """
    structlog.contextvars.bind_contextvars(**kwargs)


def remove_log_context(*keys: str) -> None:
    """Remove values from the logging context. Simple wrapper for structlog's contextvars.
    Args:
        *keys: Keys to remove from the logging context
    """
    structlog.contextvars.unbind_contextvars(*keys)


def clear_log_context() -> None:
    """Clear all values from the logging context.

    Useful for ensuring a clean context at the start of a new request.
    """
    structlog.contextvars.clear_contextvars()


# Type alias for structlog's bound_contextvars return type
LogContext = structlog.contextvars.bound_contextvars


def get_logger(name: str, **kwargs: Any) -> structlog.BoundLogger:
    """Get a logger instance. Wrapper around structlog.get_logger for convenience.

    Args:
        name: Logger name (usually __name__ from the calling module)

    Example:
        ```python
        from src.utils.logging import get_logger, add_log_context, LogContext

        # Set context that persists across the async context
        add_log_context(tenant_id="abc123")

        # Get a logger with bound context
        logger = get_logger(__name__, component="search")
        logger.info("Starting")  # Includes tenant_id and component
        ```
    """
    # Get the base logger
    logger = structlog.get_logger(name, **kwargs)
    return logger


def get_uvicorn_log_config() -> dict[str, Any]:
    """Get Uvicorn logging configuration that matches our structlog format.

    This configuration ensures that Uvicorn's access logs and other logs
    use the same format as our application logs (structured logging with
    proper timestamps and formatting).

    Returns:
        Dictionary containing Uvicorn logging configuration
    """
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": _get_log_renderer(),
                "foreign_pre_chain": [
                    structlog.stdlib.add_log_level,
                    structlog.stdlib.add_logger_name,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.EventRenamer(
                        "message"
                    ),  # Rename 'event' to 'message' for New Relic
                ],
            },
        },
        "handlers": {
            "default": {
                "formatter": "default",
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            # Configure the root logger to use our handler
            "": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            # Configure Uvicorn-specific loggers
            "uvicorn": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
        },
    }
