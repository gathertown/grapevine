"""Pydantic models for Gmail job configurations."""

from typing import Literal

from connectors.base.models import BackfillIngestConfig


class GoogleEmailDiscoveryConfig(BackfillIngestConfig, frozen=True):
    """Configuration for discovering Google Workspace users and shared drives."""

    source: Literal["google_email_discovery"] = "google_email_discovery"


class GoogleEmailUserConfig(BackfillIngestConfig, frozen=True):
    """Configuration for processing a specific user's email."""

    source: Literal["google_email_user"] = "google_email_user"
    user_email: str
    user_id: str


class GoogleEmailWebhookRefreshConfig(BackfillIngestConfig, frozen=True):
    """Configuration for refreshing Google Email webhooks."""

    source: Literal["google_email_webhook_refresh"] = "google_email_webhook_refresh"
