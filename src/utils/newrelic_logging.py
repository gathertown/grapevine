"""New Relic logging integration helpers."""

from collections.abc import MutableMapping
from typing import Any

try:
    import newrelic.agent

    NEWRELIC_AVAILABLE = True
except ImportError:
    NEWRELIC_AVAILABLE = False


def newrelic_error_processor(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Processor that sends error-level logs to New Relic.

    This processor intercepts error-level logs and sends them to New Relic
    using notice_error. It passes through all log levels unchanged.

    Args:
        logger: The logger instance
        method_name: The logging method name (e.g., 'error', 'warning')
        event_dict: The log event dictionary

    Returns:
        The unmodified event dictionary
    """
    if NEWRELIC_AVAILABLE and method_name in ("error", "critical"):
        newrelic.agent.notice_error()

    return event_dict
