"""Main CLI for connector management."""

import asyncio
import csv
import json
from typing import Any

import asyncpg
import questionary
import typer
from rich.console import Console
from rich.table import Table

from connectors.cli.health_checks import run_health_check
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.database.connector_installations import ConnectorInstallationsRepository
from src.utils.config import get_config_value

app = typer.Typer(
    help="Connector management and statistics",
    add_completion=False,
)
console = Console()


async def get_connector_stats(
    tenant_id: str | None = None,
    status: str | None = None,
    all_statuses: bool = False,
) -> list[dict]:
    """Query connector installation statistics from the database."""
    database_url = get_config_value("CONTROL_DATABASE_URL")
    conn = await asyncpg.connect(database_url)

    try:
        if all_statuses:
            # Group by type and status
            query = """
                SELECT type, status, COUNT(*) as count
                FROM connector_installations
                WHERE ($1::text IS NULL OR tenant_id = $1)
                GROUP BY type, status
                ORDER BY count DESC, type, status
            """
            rows = await conn.fetch(query, tenant_id)
            return [
                {
                    "type": row["type"],
                    "status": row["status"],
                    "count": row["count"],
                }
                for row in rows
            ]
        else:
            # Group by type only, with status filter
            status_filter = status or "active"
            query = """
                SELECT type, COUNT(*) as count
                FROM connector_installations
                WHERE status = $1
                AND ($2::text IS NULL OR tenant_id = $2)
                GROUP BY type
                ORDER BY count DESC, type
            """
            rows = await conn.fetch(query, status_filter, tenant_id)
            return [
                {
                    "type": row["type"],
                    "count": row["count"],
                    "status": status_filter,
                }
                for row in rows
            ]
    finally:
        await conn.close()


@app.command()
def stats(
    tenant_id: str | None = typer.Option(
        None,
        "--tenant-id",
        "-t",
        help="Filter to specific tenant ID",
    ),
    status: str | None = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status (default: active)",
    ),
    all_statuses: bool = typer.Option(
        False,
        "--all-statuses",
        "-a",
        help="Show breakdown by all status types",
    ),
) -> None:
    """Show statistics about connector installations."""
    try:
        results = asyncio.run(get_connector_stats(tenant_id, status, all_statuses))

        if not results:
            console.print("ℹ️  No connector installations found", style="yellow")
            return

        # Create table
        if all_statuses:
            table = Table()
            table.add_column("Connector Type", style="cyan")
            table.add_column("Status", style="magenta")
            table.add_column("Count", justify="right", style="green")

            total = 0
            for result in results:
                table.add_row(
                    result["type"],
                    result["status"],
                    str(result["count"]),
                )
                total += result["count"]

            table.add_section()
            table.add_row("TOTAL", "", str(total), style="bold")
        else:
            table = Table()
            table.add_column("Connector Type", style="cyan")
            table.add_column("Count", justify="right", style="green")

            total = 0
            for result in results:
                table.add_row(
                    result["type"],
                    str(result["count"]),
                )
                total += result["count"]

            table.add_section()
            table.add_row("TOTAL", str(total), style="bold")

        console.print(table)

    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1)


@app.command()
def health(
    tenant_id: str = typer.Option(
        None,
        "--tenant-id",
        "-t",
        help="Tenant ID to check health for. If not provided, checks all tenants.",
    ),
    output_csv: str = typer.Option(
        None,
        "--csv",
        help="Save results to CSV file at the specified path.",
    ),
) -> None:
    """Check health of all connector installations for a tenant (or all tenants)."""
    try:
        if tenant_id:
            # Single tenant mode
            results = asyncio.run(_run_health_checks(tenant_id))
            if not results:
                console.print("No connector installations found for this tenant", style="yellow")
                return
            _print_health_table(tenant_id, results)
            if output_csv:
                _save_health_csv({tenant_id: results}, output_csv)
        else:
            # All tenants mode - single table with tenant separator rows
            all_results = asyncio.run(_run_health_checks_all_tenants())
            if not all_results:
                console.print("No connector installations found", style="yellow")
                return
            _print_all_tenants_health_table(all_results)
            if output_csv:
                _save_health_csv(all_results, output_csv)

    except Exception as e:
        console.print(f"Error: {e}", style="red")
        raise typer.Exit(1)


