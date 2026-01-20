#!/usr/bin/env python3
"""
Dormant Tenant Management CLI

A tool for detecting, managing, and deleting dormant tenants that have been
provisioned but never set up any integrations.

Usage:
    uv run python -m src.dormant.cli scan          # Scan for dormant tenants (dry-run)
    uv run python -m src.dormant.cli scan --mark   # Scan and mark dormant tenants
    uv run python -m src.dormant.cli list          # List all dormant tenants
    uv run python -m src.dormant.cli inspect <id>  # Inspect a specific tenant
    uv run python -m src.dormant.cli delete <id>   # Delete a specific tenant
    uv run python -m src.dormant.cli purge         # Delete expired dormant tenants
"""

import asyncio
import csv
import json
from datetime import UTC, datetime
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.dormant.deletion import (
    DeletionResult,
    ResourceDiscoveryResult,
    cleanup_tenant_db_manager,
    discover_tenant_resources,
    hard_delete_tenant,
)
from src.dormant.service import (
    DormancyCheckResult,
    TenantInfo,
    get_dormant_days_threshold,
    get_dormant_tenants,
    get_expired_dormant_tenants,
    get_grace_period_days,
    get_tenant_info,
    inspect_tenant,
    scan_for_active_tenants,
    scan_for_dormant_tenants,
    unmark_tenant_dormant,
)
from src.utils.config import get_config_value

# Load environment variables
load_dotenv()

app = typer.Typer(
    name="dormant",
    help="Dormant tenant detection and management CLI",
    add_completion=False,
)
console = Console()


class OutputFormat(str, Enum):
    """Output format options."""

    TABLE = "table"
    JSON = "json"
    CSV = "csv"


def log_info(message: str) -> None:
    """Log info message with emoji."""
    console.print(f"ℹ️  {message}", style="blue")


def log_success(message: str) -> None:
    """Log success message with emoji."""
    console.print(f"✅ {message}", style="green")


def log_warning(message: str) -> None:
    """Log warning message with emoji."""
    console.print(f"⚠️  {message}", style="yellow")


def log_error(message: str) -> None:
    """Log error message with emoji."""
    console.print(f"❌ {message}", style="red")


def validate_environment() -> str:
    """Validate required environment variables."""
    control_db_url = get_config_value("CONTROL_DATABASE_URL")
    if not control_db_url:
        raise ValueError("CONTROL_DATABASE_URL environment variable is required")
    return control_db_url


def format_datetime(dt: datetime | None) -> str:
    """Format datetime for display."""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def days_since(dt: datetime | None) -> str:
    """Calculate days since datetime."""
    if dt is None:
        return "N/A"
    now = datetime.now(UTC)
    dt_utc = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt
    days = (now - dt_utc).days
    return f"{days} days"


