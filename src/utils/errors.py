"""
Error collection utilities for tracking and analyzing errors across agent runs.
"""

import contextvars
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Literal

ErrorType = Literal[
    "openai_timeout",
    "openai_guideline_violation",
    "openai_api_error",
    "tool_timeout",
    "tool_execution_error",
    "mcp_connection_error",
    "mcp_server_error",
    "agent_timeout",
    "question_timeout",
    "unknown_error",
]


@dataclass
class ErrorEvent:
    """Structured error event for tracking and analysis."""

    error_type: ErrorType
    timestamp: str
    error_message: str
    context: dict[str, Any]
    raw_error: str

    @classmethod
    def create(
        cls,
        error_type: ErrorType,
        error_message: str,
        exception: Exception,
        tool_name: str | None = None,
        attempt_count: int | None = None,
        timeout_duration: float | None = None,
        **extra_context,
    ) -> "ErrorEvent":
        """Create an ErrorEvent with standardized context."""
        context = {}

        if tool_name:
            context["tool_name"] = tool_name
        if attempt_count:
            context["attempt_count"] = attempt_count  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
        if timeout_duration:
            context["timeout_duration"] = timeout_duration  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

        # Add any extra context
        context.update(extra_context)

        return cls(
            error_type=error_type,
            timestamp=datetime.now(UTC).isoformat(),
            error_message=error_message,
            context=context,
            raw_error=str(exception),
        )


class ErrorCollector:
    """Thread-safe error collector for tracking errors during agent runs."""

    def __init__(self, question_id: Any | None = None):
        self._errors: list[ErrorEvent] = []
        self._lock = threading.Lock()
        self._question_id = question_id

    def add_error(
        self,
        error_type: ErrorType,
        error_message: str,
        exception: Exception,
        tool_name: str | None = None,
        attempt_count: int | None = None,
        timeout_duration: float | None = None,
        **extra_context,
    ) -> None:
        """Add an error to the collection in a thread-safe manner."""
        # Auto-include question_id if set on collector and not provided in extra_context
        if self._question_id is not None and "question_id" not in extra_context:
            extra_context["question_id"] = self._question_id

        error_event = ErrorEvent.create(
            error_type=error_type,
            error_message=error_message,
            exception=exception,
            tool_name=tool_name,
            attempt_count=attempt_count,
            timeout_duration=timeout_duration,
            **extra_context,
        )

        with self._lock:
            self._errors.append(error_event)

    def get_errors(self) -> list[dict[str, Any]]:
        """Get all collected errors as dictionaries."""
        with self._lock:
            return [asdict(error) for error in self._errors]

    def get_error_summary(self) -> dict[str, Any]:
        """Generate summary statistics for collected errors."""
        with self._lock:
            if not self._errors:
                return {
                    "total_errors": 0,
                    "error_types": {},
                    "error_tools": {},
                    "question_ids_with_errors": [],
                    "timeline": [],
                }

            # Count by type, tools, and collect question IDs
            error_types: dict[str, int] = {}
            error_tools: dict[str, int] = {}
            question_ids_with_errors = set()

            for error in self._errors:
                # Count by type
                error_types[error.error_type] = error_types.get(error.error_type, 0) + 1

                # Count by tool if applicable
                tool_name = error.context.get("tool_name")
                if tool_name:
                    error_tools[tool_name] = error_tools.get(tool_name, 0) + 1

                # Collect question ID if available
                question_id = error.context.get("question_id")
                if question_id is not None:
                    question_ids_with_errors.add(question_id)

            # Create timeline (simplified - just timestamps and types)
            timeline = [
                {
                    "timestamp": error.timestamp,
                    "error_type": error.error_type,
                    "question_id": error.context.get("question_id"),
                }
                for error in self._errors
            ]

            return {
                "total_errors": len(self._errors),
                "error_types": error_types,
                "error_tools": error_tools,
                "question_ids_with_errors": sorted(question_ids_with_errors),
                "timeline": timeline,
            }

    def clear(self) -> None:
        """Clear all collected errors."""
        with self._lock:
            self._errors.clear()

    def set_question_id(self, question_id: Any) -> None:
        """Set the question ID context for this collector."""
        self._question_id = question_id

    def has_errors(self) -> bool:
        """Check if any errors have been collected."""
        with self._lock:
            return len(self._errors) > 0


# Context variable to store per-task error collectors
_context_error_collector: contextvars.ContextVar[ErrorCollector | None] = contextvars.ContextVar(
    "error_collector", default=None
)

# Global fallback error collector instance
_global_error_collector = ErrorCollector()


def get_error_collector() -> ErrorCollector:
    """Get the current error collector instance (context-specific or global fallback)."""
    context_collector = _context_error_collector.get()
    if context_collector is not None:
        return context_collector
    return _global_error_collector


def set_context_error_collector(collector: ErrorCollector) -> None:
    """Set the error collector for the current context."""
    _context_error_collector.set(collector)


def reset_error_collector() -> None:
    """Reset the current error collector (context-specific or global)."""
    collector = get_error_collector()
    collector.clear()


# Convenience functions for common error scenarios
def collect_timeout_error(
    error_type: ErrorType,
    timeout_duration: float,
    exception: Exception,
    tool_name: str | None = None,
    **extra_context,
) -> None:
    """Convenience function to collect timeout errors."""
    get_error_collector().add_error(
        error_type=error_type,
        error_message=f"Operation timed out after {timeout_duration}s",
        exception=exception,
        tool_name=tool_name,
        timeout_duration=timeout_duration,
        **extra_context,
    )


def collect_openai_error(
    exception: Exception, attempt_count: int | None = None, **extra_context
) -> None:
    """Convenience function to collect OpenAI API errors."""
    if (
        "invalid_prompt" in str(exception).lower()
        and "flagged as potentially violating our usage policy" in str(exception).lower()
    ):
        error_type = "openai_guideline_violation"
    else:
        error_type = "openai_api_error"

    get_error_collector().add_error(
        error_type=error_type,  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
        error_message=f"OpenAI API error: {str(exception)[:200]}",
        exception=exception,
        attempt_count=attempt_count,
        **extra_context,
    )


def collect_mcp_error(exception: Exception, tool_name: str | None = None, **extra_context) -> None:
    """Convenience function to collect MCP-related errors."""
    error_str = str(exception).lower()
    if any(keyword in error_str for keyword in ["not connected"]):
        # e.g. "Client is not connected..." errors
        error_type = "mcp_connection_error"
    else:
        error_type = "tool_execution_error"

    get_error_collector().add_error(
        error_type=error_type,  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
        error_message=f"MCP/tool error: {str(exception)[:200]}",
        exception=exception,
        tool_name=tool_name,
        **extra_context,
    )
