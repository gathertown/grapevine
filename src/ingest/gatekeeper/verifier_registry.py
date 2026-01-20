"""Webhook verifier registry and factory.

This module provides a centralized registry of webhook verifiers,
mapping source types to their verification handlers.
"""

from enum import Enum

from src.ingest.gatekeeper.verification import WebhookVerifier


class WebhookSourceType(str, Enum):
    """Valid webhook source types for the gatekeeper."""

    GITHUB = "github"
    SLACK = "slack"
    LINEAR = "linear"
    NOTION = "notion"
    GOOGLE_EMAIL = "google_email"
    GOOGLE_DRIVE = "google_drive"
    JIRA = "jira"
    CONFLUENCE = "confluence"
    GATHER = "gather"
    TRELLO = "trello"
    GONG = "gong"
    HUBSPOT = "hubspot"
    ATTIO = "attio"


def _build_verifier_registry() -> dict[WebhookSourceType, WebhookVerifier]:
    """Build the verifier registry lazily to avoid circular imports.

    Returns:
        Dictionary mapping source types to their verifier instances.
    """
    # Import verifiers here to avoid circular imports at module load time
    from connectors.attio import AttioWebhookVerifier
    from connectors.confluence import ConfluenceWebhookVerifier
    from connectors.gather import GatherWebhookVerifier
    from connectors.github import GitHubWebhookVerifier
    from connectors.gmail import GoogleEmailWebhookVerifier
    from connectors.gong import GongWebhookVerifier
    from connectors.google_drive import GoogleDriveWebhookVerifier
    from connectors.hubspot import HubSpotWebhookVerifier
    from connectors.jira import JiraWebhookVerifier
    from connectors.linear import LinearWebhookVerifier
    from connectors.notion import NotionWebhookVerifier
    from connectors.slack import SlackWebhookVerifier
    from connectors.trello import TrelloWebhookVerifier

    return {
        WebhookSourceType.GITHUB: GitHubWebhookVerifier(),
        WebhookSourceType.SLACK: SlackWebhookVerifier(),
        WebhookSourceType.LINEAR: LinearWebhookVerifier(),
        WebhookSourceType.NOTION: NotionWebhookVerifier(),
        WebhookSourceType.GOOGLE_EMAIL: GoogleEmailWebhookVerifier(),
        WebhookSourceType.GOOGLE_DRIVE: GoogleDriveWebhookVerifier(),
        WebhookSourceType.JIRA: JiraWebhookVerifier(),
        WebhookSourceType.CONFLUENCE: ConfluenceWebhookVerifier(),
        WebhookSourceType.GATHER: GatherWebhookVerifier(),
        WebhookSourceType.TRELLO: TrelloWebhookVerifier(),
        WebhookSourceType.GONG: GongWebhookVerifier(),
        WebhookSourceType.HUBSPOT: HubSpotWebhookVerifier(),
        WebhookSourceType.ATTIO: AttioWebhookVerifier(),
    }


# Lazily initialized registry
_verifier_registry: dict[WebhookSourceType, WebhookVerifier] | None = None


def get_verifier(source_type: WebhookSourceType | str) -> WebhookVerifier | None:
    """Get the verifier for a given source type.

    Args:
        source_type: The webhook source type (enum or string value)

    Returns:
        The verifier instance, or None if not found
    """
    global _verifier_registry
    if _verifier_registry is None:
        _verifier_registry = _build_verifier_registry()

    # Convert string to enum if needed
    if isinstance(source_type, str):
        try:
            source_type = WebhookSourceType(source_type)
        except ValueError:
            return None

    return _verifier_registry.get(source_type)


def get_all_source_types() -> list[WebhookSourceType]:
    """Get all registered webhook source types.

    Returns:
        List of all WebhookSourceType enum values
    """
    return list(WebhookSourceType)