def create_scan_results_table(results: list[DormancyCheckResult]) -> Table:
    """Create a rich table for scan results."""
    table = Table(
        title="Dormant Tenant Candidates",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Tenant ID", style="dim")
    table.add_column("Company", style="white")
    table.add_column("Connectors", justify="center")
    table.add_column("Slack Bot", justify="center")
    table.add_column("Documents", justify="right")
    table.add_column("Usage", justify="right")
    table.add_column("Days Since Provisioned", justify="right")

    for result in results:
        table.add_row(
            result.tenant_id,
            result.company_name or "Unknown",
            "✓" if result.has_connectors else "✗",
            "✓" if result.has_slack_bot else "✗",
            str(result.document_count),
            str(result.usage_count),
            str(result.days_since_provisioning) if result.days_since_provisioning else "N/A",
        )

    return table


def create_dormant_list_table(tenants: list[TenantInfo]) -> Table:
    """Create a rich table for dormant tenant list."""
    table = Table(
        title="Dormant Tenants",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    table.add_column("Tenant ID", style="dim")
    table.add_column("WorkOS Org ID", style="white")
    table.add_column("Provisioned At")
    table.add_column("Dormant Since")
    table.add_column("Days Dormant", justify="right")
    table.add_column("Grace Period Expires", style="yellow")

    grace_period = get_grace_period_days()

    for tenant in tenants:
        days_dormant = days_since(tenant.dormant_detected_at)

        # Calculate grace period expiration
        if tenant.dormant_detected_at:
            from datetime import timedelta

            expiry = tenant.dormant_detected_at + timedelta(days=grace_period)
            if datetime.now(UTC) > expiry.replace(tzinfo=UTC):
                expiry_str = "[red]EXPIRED[/red]"
            else:
                expiry_str = format_datetime(expiry)
        else:
            expiry_str = "N/A"

        table.add_row(
            tenant.id,
            tenant.workos_org_id or "N/A",
            format_datetime(tenant.provisioned_at),
            format_datetime(tenant.dormant_detected_at),
            days_dormant,
            expiry_str,
        )

    return table


def results_to_dict(results: list[DormancyCheckResult]) -> list[dict[str, Any]]:
    """Convert scan results to list of dicts for export."""
    return [
        {
            "tenant_id": r.tenant_id,
            "company_name": r.company_name,
            "is_dormant": r.is_dormant,
            "has_connectors": r.has_connectors,
            "has_slack_bot": r.has_slack_bot,
            "document_count": r.document_count,
            "usage_count": r.usage_count,
            "days_since_provisioning": r.days_since_provisioning,
            "reasons": r.reasons,
        }
        for r in results
    ]


def tenants_to_dict(tenants: list[TenantInfo]) -> list[dict[str, Any]]:
    """Convert tenant info list to list of dicts for export."""
    return [
        {
            "tenant_id": t.id,
            "workos_org_id": t.workos_org_id,
            "state": t.state,
            "provisioned_at": t.provisioned_at.isoformat() if t.provisioned_at else None,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "is_dormant": t.is_dormant,
            "dormant_detected_at": (
                t.dormant_detected_at.isoformat() if t.dormant_detected_at else None
            ),
        }
        for t in tenants
    ]


def export_json(data: list[dict[str, Any]], output: Path | None) -> None:
    """Export data as JSON."""
    json_str = json.dumps(data, indent=2, default=str)
    if output:
        output.write_text(json_str)
        log_success(f"Exported to {output}")
    else:
        console.print(json_str)


def export_csv(data: list[dict[str, Any]], output: Path | None) -> None:
    """Export data as CSV."""
    if not data:
        log_warning("No data to export")
        return

    output_buffer = StringIO()
    writer = csv.DictWriter(output_buffer, fieldnames=data[0].keys())
    writer.writeheader()
    writer.writerows(data)

    csv_str = output_buffer.getvalue()
    if output:
        output.write_text(csv_str)
        log_success(f"Exported to {output}")
    else:
        console.print(csv_str)


@app.command()
def scan(
    mark: bool = typer.Option(False, "--mark", help="Mark detected dormant tenants in database"),
    format: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "-f", help="Output format"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """
    Scan for dormant tenant candidates.

    By default, this is a dry-run that shows which tenants would be marked as dormant.
    Use --mark to actually mark them in the database.

    A tenant is considered dormant if ALL of these conditions are true:
    - No connector installations
    - No Slack bot installed
    - Zero documents in tenant database
    - No MCP usage/requests recorded
    - Provisioned more than DORMANT_DAYS_THRESHOLD days ago
    """
    try:
        validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    threshold = get_dormant_days_threshold()
    grace_period = get_grace_period_days()

    console.print()
    console.print(
        Panel(
            f"[bold]Dormant Tenant Scan[/bold]\n\n"
            f"Threshold: {threshold} days since provisioning\n"
            f"Grace Period: {grace_period} days before deletion eligible\n"
            f"Mode: {'[yellow]MARKING[/yellow]' if mark else '[green]DRY RUN[/green]'}",
            title="Configuration",
            border_style="blue",
        )
    )
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning tenants...", total=None)

        result = asyncio.run(scan_for_dormant_tenants(mark=mark))

        progress.update(task, completed=True)

    console.print()

    # Summary
    console.print("📊 [bold]Scan Summary[/bold]")
    console.print(f"   Total tenants scanned: {result.total_scanned}")
    console.print(f"   Dormant candidates found: {len(result.dormant_candidates)}")
    if mark:
        console.print(f"   Newly marked as dormant: {result.newly_marked}")
    if result.errors:
        console.print(f"   [red]Errors: {len(result.errors)}[/red]")
    console.print()

    if not result.dormant_candidates:
        log_success("No dormant tenants found!")
        return

    # Output results
    if format == OutputFormat.TABLE:
        table = create_scan_results_table(result.dormant_candidates)
        console.print(table)
    elif format == OutputFormat.JSON:
        export_json(results_to_dict(result.dormant_candidates), output)
    elif format == OutputFormat.CSV:
        export_csv(results_to_dict(result.dormant_candidates), output)

    console.print()

    if not mark:
        console.print("[dim]This was a dry run. Use --mark to mark these tenants as dormant.[/dim]")


@app.command()
def active(
    format: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "-f", help="Output format"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
) -> None:
    """
    Scan for active (non-dormant) tenants.

    Shows tenants that do NOT meet dormancy criteria - i.e., tenants that have:
    - Connector installations, OR
    - Slack bot installed, OR
    - Documents in tenant database, OR
    - MCP usage/requests recorded, OR
    - Provisioned less than DORMANT_DAYS_THRESHOLD days ago

    This is the reverse of the 'scan' command - it shows healthy/active tenants.
    """
    try:
        validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    threshold = get_dormant_days_threshold()

    console.print()
    console.print(
        Panel(
            f"[bold]Active Tenant Scan[/bold]\n\n"
            f"Dormancy Threshold: {threshold} days since provisioning\n"
            f"Showing tenants that do NOT meet dormancy criteria",
            title="Configuration",
            border_style="green",
        )
    )
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Scanning tenants...", total=None)

        result = asyncio.run(scan_for_active_tenants())

        progress.update(task, completed=True)

    console.print()

    # Summary
    console.print("📊 [bold]Scan Summary[/bold]")
    console.print(f"   Total tenants scanned: {result.total_scanned}")
    console.print(f"   Active tenants found: {len(result.active_tenants)}")
    if result.errors:
        console.print(f"   [red]Errors: {len(result.errors)}[/red]")
    console.print()

    if not result.active_tenants:
        log_warning("No active tenants found!")
        return

    # Output results
    if format == OutputFormat.TABLE:
        table = create_scan_results_table(result.active_tenants)
        console.print(table)
    elif format == OutputFormat.JSON:
        export_json(results_to_dict(result.active_tenants), output)
    elif format == OutputFormat.CSV:
        export_csv(results_to_dict(result.active_tenants), output)

    console.print()


@app.command("list")
def list_dormant(
    format: OutputFormat = typer.Option(OutputFormat.TABLE, "--format", "-f", help="Output format"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output file path"),
    expired_only: bool = typer.Option(
        False, "--expired", help="Only show tenants past grace period"
    ),
) -> None:
    """
    List all tenants currently marked as dormant.

    Use --expired to only show tenants that have passed the grace period
    and are eligible for deletion.
    """
    try:
        validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    async def get_tenants():
        from src.clients.tenant_db import tenant_db_manager

        control_pool = await tenant_db_manager.get_control_db()
        if expired_only:
            return await get_expired_dormant_tenants(control_pool)
        else:
            return await get_dormant_tenants(control_pool)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching dormant tenants...", total=None)
        tenants = asyncio.run(get_tenants())
        progress.update(task, completed=True)

    console.print()

    if not tenants:
        if expired_only:
            log_success("No expired dormant tenants found!")
        else:
            log_success("No dormant tenants found!")
        return

    title = "Expired Dormant Tenants" if expired_only else "All Dormant Tenants"
    console.print(f"📋 [bold]{title}[/bold]: {len(tenants)} found")
    console.print()

    if format == OutputFormat.TABLE:
        table = create_dormant_list_table(tenants)
        console.print(table)
    elif format == OutputFormat.JSON:
        export_json(tenants_to_dict(tenants), output)
    elif format == OutputFormat.CSV:
        export_csv(tenants_to_dict(tenants), output)


@app.command()
def inspect(
    tenant_id: str = typer.Argument(..., help="Tenant ID to inspect"),
) -> None:
    """
    Inspect a specific tenant's dormancy status.

    Shows detailed information about whether the tenant is dormant
    and why (or why not).
    """
    try:
        validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    console.print()
    console.print(f"🔍 [bold]Inspecting tenant: {tenant_id}[/bold]")
    console.print()

    async def _inspect_and_get_info() -> tuple[DormancyCheckResult | None, TenantInfo | None]:
        return await inspect_tenant(tenant_id), await get_tenant_info(tenant_id)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Checking tenant...", total=None)
        result, tenant = asyncio.run(_inspect_and_get_info())
        progress.update(task, completed=True)

    if result is None:
        log_error(f"Tenant {tenant_id} not found")
        raise typer.Exit(1)

    # Create info panel
    info_lines = [
        f"[bold]Tenant ID:[/bold] {result.tenant_id}",
        f"[bold]Company Name:[/bold] {result.company_name or 'Unknown'}",
        "",
        f"[bold]Has Connectors:[/bold] {'✓ Yes' if result.has_connectors else '✗ No'}",
        f"[bold]Has Slack Bot:[/bold] {'✓ Yes' if result.has_slack_bot else '✗ No'}",
        f"[bold]Document Count:[/bold] {result.document_count}",
        f"[bold]Usage Count:[/bold] {result.usage_count}",
        f"[bold]Days Since Provisioning:[/bold] {result.days_since_provisioning or 'N/A'}",
    ]

    if tenant:
        info_lines.extend(
            [
                "",
                f"[bold]State:[/bold] {tenant.state}",
                f"[bold]WorkOS Org ID:[/bold] {tenant.workos_org_id or 'N/A'}",
                f"[bold]Provisioned At:[/bold] {format_datetime(tenant.provisioned_at)}",
                f"[bold]Is Marked Dormant:[/bold] {'Yes' if tenant.is_dormant else 'No'}",
            ]
        )
        if tenant.dormant_detected_at:
            info_lines.append(
                f"[bold]Dormant Since:[/bold] {format_datetime(tenant.dormant_detected_at)}"
            )

    border_color = "red" if result.is_dormant else "green"
    status = "[red]DORMANT[/red]" if result.is_dormant else "[green]ACTIVE[/green]"

    console.print(
        Panel(
            "\n".join(info_lines),
            title=f"Tenant Status: {status}",
            border_style=border_color,
        )
    )

    if result.is_dormant and result.reasons:
        console.print()
        console.print("[bold]Reasons for dormancy:[/bold]")
        for reason in result.reasons:
            console.print(f"  • {reason}")


def _print_discovery_result(discovery: ResourceDiscoveryResult) -> None:
    """Print resource discovery result details."""
    lines: list[str] = []

    # PostgreSQL
    lines.append("[bold cyan]PostgreSQL:[/bold cyan]")
    if discovery.database_exists:
        lines.append(f"  [green]✓[/green] Database: {discovery.database_name}")
    else:
        lines.append(f"  [dim]✗ Database: {discovery.database_name} (not found)[/dim]")

    if discovery.role_exists:
        lines.append(f"  [green]✓[/green] Role: {discovery.role_name}")
    else:
        lines.append(f"  [dim]✗ Role: {discovery.role_name} (not found)[/dim]")

    # OpenSearch
    lines.append("")
    lines.append("[bold cyan]OpenSearch:[/bold cyan]")
    if discovery.opensearch_indices:
        for idx in discovery.opensearch_indices:
            lines.append(f"  [green]✓[/green] Index: {idx}")
    else:
        lines.append(f"  [dim]✗ No indices found for tenant-{discovery.tenant_id}*[/dim]")

    # Turbopuffer
    lines.append("")
    lines.append("[bold cyan]Turbopuffer:[/bold cyan]")
    if discovery.turbopuffer_namespace_exists:
        lines.append(f"  [green]✓[/green] Namespace: {discovery.tenant_id}")
    else:
        lines.append(f"  [dim]✗ Namespace: {discovery.tenant_id} (not found)[/dim]")

    # SSM
    lines.append("")
    lines.append("[bold cyan]SSM Parameters:[/bold cyan]")
    if discovery.ssm_parameters:
        lines.append(f"  [green]✓[/green] Found {len(discovery.ssm_parameters)} parameter(s):")
        for param in discovery.ssm_parameters[:10]:  # Show first 10
            lines.append(f"      • {param}")
        if len(discovery.ssm_parameters) > 10:
            lines.append(f"      ... and {len(discovery.ssm_parameters) - 10} more")
    else:
        lines.append(f"  [dim]✗ No parameters found under /{discovery.tenant_id}/[/dim]")

    # Control DB
    lines.append("")
    lines.append("[bold cyan]Control Database:[/bold cyan]")
    if discovery.control_db_tenant_exists:
        lines.append("  [green]✓[/green] Tenant record exists")
        if discovery.control_db_related_counts:
            lines.append("  [green]✓[/green] Related records:")
            for table, count in discovery.control_db_related_counts.items():
                lines.append(f"      • {table}: {count}")
        else:
            lines.append("  [dim]  No related records in other tables[/dim]")
    else:
        lines.append("  [dim]✗ Tenant record not found[/dim]")

    # Errors
    if discovery.errors:
        lines.append("")
        lines.append("[bold yellow]Discovery Errors:[/bold yellow]")
        for error in discovery.errors:
            lines.append(f"  [yellow]⚠[/yellow] {error}")

    console.print(
        Panel(
            "\n".join(lines),
            title=f"Resources Found for Tenant {discovery.tenant_id}",
            border_style="blue",
        )
    )


@app.command()
def delete(
    tenant_id: str = typer.Argument(..., help="Tenant ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be deleted without actually deleting"
    ),
) -> None:
    """
    Delete a specific tenant and all associated resources.

    This performs a HARD DELETE which:
    - Drops the PostgreSQL tenant database and role
    - Deletes all OpenSearch indices (alias + versioned)
    - Deletes the Turbopuffer namespace
    - Deletes all SSM parameters
    - Removes records from control database (cascades to related tables)

    Use --dry-run to see what resources exist without deleting them.

    WARNING: This operation is IRREVERSIBLE!
    """
    try:
        validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    console.print()

    if dry_run:
        # Dry run: discover and display what would be deleted
        console.print(f"🔍 [bold]Dry Run: Discovering resources for tenant {tenant_id}[/bold]")
        console.print()

        async def _discover_with_cleanup() -> ResourceDiscoveryResult:
            try:
                return await discover_tenant_resources(tenant_id)
            finally:
                # Clean up to prevent "Unclosed client session" warnings
                await cleanup_tenant_db_manager()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Discovering resources...", total=None)
            discovery = asyncio.run(_discover_with_cleanup())
            progress.update(task, completed=True)

        console.print()
        _print_discovery_result(discovery)
        console.print()

        # Summary
        resources_found = (
            discovery.database_exists
            or discovery.role_exists
            or discovery.opensearch_indices
            or discovery.turbopuffer_namespace_exists
            or discovery.ssm_parameters
            or discovery.control_db_tenant_exists
        )

        if resources_found:
            log_info("Dry run complete. Use without --dry-run to delete these resources.")
        else:
            log_warning("No resources found for this tenant.")

        return

    # Normal delete flow - fetch tenant info
    async def _get_tenant_with_cleanup() -> TenantInfo | None:
        try:
            return await get_tenant_info(tenant_id)
        finally:
            # Clean up to allow subsequent asyncio.run() calls
            await cleanup_tenant_db_manager()

    tenant = asyncio.run(_get_tenant_with_cleanup())
    if tenant is None:
        log_error(f"Tenant {tenant_id} not found in control database")
        raise typer.Exit(1)

    # Show warning
    console.print(
        Panel(
            f"[bold red]⚠️  WARNING: DESTRUCTIVE OPERATION[/bold red]\n\n"
            f"You are about to PERMANENTLY DELETE tenant:\n"
            f"  • Tenant ID: {tenant_id}\n"
            f"  • WorkOS Org: {tenant.workos_org_id or 'N/A'}\n"
            f"  • State: {tenant.state}\n"
            f"  • Provisioned: {format_datetime(tenant.provisioned_at)}\n\n"
            f"This will delete:\n"
            f"  • PostgreSQL database (db_{tenant_id}) and role ({tenant_id}_app_rw)\n"
            f"  • OpenSearch indices (tenant-{tenant_id}*)\n"
            f"  • Turbopuffer namespace\n"
            f"  • All SSM parameters (/{tenant_id}/*)\n"
            f"  • Control database records\n\n"
            f"[bold]THIS CANNOT BE UNDONE![/bold]",
            title="Deletion Warning",
            border_style="red",
        )
    )
    console.print()

    if not force:
        confirm = typer.confirm(
            f"Are you sure you want to delete tenant {tenant_id}?",
            default=False,
        )
        if not confirm:
            log_info("Deletion cancelled")
            raise typer.Exit(0)

    console.print()
    log_info(f"Deleting tenant {tenant_id}...")
    console.print()

    async def _delete_with_cleanup() -> DeletionResult:
        try:
            return await hard_delete_tenant(tenant_id)
        finally:
            # Clean up to allow subsequent asyncio.run() calls
            await cleanup_tenant_db_manager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Deleting tenant resources...", total=None)
        result = asyncio.run(_delete_with_cleanup())
        progress.update(task, completed=True)

    console.print()
    _print_deletion_result(result)


@app.command()
def purge(
    expired: bool = typer.Option(
        True, "--expired/--all", help="Only delete expired dormant tenants"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be deleted without deleting"
    ),
) -> None:
    """
    Delete multiple dormant tenants.

    By default, only deletes tenants that have been dormant for longer
    than the grace period (DORMANT_GRACE_PERIOD_DAYS).

    Use --dry-run to see what would be deleted without actually deleting.
    """
    try:
        validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    grace_period = get_grace_period_days()

    async def get_tenants():
        from src.clients.tenant_db import tenant_db_manager

        try:
            control_pool = await tenant_db_manager.get_control_db()
            if expired:
                return await get_expired_dormant_tenants(control_pool)
            else:
                return await get_dormant_tenants(control_pool)
        finally:
            # Clean up to allow subsequent asyncio.run() calls
            await cleanup_tenant_db_manager()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Finding tenants to purge...", total=None)
        tenants = asyncio.run(get_tenants())
        progress.update(task, completed=True)

    console.print()

    if not tenants:
        if expired:
            log_success(f"No expired dormant tenants found (grace period: {grace_period} days)")
        else:
            log_success("No dormant tenants found")
        return

    # Show tenants to be deleted
    console.print(f"🗑️  [bold]Tenants to delete:[/bold] {len(tenants)}")
    console.print()

    table = create_dormant_list_table(tenants)
    console.print(table)
    console.print()

    if dry_run:
        log_info("Dry run - no tenants were deleted")
        return

    # Confirmation
    if not force:
        console.print(
            Panel(
                f"[bold red]⚠️  WARNING: DESTRUCTIVE OPERATION[/bold red]\n\n"
                f"You are about to PERMANENTLY DELETE {len(tenants)} tenant(s).\n\n"
                f"[bold]THIS CANNOT BE UNDONE![/bold]",
                border_style="red",
            )
        )
        console.print()

        confirm = typer.confirm(
            f"Are you sure you want to delete {len(tenants)} tenant(s)?",
            default=False,
        )
        if not confirm:
            log_info("Purge cancelled")
            raise typer.Exit(0)

    # Delete tenants
    console.print()
    log_info(f"Deleting {len(tenants)} tenants...")
    console.print()

    success_count = 0
    failure_count = 0

    async def _delete_with_cleanup(tid: str) -> DeletionResult:
        try:
            return await hard_delete_tenant(tid)
        finally:
            await cleanup_tenant_db_manager()

    for tenant in tenants:
        console.print(f"  Deleting {tenant.id}...")
        result = asyncio.run(_delete_with_cleanup(tenant.id))

        if result.success:
            success_count += 1
            console.print("    [green]✓[/green] Deleted successfully")
        else:
            failure_count += 1
            console.print(f"    [red]✗[/red] Failed: {', '.join(result.errors)}")

    console.print()
    console.print("📊 [bold]Purge Summary[/bold]")
    console.print(f"   Successfully deleted: {success_count}")
    console.print(f"   Failed: {failure_count}")


@app.command()
def unmark(
    tenant_id: str = typer.Argument(..., help="Tenant ID to unmark as dormant"),
) -> None:
    """
    Remove dormant marking from a tenant.

    Use this if a tenant has become active and should no longer be
    considered dormant.
    """
    try:
        validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    # Verify tenant exists
    async def _get_tenant_with_cleanup() -> TenantInfo | None:
        try:
            return await get_tenant_info(tenant_id)
        finally:
            await cleanup_tenant_db_manager()

    tenant = asyncio.run(_get_tenant_with_cleanup())
    if tenant is None:
        log_error(f"Tenant {tenant_id} not found")
        raise typer.Exit(1)

    if not tenant.is_dormant:
        log_info(f"Tenant {tenant_id} is not marked as dormant")
        return

    async def do_unmark():
        try:
            from src.clients.tenant_db import tenant_db_manager

            control_pool = await tenant_db_manager.get_control_db()
            return await unmark_tenant_dormant(control_pool, tenant_id)
        finally:
            # Clean up to allow subsequent asyncio.run() calls
            await cleanup_tenant_db_manager()

    success = asyncio.run(do_unmark())

    if success:
        log_success(f"Tenant {tenant_id} is no longer marked as dormant")
    else:
        log_error(f"Failed to unmark tenant {tenant_id}")
        raise typer.Exit(1)


def _print_deletion_result(result: DeletionResult) -> None:
    """Print deletion result details."""
    if result.success:
        console.print(
            Panel(
                f"[green]✓ Successfully deleted tenant {result.tenant_id}[/green]\n\n"
                f"Completed steps:\n" + "\n".join(f"  • {step}" for step in result.steps_completed),
                title="Deletion Complete",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[red]✗ Failed to fully delete tenant {result.tenant_id}[/red]\n\n"
                f"Completed steps:\n"
                + "\n".join(f"  • {step}" for step in result.steps_completed)
                + "\n\nFailed steps:\n"
                + "\n".join(f"  • {step}" for step in result.steps_failed)
                + "\n\nErrors:\n"
                + "\n".join(f"  • {err}" for err in result.errors),
                title="Deletion Failed",
                border_style="red",
            )
        )


if __name__ == "__main__":
    app()