def _print_health_table(tenant_id: str, results: list[dict]) -> None:
    """Print a health check results table for a single tenant."""
    table = Table(title=f"Connector Health for tenant: {tenant_id}")
    table.add_column("Type", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("External ID")
    table.add_column("Healthy", justify="center")
    table.add_column("Message")

    for result in results:
        healthy_display = "OK" if result["healthy"] else ("FAIL" if result["checked"] else "-")
        healthy_style = "green" if result["healthy"] else ("red" if result["checked"] else "dim")
        table.add_row(
            result["type"],
            result["status"],
            result["external_id"],
            f"[{healthy_style}]{healthy_display}[/{healthy_style}]",
            result["message"],
        )

    console.print(table)


def _print_all_tenants_health_table(all_results: dict[str, list[dict]]) -> None:
    """Print a single table with all tenants, showing tenant ID on first row of each group."""
    table = Table(title="Connector Health - All Tenants")
    table.add_column("Tenant", style="yellow bold", no_wrap=True)
    table.add_column("Type", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("External ID")
    table.add_column("Healthy", justify="center")
    table.add_column("Message")

    for tid, results in all_results.items():
        for result in results:
            healthy_display = "OK" if result["healthy"] else ("FAIL" if result["checked"] else "-")
            healthy_style = (
                "green" if result["healthy"] else ("red" if result["checked"] else "dim")
            )
            table.add_row(
                tid,
                result["type"],
                result["status"],
                result["external_id"],
                f"[{healthy_style}]{healthy_display}[/{healthy_style}]",
                result["message"],
            )

    console.print(table)


def _save_health_csv(all_results: dict[str, list[dict]], filepath: str) -> None:
    """Save health check results to a CSV file."""
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["tenant_id", "type", "status", "external_id", "healthy", "message"])

        for tenant_id, results in all_results.items():
            for result in results:
                healthy_value = (
                    "OK" if result["healthy"] else ("FAIL" if result["checked"] else "SKIP")
                )
                writer.writerow(
                    [
                        tenant_id,
                        result["type"],
                        result["status"],
                        result["external_id"],
                        healthy_value,
                        result["message"],
                    ]
                )

    console.print(f"Saved CSV to: {filepath}", style="green")


async def _run_health_checks(tenant_id: str) -> list[dict]:
    """Run health checks for all connectors of a tenant."""
    repo = ConnectorInstallationsRepository()
    connectors = await repo.get_by_tenant(tenant_id)

    if not connectors:
        return []

    ssm_client = SSMClient()
    results = []

    # Run health checks concurrently
    async def check_connector(connector):
        result = await run_health_check(tenant_id, connector, ssm_client)
        return {
            "type": connector.type,
            "status": connector.status,
            "external_id": connector.external_id,
            "healthy": result.healthy,
            "checked": connector.status not in ("pending", "disconnected")
            and "Not implemented" not in result.message,
            "message": result.message,
        }

    results = await asyncio.gather(*[check_connector(c) for c in connectors])
    return list(results)


async def _run_health_checks_all_tenants() -> dict[str, list[dict]]:
    """Run health checks for all tenants with connectors."""
    repo = ConnectorInstallationsRepository()
    tenant_ids = await repo.get_all_tenant_ids_with_connectors()

    if not tenant_ids:
        return {}

    all_results: dict[str, list[dict]] = {}
    for tenant_id in tenant_ids:
        console.print(f"Checking tenant: {tenant_id}...", style="dim")
        results = await _run_health_checks(tenant_id)
        if results:
            all_results[tenant_id] = results

    return all_results


# Backfill connector registry - maps connector type to config class
# Lazy import to avoid circular imports
def _get_backfill_registry() -> dict[str, dict[str, Any]]:
    """Get the backfill connector registry with config classes."""
    from connectors.asana import AsanaFullBackfillConfig
    from connectors.attio.attio_models import AttioBackfillRootConfig
    from connectors.confluence.confluence_models import ConfluenceApiBackfillRootConfig
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
    from connectors.notion.notion_models import NotionApiBackfillRootConfig
    from connectors.salesforce.salesforce_models import SalesforceBackfillRootConfig
    from connectors.slack.slack_models import SlackExportBackfillRootConfig
    from connectors.trello.trello_models import TrelloApiBackfillRootConfig
    from connectors.zendesk import ZendeskFullBackfillConfig

    return {
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
            "installation_type": "github",  # Maps to github connector installation
        },
        "google_drive": {
            "name": "Google Drive",
            "config_class": GoogleDriveDiscoveryConfig,
            "requires_config": False,
            "description": "Backfill files from Google Drive",
        },
        "google_email": {
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
            "description": "Backfill all HubSpot objects",
        },
        "salesforce": {
            "name": "Salesforce",
            "config_class": SalesforceBackfillRootConfig,
            "requires_config": False,
            "description": "Backfill all Salesforce objects",
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
            "description": "Backfill tickets from Zendesk",
        },
        "asana": {
            "name": "Asana",
            "config_class": AsanaFullBackfillConfig,
            "requires_config": False,
            "description": "Backfill tasks from Asana",
        },
        "intercom": {
            "name": "Intercom",
            "config_class": IntercomApiBackfillRootConfig,
            "requires_config": False,
            "description": "Backfill all Intercom data",
        },
        "fireflies": {
            "name": "Fireflies",
            "config_class": FirefliesFullBackfillConfig,
            "requires_config": False,
            "description": "Backfill transcripts from Fireflies",
            "installation_type": "fireflies",
        },
        "gitlab": {
            "name": "GitLab",
            "config_class": GitLabBackfillRootConfig,
            "requires_config": True,
            "config_example": {"projects": ["group/project1", "group/project2"]},
            "description": "Backfill MRs and code from GitLab (use 'projects' OR 'groups' to scope)",
        },
    }


