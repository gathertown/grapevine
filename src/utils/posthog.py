"""PostHog Analytics Client for Python Services

Provides PostHog tracking functionality for Python services in the Grapevine platform.
This module handles event tracking and person property management for backend services.
"""

from __future__ import annotations

import os
from typing import Any

import posthog

from src.utils.logging import get_logger

logger = get_logger(__name__)


class PostHogService:
    """PostHog service for tracking events and person properties from Python services."""

    def __init__(self, api_key: str | None = None, host: str | None = None):
        """Initialize the PostHog service.

        Args:
            api_key: PostHog API key. If not provided, will try to get from VITE_POSTHOG_API_KEY env var.
            host: PostHog host URL. If not provided, will try to get from VITE_POSTHOG_HOST env var.
        """
        self._api_key = api_key or os.environ.get("VITE_POSTHOG_API_KEY")
        self._host = host or os.environ.get("VITE_POSTHOG_HOST", "https://us.i.posthog.com")
        self._is_initialized = False

        if self._api_key:
            self._initialize()
        else:
            logger.warning("No PostHog API key provided, tracking will be disabled")

    def _initialize(self) -> None:
        """Initialize the PostHog client."""
        if self._is_initialized:
            return

        try:
            posthog.api_key = self._api_key
            posthog.host = self._host
            self._is_initialized = True
            logger.info(f"PostHog client initialized successfully with host {self._host}")
        except Exception as e:
            logger.error(f"Failed to initialize PostHog client: {e}")
            self._is_initialized = False

    @property
    def is_initialized(self) -> bool:
        """Check if the service is properly initialized."""
        return self._is_initialized

    def set(self, distinct_id: str, properties: dict[str, Any]) -> None:
        """Set person properties for a user.

        Args:
            distinct_id: The distinct ID (typically tenant_id for our use case)
            properties: Dictionary of person properties to set
        """
        if not self.is_initialized:
            logger.warning("PostHog client not initialized, skipping set call")
            return

        try:
            # Always add source=backend to identify these as backend-originated person properties
            properties_with_source = {
                **properties,
                "source": "backend",
            }

            posthog.set(distinct_id=distinct_id, properties=properties_with_source)

            logger.info(
                f"Successfully set person properties for {distinct_id}",
                extra={"distinct_id": distinct_id, "properties": properties_with_source},
            )

        except Exception as e:
            logger.error(
                f"Failed to set person properties for {distinct_id}: {e}",
                extra={"distinct_id": distinct_id, "properties": properties},
            )

    def capture(
        self,
        distinct_id: str,
        event: str,
        properties: dict[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Capture an event for a user.

        Args:
            distinct_id: The distinct ID (typically tenant_id for our use case)
            event: Name of the event to capture
            properties: Optional dictionary of event properties
            timestamp: Optional ISO 8601 timestamp to backdate the event (e.g., "2025-01-15T12:00:00Z")
        """
        if not self.is_initialized:
            logger.warning("PostHog client not initialized, skipping capture call")
            return

        try:
            if timestamp:
                posthog.capture(
                    event=event,
                    distinct_id=distinct_id,
                    properties=properties or {},
                    timestamp=timestamp,
                )
            else:
                posthog.capture(event=event, distinct_id=distinct_id, properties=properties or {})

            logger.info(
                f"Successfully captured event {event} for {distinct_id}",
                extra={
                    "event": event,
                    "distinct_id": distinct_id,
                    "properties": properties,
                    "timestamp": timestamp,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to capture event {event} for {distinct_id}: {e}",
                extra={
                    "event": event,
                    "distinct_id": distinct_id,
                    "properties": properties,
                    "timestamp": timestamp,
                },
            )

    def flush(self) -> None:
        """Flush any pending events."""
        if not self.is_initialized:
            return

        try:
            posthog.flush()
            logger.debug("Successfully flushed PostHog events")
        except Exception as e:
            logger.error(f"Failed to flush PostHog events: {e}")


# Global service instance
_posthog_service: PostHogService | None = None


def get_posthog_service() -> PostHogService:
    """Get the global PostHog service instance."""
    global _posthog_service
    if _posthog_service is None:
        _posthog_service = PostHogService()
    return _posthog_service
