"""Pydantic models for Google Drive job configurations."""

from typing import Literal

from connectors.base.models import BackfillIngestConfig


class GoogleDriveDiscoveryConfig(BackfillIngestConfig, frozen=True):
    """Configuration for discovering Google Workspace users and shared drives."""

    source: Literal["google_drive_discovery"] = "google_drive_discovery"


class GoogleDriveUserDriveConfig(BackfillIngestConfig, frozen=True):
    """Configuration for processing a specific user's personal drive."""

    source: Literal["google_drive_user_drive"] = "google_drive_user_drive"
    user_email: str
    user_id: str


class GoogleDriveSharedDriveConfig(BackfillIngestConfig, frozen=True):
    """Configuration for processing a specific shared drive."""

    source: Literal["google_drive_shared_drive"] = "google_drive_shared_drive"
    drive_id: str
    drive_name: str


class GoogleDriveWebhookRefreshConfig(BackfillIngestConfig, frozen=True):
    """Configuration for refreshing Google Drive webhooks."""

    source: Literal["google_drive_webhook_refresh"] = "google_drive_webhook_refresh"