async def _get_tenant_connector_types(tenant_id: str) -> list[str]:
    """Get connector types installed for a tenant."""
    repo = ConnectorInstallationsRepository()
    connectors = await repo.get_by_tenant(tenant_id)
    return list({c.type for c in connectors})


def _get_backfill_choices_for_tenant(
    installed_types: list[str], registry: dict[str, dict[str, Any]]
) -> list[questionary.Choice]:
    """Build questionary choices filtered by tenant's installed connectors."""
    choices = []
    for key, info in registry.items():
        # Check if this backfill type matches an installed connector
        # Some backfill types map to different installation types (e.g., github_code -> github)
        installation_type = info.get("installation_type", key)
        if installation_type not in installed_types:
            continue

        config_marker = " [requires config]" if info["requires_config"] else ""
        choice_text = f"{info['name']}{config_marker}"
        choices.append(questionary.Choice(title=choice_text, value=key))

    return choices


@app.command()
def backfill(
    tenant_id: str = typer.Option(
        ..., "--tenant-id", "-t", help="Tenant ID to backfill connector for"
    ),
    connector_key: str | None = typer.Option(
        None,
        "--connector",
        help="Connector key to backfill (if not provided, interactive selection)",
    ),
    config_file: str | None = typer.Option(
        None,
        "--config-file",
        "-c",
        help="Path to JSON config file for connectors that require additional configuration",
    ),
) -> None:
    """Interactive backfill tool - only shows connectors installed for the tenant."""
    registry = _get_backfill_registry()

    # Get installed connector types for this tenant
    installed_types = asyncio.run(_get_tenant_connector_types(tenant_id))

    if not installed_types:
        console.print(f"[yellow]No connectors installed for tenant {tenant_id}[/yellow]")
        raise typer.Exit(1)

    console.print()
    console.print(f"[bold blue]Backfill CLI[/bold blue] - Tenant: [cyan]{tenant_id}[/cyan]")

    # If connector not specified, show interactive selection
    if not connector_key:
        choices = _get_backfill_choices_for_tenant(installed_types, registry)

        if not choices:
            console.print("[yellow]No backfill options available for installed connectors[/yellow]")
            raise typer.Exit(1)

        connector_key = questionary.select(
            "Select a connector to backfill:",
            choices=choices,
            use_arrow_keys=True,
        ).ask()

        if connector_key is None:
            console.print("[yellow]Selection cancelled.[/yellow]")
            raise typer.Exit(0)

    # Validate connector key
    if connector_key not in registry:
        console.print(f"[red]Unknown connector: {connector_key}[/red]")
        raise typer.Exit(1)

    connector_info = registry[connector_key]

    # Check if connector is installed (for non-interactive mode)
    installation_type = connector_info.get("installation_type", connector_key)
    if installation_type not in installed_types:
        console.print(
            f"[red]Connector '{connector_key}' is not installed for tenant {tenant_id}[/red]"
        )
        console.print(f"[dim]Installed connectors: {', '.join(installed_types)}[/dim]")
        raise typer.Exit(1)

    console.print(f"\n[green]Selected: {connector_info['name']}[/green]")
    console.print(f"[dim]{connector_info['description']}[/dim]\n")

    # Handle config file
    config_data: dict[str, Any] = {}
    if config_file:
        try:
            with open(config_file) as f:
                config_data = json.load(f)
            console.print(f"[green]Loaded config from {config_file}[/green]")
        except FileNotFoundError:
            console.print(f"[red]Config file not found: {config_file}[/red]")
            raise typer.Exit(1)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON in config file: {e}[/red]")
            raise typer.Exit(1)
    elif connector_info["requires_config"]:
        console.print("\n[yellow]This connector requires a config file.[/yellow]")
        if "config_example" in connector_info:
            console.print("[dim]Example config:[/dim]")
            console.print(json.dumps(connector_info["config_example"], indent=2))
        console.print("\n[red]Please provide a config file with --config-file[/red]")
        raise typer.Exit(1)

    # Run backfill
    async def _do_backfill() -> None:
        console.print(f"[blue]Starting backfill for {connector_info['name']}...[/blue]")

        config_class = connector_info["config_class"]
        try:
            config = config_class(
                tenant_id=tenant_id,
                suppress_notification=True,
                **config_data,
            )
        except Exception as e:
            console.print(f"[red]Failed to create config: {e}[/red]")
            raise typer.Exit(1)

        sqs_client = SQSClient()
        try:
            await sqs_client.send_backfill_ingest_message(config)
            console.print(
                f"[green]✅ Successfully sent backfill message for {connector_info['name']}[/green]"
            )
            console.print(f"[dim]Tenant: {tenant_id}[/dim]")
        except Exception as e:
            console.print(f"[red]❌ Failed to send backfill message: {e}[/red]")
            raise typer.Exit(1)

    asyncio.run(_do_backfill())


if __name__ == "__main__":
    app()
