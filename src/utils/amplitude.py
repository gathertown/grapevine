"""Amplitude Analytics Client for Python Services

Provides Amplitude tracking functionality for Python services in the Grapevine platform.
This module handles event tracking and user identification for backend services.
"""

from __future__ import annotations

import os
from typing import Any

from amplitude import Amplitude, BaseEvent, EventOptions, Identify

from src.utils.logging import get_logger

logger = get_logger(__name__)


class AmplitudeService:
    """Amplitude service for tracking events and user identification from Python services."""

    def __init__(self, api_key: str | None = None):
        """Initialize the Amplitude service.

        Args:
            api_key: Amplitude API key. If not provided, will try to get from VITE_AMPLITUDE_API_KEY env var.
        """
        self._api_key = api_key or os.environ.get("VITE_AMPLITUDE_API_KEY")
        self._client: Amplitude | None = None
        self._is_initialized = False

        if self._api_key:
            self._initialize()
        else:
            logger.warning("No Amplitude API key provided, tracking will be disabled")

    def _initialize(self) -> None:
        """Initialize the Amplitude client."""
        if self._is_initialized:
            return

        try:
            self._client = Amplitude(self._api_key)
            self._is_initialized = True
            logger.info("Amplitude client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Amplitude client: {e}")
            self._client = None

    @property
    def is_initialized(self) -> bool:
        """Check if the service is properly initialized."""
        return self._is_initialized and self._client is not None

    def identify(self, user_id: str, user_properties: dict[str, Any]) -> None:
        """Identify a user with their properties.

        Args:
            user_id: The user ID (typically tenant_id for our use case)
            user_properties: Dictionary of user properties to set
        """
        if not self.is_initialized or self._client is None:
            logger.warning("Amplitude client not initialized, skipping identify call")
            return

        try:
            identify_event = Identify()

            # Set all user properties
            for key, value in user_properties.items():
                identify_event.set(key, value)

            # Create event options with user_id
            event_options = EventOptions(user_id=user_id)

            # Send identify event
            self._client.identify(identify_event, event_options)

            logger.info(
                f"Successfully identified user {user_id} with properties",
                extra={"user_id": user_id, "properties": user_properties},
            )

        except Exception as e:
            logger.error(
                f"Failed to identify user {user_id}: {e}",
                extra={"user_id": user_id, "properties": user_properties},
            )

    def track_event(
        self, event_name: str, user_id: str, event_properties: dict[str, Any] | None = None
    ) -> None:
        """Track an event for a user.

        Args:
            event_name: Name of the event to track
            user_id: The user ID (typically tenant_id for our use case)
            event_properties: Optional dictionary of event properties
        """
        if not self.is_initialized or self._client is None:
            logger.warning("Amplitude client not initialized, skipping track event")
            return

        try:
            event = BaseEvent(
                event_type=event_name, user_id=user_id, event_properties=event_properties or {}
            )

            self._client.track(event)

            logger.info(
                f"Successfully tracked event {event_name} for user {user_id}",
                extra={
                    "event_name": event_name,
                    "user_id": user_id,
                    "properties": event_properties,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to track event {event_name} for user {user_id}: {e}",
                extra={
                    "event_name": event_name,
                    "user_id": user_id,
                    "properties": event_properties,
                },
            )

    def flush(self) -> None:
        """Flush any pending events."""
        if not self.is_initialized or self._client is None:
            return

        try:
            self._client.flush()
            logger.debug("Successfully flushed Amplitude events")
        except Exception as e:
            logger.error(f"Failed to flush Amplitude events: {e}")


# Global service instance
_amplitude_service: AmplitudeService | None = None


def get_amplitude_service() -> AmplitudeService:
    """Get the global Amplitude service instance."""
    global _amplitude_service
    if _amplitude_service is None:
        _amplitude_service = AmplitudeService()
    return _amplitude_service
