#!/usr/bin/env python3
"""Backfill CLI tool for all connectors.

This script provides an interactive interface to backfill any connector
for a specific tenant across different environments (local, staging, production).
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import questionary
import typer
from rich.console import Console

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from connectors.asana import AsanaFullBackfillConfig
from connectors.attio.attio_models import AttioBackfillRootConfig
from connectors.canva.canva_models import CanvaBackfillRootConfig, CanvaIncrementalBackfillConfig
from connectors.clickup import ClickupFullBackfillConfig
from connectors.confluence.confluence_models import ConfluenceApiBackfillRootConfig
from connectors.figma.figma_models import FigmaBackfillRootConfig, FigmaIncrementalBackfillConfig
from connectors.fireflies import FirefliesFullBackfillConfig
from connectors.gather.gather_models import GatherApiBackfillRootConfig
from connectors.github.github_models import (
    GitHubFileBackfillRootConfig,
    GitHubPRBackfillRootConfig,
)
from connectors.gitlab.gitlab_models import GitLabBackfillRootConfig
from connectors.gmail.gmail_models import GoogleEmailDiscoveryConfig
from connectors.gong.gong_models import GongCallBackfillRootConfig
from connectors.google_drive.google_drive_models import GoogleDriveDiscoveryConfig
from connectors.hubspot.hubspot_models import HubSpotBackfillRootConfig
from connectors.intercom.intercom_models import IntercomApiBackfillRootConfig
from connectors.jira.jira_models import JiraApiBackfillRootConfig
from connectors.linear.linear_models import LinearApiBackfillRootConfig
from connectors.monday.monday_job_models import MondayBackfillRootConfig
from connectors.notion.notion_models import NotionApiBackfillRootConfig
from connectors.pipedrive.pipedrive_models import PipedriveBackfillRootConfig
from connectors.posthog.posthog_models import PostHogBackfillRootConfig
from connectors.salesforce.salesforce_models import SalesforceBackfillRootConfig
from connectors.slack.slack_models import SlackExportBackfillRootConfig
from connectors.teamwork.teamwork_backfill_config import TeamworkBackfillRootConfig
from connectors.trello.trello_models import TrelloApiBackfillRootConfig
from connectors.zendesk import ZendeskFullBackfillConfig
from src.clients.sqs import SQSClient
from src.utils.logging import get_logger

app = typer.Typer(help="Interactive backfill tool for all connectors")
console = Console()
logger = get_logger(__name__)


# Connector registry with metadata for interactive selection
CONNECTORS = {
    "attio": {
        "name": "Attio",
        "config_class": AttioBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill all Attio objects (companies, people, deals)",
    },
    "github": {
        "name": "GitHub PRs",
        "config_class": GitHubPRBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill pull requests from GitHub repositories",
    },
    "github_code": {
        "name": "GitHub Code Files",
        "config_class": GitHubFileBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill code files from GitHub repositories",
    },
    "google_drive": {
        "name": "Google Drive",
        "config_class": GoogleDriveDiscoveryConfig,
        "requires_config": False,
        "description": "Backfill files from Google Drive (user drives and shared drives)",
    },
    "gmail": {
        "name": "Gmail",
        "config_class": GoogleEmailDiscoveryConfig,
        "requires_config": False,
        "description": "Backfill email messages from Gmail",
    },
    "slack": {
        "name": "Slack",
        "config_class": SlackExportBackfillRootConfig,
        "requires_config": True,
        "config_example": {"s3_uri": "s3://bucket-name/tenant-id/slack-export.zip"},
        "description": "Backfill messages from Slack export file (requires S3 URI)",
    },
    "linear": {
        "name": "Linear",
        "config_class": LinearApiBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill issues from Linear",
    },
    "monday": {
        "name": "Monday.com",
        "config_class": MondayBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill items from Monday.com boards",
    },
    "notion": {
        "name": "Notion",
        "config_class": NotionApiBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill pages from Notion",
    },
    "hubspot": {
        "name": "HubSpot",
        "config_class": HubSpotBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill all HubSpot objects (deals, tickets, companies, contacts)",
    },
    "salesforce": {
        "name": "Salesforce",
        "config_class": SalesforceBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill all Salesforce objects (accounts, opportunities, cases, contacts, leads)",
    },
    "jira": {
        "name": "Jira",
        "config_class": JiraApiBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill issues from Jira",
    },
    "confluence": {
        "name": "Confluence",
        "config_class": ConfluenceApiBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill pages from Confluence",
    },
    "gong": {
        "name": "Gong",
        "config_class": GongCallBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill call recordings from Gong",
    },
    "gather": {
        "name": "Gather",
        "config_class": GatherApiBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill meetings from Gather",
    },
    "trello": {
        "name": "Trello",
        "config_class": TrelloApiBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill cards from Trello",
    },
    "zendesk": {
        "name": "Zendesk",
        "config_class": ZendeskFullBackfillConfig,
        "requires_config": False,
        "description": "Backfill tickets from Zendesk (full backfill by default)",
    },
    "asana": {
        "name": "Asana",
        "config_class": AsanaFullBackfillConfig,
        "requires_config": False,
        "description": "Backfill tasks from Asana (full backfill by default)",
    },
    "intercom": {
        "name": "Intercom",
        "config_class": IntercomApiBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill all Intercom data (conversations, help center, contacts, companies)",
    },
    "fireflies": {
        "name": "Fireflies",
        "config_class": FirefliesFullBackfillConfig,
        "requires_config": False,
        "description": "Backfill transcripts from Fireflies (full backfill by default)",
    },
    "gitlab": {
        "name": "GitLab",
        "config_class": GitLabBackfillRootConfig,
        "requires_config": True,
        "config_example": {"projects": ["group/project1", "group/project2"]},
        "description": "Backfill MRs and code from GitLab (use 'projects' OR 'groups' to scope)",
    },
    "clickup": {
        "name": "ClickUp",
        "config_class": ClickupFullBackfillConfig,
        "requires_config": False,
        "description": "Backfill tasks and permissions from ClickUp",
    },
    "pipedrive": {
        "name": "Pipedrive",
        "config_class": PipedriveBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill all Pipedrive objects (deals, persons, organizations, products)",
    },
    "figma": {
        "name": "Figma",
        "config_class": FigmaBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill all Figma design files and comments from selected teams",
    },
    "figma-incremental": {
        "name": "Figma (Incremental)",
        "config_class": FigmaIncrementalBackfillConfig,
        "requires_config": False,
        "description": "Incremental sync of Figma files modified since last sync",
    },
    "posthog": {
        "name": "PostHog",
        "config_class": PostHogBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill all PostHog data (dashboards, insights, feature flags, experiments, surveys, annotations)",
    },
    "canva": {
        "name": "Canva",
        "config_class": CanvaBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill all Canva designs from the connected user account",
    },
    "canva-incremental": {
        "name": "Canva (Incremental)",
        "config_class": CanvaIncrementalBackfillConfig,
        "requires_config": False,
        "description": "Incremental sync of Canva designs modified since last sync",
    },
    "teamwork": {
        "name": "Teamwork",
        "config_class": TeamworkBackfillRootConfig,
        "requires_config": False,
        "description": "Backfill tasks from Teamwork projects",
    },
}


def check_environment() -> None:
    """Check that required environment variables are set."""
    required_vars = [
        "INGEST_JOBS_QUEUE_ARN",
        "AWS_REGION",
    ]

    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)

    if missing_vars:
        console.print("[red]Missing required environment variables:[/red]")
        for var in missing_vars:
            console.print(f"[red]  - {var}[/red]")
        sys.exit(1)


def get_connector_selection() -> str:
    """Prompt user to select a connector interactively and return the connector key."""
    # Build choices for questionary
    choices = []
    for key, info in CONNECTORS.items():
        config_marker = " [requires config]" if info["requires_config"] else ""
        choice_text = f"{info['name']}{config_marker}"
        choices.append(questionary.Choice(title=choice_text, value=key))

    # Use questionary for interactive arrow-key selection
    connector_key = questionary.select(
        "Select a connector to backfill:",
        choices=choices,
        use_arrow_keys=True,
        style=questionary.Style(
            [
                ("qmark", "fg:#673ab7 bold"),  # question mark
                ("question", "bold"),  # question text
                ("answer", "fg:#f44336 bold"),  # selected answer
                ("pointer", "fg:#673ab7 bold"),  # selection pointer
                ("highlighted", "fg:#673ab7 bold"),  # highlighted choice
                ("selected", "fg:#cc5454"),  # selected but not highlighted
            ]
        ),
    ).ask()

    if connector_key is None:
        console.print("[yellow]Selection cancelled.[/yellow]")
        sys.exit(0)

    return connector_key


def load_config_file(config_file_path: str) -> dict[str, Any]:
    """Load and parse a JSON config file."""
    try:
        with open(config_file_path) as f:
            config_data = json.load(f)
        console.print(f"[green]Loaded config from {config_file_path}[/green]")
        return config_data
    except FileNotFoundError:
        console.print(f"[red]Config file not found: {config_file_path}[/red]")
        sys.exit(1)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON in config file: {e}[/red]")
        sys.exit(1)


def prompt_for_config_file(connector_info: dict[str, Any]) -> dict[str, Any] | None:
    """Prompt user for config file path if connector requires it."""
    console.print("\n[yellow]This connector requires a config file.[/yellow]")

    if "config_example" in connector_info:
        console.print("[dim]Example config:[/dim]")
        console.print(json.dumps(connector_info["config_example"], indent=2))
        console.print()

    response = typer.prompt(
        "Enter config file path (or 'skip' to cancel)",
        default="skip",
    )

    if response.lower() == "skip":
        console.print("[yellow]Backfill cancelled.[/yellow]")
        sys.exit(0)

    return load_config_file(response)


@app.command()
def backfill(
    tenant_id: str = typer.Option(
        ..., "--tenant-id", "-t", help="Tenant ID to backfill connector for"
    ),
    env: str = typer.Option(
        "local",
        "--env",
        "-e",
        help="Environment to run in (local, staging, production)",
    ),
    connector_key: str | None = typer.Option(
        None,
        "--connector",
        help="Connector key to backfill (if not provided, interactive selection will be used)",
    ),
    config_file: str | None = typer.Option(
        None,
        "--config-file",
        "-c",
        help="Path to JSON config file for connectors that require additional configuration",
    ),
):
    """Interactive backfill tool for all connectors.

    Select a connector from the list and backfill it for the specified tenant.
    Some connectors may require additional configuration via a JSON file.
    """
    # Validate environment
    valid_envs = ["local", "staging", "production"]
    if env not in valid_envs:
        console.print(f"[red]Invalid environment: {env}[/red]")
        console.print(f"[red]Valid options: {', '.join(valid_envs)}[/red]")
        sys.exit(1)

    # Check required environment variables
    check_environment()

    # Display header
    console.print()
    console.print(
        f"[bold blue]Backfill CLI[/bold blue] - Tenant: [cyan]{tenant_id}[/cyan] | Environment: [yellow]{env}[/yellow]"
    )

    # Get connector selection
    connector_key = connector_key or get_connector_selection()
    connector_info = CONNECTORS[connector_key]

    console.print(f"\n[green]Selected: {connector_info['name']}[/green]")
    console.print(f"[dim]{connector_info['description']}[/dim]\n")

    # Handle config file
    config_data: dict[str, Any] = {}
    if config_file:
        config_data = load_config_file(config_file)
    elif connector_info["requires_config"]:
        result = prompt_for_config_file(connector_info)
        if result is not None:
            config_data = result

    # Run backfill
    async def _backfill():
        console.print(f"[blue]Starting backfill for {connector_info['name']}...[/blue]")

        # Instantiate config
        config_class = connector_info["config_class"]
        try:
            config = config_class(  # type: ignore[operator]
                tenant_id=tenant_id,
                suppress_notification=True,
                **config_data,
            )
        except Exception as e:
            console.print(f"[red]Failed to create config: {e}[/red]")
            sys.exit(1)

        # Send to SQS
        sqs_client = SQSClient()
        try:
            await sqs_client.send_backfill_ingest_message(config)
            console.print(
                f"[green]✅ Successfully sent backfill message for {connector_info['name']}[/green]"
            )
            console.print(f"[dim]Tenant: {tenant_id}[/dim]")
            console.print(f"[dim]Environment: {env}[/dim]")
        except Exception as e:
            console.print(f"[red]❌ Failed to send backfill message: {e}[/red]")
            sys.exit(1)

    asyncio.run(_backfill())


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    app()
