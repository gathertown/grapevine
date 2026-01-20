"""PostHog API client module."""

from connectors.posthog.client.posthog_client import (
    PostHogAPIError,
    PostHogClient,
    get_posthog_client_for_tenant,
)

__all__ = [
    "PostHogClient",
    "PostHogAPIError",
    "get_posthog_client_for_tenant",
]
