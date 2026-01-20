#!/usr/bin/env python3
"""
Corporate Context Usage Reporting CLI

A tool for generating usage reports across all tenants using MCP /billing/usage endpoint.
"""

import asyncio
import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import aiohttp
import asyncpg
import jwt
import typer
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

from src.clients.redis import get_client as get_redis_client
from src.clients.redis import get_connection_url
from src.utils.config import get_config_value, get_mcp_base_url
from src.utils.posthog import get_posthog_service

# Load environment variables
load_dotenv()

app = typer.Typer(
    name="usage",
    help="Usage reporting for Corporate Context (MCP endpoint-based)",
    add_completion=False,
)
console = Console()


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


def validate_environment() -> tuple[str, str]:
    """
    Validate required environment variables and return connection info.

    Returns:
        Tuple of (control_db_url, redis_url)
    """
    control_db_url = get_config_value("CONTROL_DATABASE_URL")
    if not control_db_url:
        raise ValueError("CONTROL_DATABASE_URL environment variable is required")

    redis_url = get_connection_url()

    return control_db_url, redis_url


async def test_database_connectivity(db_url: str, timeout: int = 10) -> bool:
    """Test if we can connect to a database."""
    try:
        conn = await asyncio.wait_for(asyncpg.connect(db_url), timeout=timeout)
        await conn.execute("SELECT 1")
        await conn.close()
        return True
    except Exception:
        return False


async def test_redis_connectivity(timeout: int = 10) -> bool:
    """Test if we can connect to Redis."""
    try:
        client = await asyncio.wait_for(get_redis_client(), timeout=timeout)
        await asyncio.wait_for(client.ping(), timeout=timeout)
        return True
    except Exception:
        return False


async def get_provisioned_tenant_ids(control_db_url: str) -> list[str]:
    """Get list of provisioned tenant IDs from control database."""
    try:
        conn = await asyncpg.connect(control_db_url)
        try:
            rows = await conn.fetch("SELECT id FROM tenants WHERE state = 'provisioned'")
            return [row["id"] for row in rows]
        finally:
            await conn.close()
    except Exception as e:
        log_error(f"Failed to get tenant IDs: {e}")
        return []


def generate_tenant_jwt(tenant_id: str, expires_in_seconds: int = 300) -> str:
    """Generate a short-lived JWT token for a tenant.

    Args:
        tenant_id: Tenant identifier
        expires_in_seconds: Token expiration in seconds (default: 5 minutes)

    Returns:
        JWT token string

    Raises:
        ValueError: If JWT configuration is missing
    """
    private_key = get_config_value("INTERNAL_JWT_PRIVATE_KEY")
    if not private_key:
        raise ValueError(
            "INTERNAL_JWT_PRIVATE_KEY environment variable is required to generate tokens"
        )

    issuer = get_config_value("INTERNAL_JWT_ISSUER")
    audience = get_config_value("INTERNAL_JWT_AUDIENCE")

    now = int(time.time())
    exp = now + expires_in_seconds

    payload = {
        "tenant_id": tenant_id,
        "iat": now,
        "exp": exp,
    }

    if issuer:
        payload["iss"] = issuer

    if audience:
        payload["aud"] = audience

    # Generate RS256 JWT
    token = jwt.encode(payload, private_key, algorithm="RS256")
    return token


async def get_tenant_usage_from_mcp(tenant_id: str) -> dict[str, Any] | None:
    """Query usage data from MCP /billing/usage endpoint.

    Args:
        tenant_id: Tenant identifier

    Returns:
        Usage data dict or None if request fails
    """
    try:
        # Generate JWT token for this tenant
        token = generate_tenant_jwt(tenant_id)

        # Get MCP server URL
        mcp_base_url = get_mcp_base_url()
        url = f"{mcp_base_url}/v1/billing/usage"

        # Make HTTP request
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token}"}
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    log_warning(
                        f"MCP request failed for tenant {tenant_id}: {response.status} {await response.text()}"
                    )
                    return None

    except Exception as e:
        log_error(f"Error querying MCP for tenant {tenant_id}: {e}")
        return None


async def get_tenant_usage_report_from_mcp(
    tenant_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> "TenantUsageReport | None":
    """Build a usage report from MCP endpoint data.

    Args:
        tenant_id: Tenant identifier
        since: Start date (currently unused, MCP returns current billing period)
        until: End date (currently unused, MCP returns current billing period)

    Returns:
        TenantUsageReport or None if query fails
    """
    try:
        # Query usage from MCP /billing/usage endpoint
        usage_data = await get_tenant_usage_from_mcp(tenant_id)
        if not usage_data:
            return None

        # Create report
        report = TenantUsageReport(tenant_id)

        # Extract data from MCP response (uses camelCase keys)
        requests_used = usage_data.get("requestsUsed", 0)
        requests_available = usage_data.get("requestsAvailable", 0)
        tier = usage_data.get("tier", "unknown")
        is_trial = usage_data.get("isTrial", False)
        is_gather_managed = usage_data.get("isGatherManaged", False)
        billing_cycle_anchor = usage_data.get("billingCycleAnchor")
        trial_start_at = usage_data.get("trialStartAt")

        # Use billing period directly from API response
        if billing_cycle_anchor:
            report.billing_period_start = billing_cycle_anchor
            # Extract year-month for period key
            period_dt = datetime.fromisoformat(billing_cycle_anchor.replace("Z", "+00:00"))
            period_key = period_dt.strftime("%Y-%m")
        elif trial_start_at:
            report.billing_period_start = trial_start_at
            # Extract year-month for period key
            period_dt = datetime.fromisoformat(trial_start_at.replace("Z", "+00:00"))
            period_key = period_dt.strftime("%Y-%m")
        else:
            # Fallback to current month if no anchor or trial date
            now = datetime.now(UTC)
            report.billing_period_start = now.strftime("%Y-%m-%d")
            period_key = now.strftime("%Y-%m")

        # Add usage data (MCP only returns requests, not tokens)
        if requests_used > 0:
            report.add_monthly_usage("requests", period_key, requests_used)

        # Store billing limits
        report.billing_limits = {
            "monthly_requests": requests_available,
            "is_trial": is_trial,
            "tier": tier,
            "billing_cycle_anchor": billing_cycle_anchor,
            "billing_interval": "month",
            "trial_start_at": trial_start_at,
            "is_gather_managed": is_gather_managed,
        }

        return report

    except Exception as e:
        log_error(f"Error building usage report for tenant {tenant_id}: {e}")
        return None


class TenantUsageReport:
    """Represents usage data for a single tenant."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.total_requests = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_embedding_tokens = 0
        self.months_with_data: set[str] = set()
        self.billing_period_start: str | None = None
        self.billing_limits: dict[str, Any] | None = None

    def add_monthly_usage(self, metric_type: str, month: str, value: int):
        """Add monthly usage data for a metric type."""
        if value > 0:
            self.months_with_data.add(month)

        if metric_type == "requests":
            self.total_requests += value
        elif metric_type == "input_tokens":
            self.total_input_tokens += value
        elif metric_type == "output_tokens":
            self.total_output_tokens += value
        elif metric_type == "embedding_tokens":
            self.total_embedding_tokens += value

    @property
    def total_tokens(self) -> int:
        """Total tokens used by this tenant."""
        return self.total_input_tokens + self.total_output_tokens + self.total_embedding_tokens

    @property
    def earliest_month(self) -> str | None:
        """Earliest month with data."""
        return min(self.months_with_data) if self.months_with_data else None

    @property
    def latest_month(self) -> str | None:
        """Latest month with data."""
        return max(self.months_with_data) if self.months_with_data else None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "tenant_id": self.tenant_id,
            "summary": {
                "total_requests": self.total_requests,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_embedding_tokens": self.total_embedding_tokens,
                "total_tokens": self.total_tokens,
            },
            "time_range": {
                "earliest_month": self.earliest_month,
                "latest_month": self.latest_month,
                "months_with_data": sorted(self.months_with_data),
            },
        }

        # Add billing data if available
        if self.billing_period_start:
            result["billing_period_start"] = self.billing_period_start
        if self.billing_limits:
            result["billing_limits"] = self.billing_limits

        return result


def generate_month_keys(since: datetime | None, until: datetime | None) -> list[str]:
    """Generate list of YYYY-MM keys for the date range."""
    if not since and not until:
        # Default: last 6 months including current month
        now = datetime.utcnow()
        since = now.replace(day=1) - timedelta(days=150)  # About 5 months back
        until = now

    if not since:
        since = until - timedelta(days=180) if until else datetime.utcnow() - timedelta(days=180)

    if not until:
        until = datetime.utcnow()

    # Generate month keys from since to until
    months = []
    current = since.replace(day=1)  # Start at beginning of month

    while current <= until:
        months.append(current.strftime("%Y-%m"))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return months


async def get_tenant_usage_from_redis(
    tenant_id: str,
    since: datetime | None = None,
    until: datetime | None = None,
) -> TenantUsageReport | None:
    """Get usage data for a single tenant from Redis."""

    try:
        redis_client = await get_redis_client()

        # Generate month keys to query
        month_keys = generate_month_keys(since, until)
        metric_types = ["requests", "input_tokens", "output_tokens", "embedding_tokens"]

        # Create report
        report = TenantUsageReport(tenant_id)

        # Query all Redis keys for this tenant
        for month in month_keys:
            for metric_type in metric_types:
                redis_key = f"usage:{tenant_id}:{metric_type}:{month}"

                try:
                    value = await redis_client.get(redis_key)
                    usage_value = int(value) if value is not None else 0

                    if usage_value > 0:
                        report.add_monthly_usage(metric_type, month, usage_value)

                except Exception as e:
                    log_warning(f"Failed to get Redis key {redis_key}: {e}")
                    continue

        # Return report only if it has data
        if report.total_requests > 0 or report.total_tokens > 0:
            return report

        return None

    except Exception as e:
        log_error(f"Error getting Redis usage for tenant {tenant_id}: {e}")
        return None


@app.command()
def report(
    output: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
    since: str | None = typer.Option(None, "--since", help="Start date (YYYY-MM-DD format)"),
    until: str | None = typer.Option(None, "--until", help="End date (YYYY-MM-DD format)"),
    tenant: str | None = typer.Option(None, "--tenant", help="Report for specific tenant only"),
    format: str = typer.Option("table", "--format", "-f", help="Output format: table, json, csv"),
    max_parallel: int = typer.Option(10, "--max-parallel", help="Maximum parallel MCP queries"),
) -> None:
    """Generate usage reports for all tenants from MCP endpoint."""

    # Parse date filters
    since_dt = None
    until_dt = None

    if since:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d")
        except ValueError:
            log_error("Invalid since date format. Use YYYY-MM-DD")
            raise typer.Exit(1)

    if until:
        try:
            until_dt = datetime.strptime(until, "%Y-%m-%d")
            # Set to end of day
            until_dt = until_dt.replace(hour=23, minute=59, second=59)
        except ValueError:
            log_error("Invalid until date format. Use YYYY-MM-DD")
            raise typer.Exit(1)

    # Validate format
    if format not in ["table", "json", "csv"]:
        log_error("Invalid format. Choose from: table, json, csv")
        raise typer.Exit(1)

    # Run the async report generation
    asyncio.run(
        generate_usage_report(
            output=output,
            since=since_dt,
            until=until_dt,
            specific_tenant=tenant,
            output_format=format,
            max_parallel=max_parallel,
        )
    )


async def generate_usage_report(
    output: str | None,
    since: datetime | None,
    until: datetime | None,
    specific_tenant: str | None,
    output_format: str,
    max_parallel: int,
) -> None:
    """Main report generation logic."""

    log_info("Starting MCP endpoint-based usage report generation...")

    # Show filters
    if since or until or specific_tenant:
        console.print("[dim]Applied filters:[/dim]")
        if since:
            console.print(f"  Since: {since.strftime('%Y-%m-%d')}")
        if until:
            console.print(f"  Until: {until.strftime('%Y-%m-%d')}")
        if specific_tenant:
            console.print(f"  Tenant: {specific_tenant}")
        console.print()

    # Validate environment
    try:
        control_db_url, redis_url = validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    # Test connectivity
    log_info("Testing database connectivity...")

    if not await test_database_connectivity(control_db_url):
        log_error("Cannot connect to control database")
        raise typer.Exit(1)
    log_success("Control database connection successful")

    # Get tenant IDs
    if specific_tenant:
        tenant_ids = [specific_tenant]
        log_info(f"Reporting for specific tenant: {specific_tenant}")
    else:
        tenant_ids = await get_provisioned_tenant_ids(control_db_url)
        if not tenant_ids:
            log_warning("No provisioned tenants found")
            return

        log_info(f"Found {len(tenant_ids)} provisioned tenants")

    # Collect usage data with progress tracking
    semaphore = asyncio.Semaphore(max_parallel)
    tenant_reports: list[TenantUsageReport] = []

    async def get_tenant_usage_with_semaphore(tenant_id: str) -> TenantUsageReport | None:
        async with semaphore:
            # Query usage from MCP endpoint (includes raw Redis data for comparison)
            return await get_tenant_usage_report_from_mcp(tenant_id, since, until)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            "Collecting usage data from MCP endpoint...", total=len(tenant_ids)
        )

        for idx, tenant_id in enumerate(tenant_ids, start=1):
            report = await get_tenant_usage_with_semaphore(tenant_id)
            if report:
                tenant_reports.append(report)
            progress.update(
                task,
                advance=1,
                description=f"Processing tenant {idx}/{len(tenant_ids)} - Latest: {tenant_id[:16]}",
            )

    # For specific tenant queries, include tenant even if no usage (to show raw Redis data)
    if specific_tenant:
        # Don't filter out tenants with no usage for specific tenant queries
        pass
    else:
        # Filter out tenants with no usage for general reports
        tenant_reports = [r for r in tenant_reports if r.total_requests > 0 or r.total_tokens > 0]

    if not tenant_reports:
        log_warning("No usage data found for any tenants from MCP endpoint")
        return

    log_success(f"Collected usage data from {len(tenant_reports)} tenants")

    # Generate output
    if output_format == "json":
        await output_json_report(tenant_reports, output)
    elif output_format == "csv":
        await output_csv_report(tenant_reports, output)
    else:  # table
        await output_table_report(tenant_reports, output)


async def output_table_report(
    tenant_reports: list[TenantUsageReport], output_file: str | None
) -> None:
    """Output usage report as a rich table."""

    # Check if this is a single tenant report - show detailed view
    if len(tenant_reports) == 1:
        await output_single_tenant_detailed_report(tenant_reports[0], output_file)
        return

    # Create summary table - show top 25 by request usage
    sorted_reports = sorted(tenant_reports, key=lambda r: r.total_requests, reverse=True)
    top_25_reports = sorted_reports[:25]

    table = Table(box=box.ROUNDED, title="Usage Report Summary - Top 25 by Requests (MCP Endpoint)")
    table.add_column("Rank", style="dim", justify="right")
    table.add_column("Tenant ID", style="cyan", min_width=16)
    table.add_column("Requests", justify="right", style="green")
    table.add_column("Tier", style="yellow")
    table.add_column("Billing Period", style="dim")

    # Calculate totals across ALL tenants (not just top 25)
    total_requests = sum(r.total_requests for r in tenant_reports)

    for idx, report in enumerate(top_25_reports, start=1):
        billing_period = "Unknown"
        if report.billing_period_start:
            billing_period = report.billing_period_start
        elif report.earliest_month and report.latest_month:
            if report.earliest_month == report.latest_month:
                billing_period = report.earliest_month
            else:
                billing_period = f"{report.earliest_month} to {report.latest_month}"

        tier = report.billing_limits.get("tier", "unknown") if report.billing_limits else "unknown"

        table.add_row(
            f"#{idx}",
            report.tenant_id[:16],  # Truncate long tenant IDs
            f"{report.total_requests:,}",
            tier,
            billing_period,
        )

    # Add totals row
    table.add_section()
    table.add_row(
        "",
        "[bold]TOTAL[/bold]",
        f"[bold]{total_requests:,}[/bold]",
        "",
        f"[dim]{len(tenant_reports)} tenants[/dim]",
    )

    console.print()
    console.print(table)
    console.print()

    # Show additional statistics
    if tenant_reports:
        console.print("[bold]Statistics:[/bold]")
        console.print(f"• Tenants with usage: {len(tenant_reports)}")
        console.print(f"• Average requests per tenant: {total_requests // len(tenant_reports):,}")

        top_tenant = max(tenant_reports, key=lambda r: r.total_requests)
        console.print(
            f"• Top usage tenant: {top_tenant.tenant_id} ({top_tenant.total_requests:,} requests)"
        )

    # Save to file if requested
    if output_file:
        # For table format, save as plain text
        import io
        from contextlib import redirect_stdout

        output_buffer = io.StringIO()
        with redirect_stdout(output_buffer):
            console.print(table)

        Path(output_file).write_text(output_buffer.getvalue())
        log_success(f"Report saved to: {output_file}")


async def output_single_tenant_detailed_report(
    report: TenantUsageReport, output_file: str | None
) -> None:
    """Output detailed report for a single tenant with raw Redis data."""

    console.print()
    console.print(f"[bold cyan]Detailed Report for Tenant: {report.tenant_id}[/bold cyan]")
    console.print()

    # Check for expired trial and show big red warning
    if report.billing_limits:
        limits = report.billing_limits
        is_trial = limits.get("is_trial", False)
        trial_start_str = limits.get("trial_start_at")

        if is_trial and trial_start_str:
            try:
                from datetime import UTC

                trial_start = datetime.fromisoformat(trial_start_str.replace("Z", "+00:00"))
                trial_end = trial_start + timedelta(days=30)
                now = datetime.now(UTC)

                if now > trial_end:
                    # Trial has expired - show big red warning
                    console.print("🚨" * 20)
                    console.print()
                    console.print("[bold red on white]     TRIAL EXPIRED     [/bold red on white]")
                    console.print()
                    console.print(
                        f"[bold red]Trial started: {trial_start.strftime('%Y-%m-%d %H:%M:%S UTC')}[/bold red]"
                    )
                    console.print(
                        f"[bold red]Trial expired: {trial_end.strftime('%Y-%m-%d %H:%M:%S UTC')}[/bold red]"
                    )
                    console.print(
                        f"[bold red]Days past expiration: {(now - trial_end).days}[/bold red]"
                    )
                    console.print()
                    console.print("🚨" * 20)
                    console.print()
                elif is_trial:
                    # Trial is active - show warning about upcoming expiration
                    days_remaining = (trial_end - now).days
                    if days_remaining <= 7:
                        console.print("⚠️" * 15)
                        console.print()
                        console.print(
                            "[bold yellow on black]  TRIAL EXPIRING SOON  [/bold yellow on black]"
                        )
                        console.print()
                        console.print(
                            f"[bold yellow]Trial expires: {trial_end.strftime('%Y-%m-%d %H:%M:%S UTC')}[/bold yellow]"
                        )
                        console.print(
                            f"[bold yellow]Days remaining: {days_remaining}[/bold yellow]"
                        )
                        console.print()
                        console.print("⚠️" * 15)
                        console.print()
            except Exception as e:
                log_warning(f"Failed to parse trial date for expiration check: {e}")

    # Billing Limits Section
    if report.billing_limits:
        console.print("[bold]Billing Limits:[/bold]")
        limits_table = Table(box=box.SIMPLE, show_header=False)
        limits_table.add_column("Property", style="dim")
        limits_table.add_column("Value", style="")

        limits = report.billing_limits
        limits_table.add_row("Tier", limits["tier"])
        limits_table.add_row("Monthly Requests Limit", f"{limits['monthly_requests']:,}")
        limits_table.add_row("Is Trial", "Yes" if limits["is_trial"] else "No")
        limits_table.add_row("Is Gather Managed", "Yes" if limits["is_gather_managed"] else "No")
        if limits["billing_cycle_anchor"]:
            limits_table.add_row("Billing Cycle Anchor", limits["billing_cycle_anchor"])
        if limits["trial_start_at"]:
            limits_table.add_row("Trial Start", limits["trial_start_at"])
        if report.billing_period_start:
            limits_table.add_row("Current Billing Period Start", report.billing_period_start)

        console.print(limits_table)
        console.print()

    # Usage Summary Section
    console.print("[bold]Usage Summary:[/bold]")
    summary_table = Table(box=box.SIMPLE, show_header=False)
    summary_table.add_column("Metric", style="dim")
    summary_table.add_column("Total", style="green", justify="right")

    summary_table.add_row("Requests", f"{report.total_requests:,}")

    console.print(summary_table)
    console.print()

    # Save to file if requested
    if output_file:
        # Calculate trial status for JSON output
        trial_status = None
        if report.billing_limits:
            limits = report.billing_limits
            is_trial = limits.get("is_trial", False)
            trial_start_str = limits.get("trial_start_at")

            if is_trial and trial_start_str:
                try:
                    from datetime import UTC

                    trial_start = datetime.fromisoformat(trial_start_str.replace("Z", "+00:00"))
                    trial_end = trial_start + timedelta(days=30)
                    now = datetime.now(UTC)

                    if now > trial_end:
                        trial_status = {
                            "status": "expired",
                            "trial_start": trial_start.isoformat(),
                            "trial_end": trial_end.isoformat(),
                            "days_past_expiration": (now - trial_end).days,
                        }
                    else:
                        days_remaining = (trial_end - now).days
                        trial_status = {
                            "status": "active",
                            "trial_start": trial_start.isoformat(),
                            "trial_end": trial_end.isoformat(),
                            "days_remaining": days_remaining,
                            "expires_soon": days_remaining <= 7,
                        }
                except Exception:
                    pass

        # For detailed single tenant report, save as JSON for better structure
        report_data = {
            "tenant_id": report.tenant_id,
            "generated_at": datetime.utcnow().isoformat(),
            "data_source": "mcp_endpoint",
            "trial_status": trial_status,
            "summary": {
                "total_requests": report.total_requests,
                "total_input_tokens": report.total_input_tokens,
                "total_output_tokens": report.total_output_tokens,
                "total_embedding_tokens": report.total_embedding_tokens,
                "total_tokens": report.total_tokens,
            },
            "billing_limits": report.billing_limits,
            "billing_period_start": report.billing_period_start,
        }

        Path(output_file).write_text(json.dumps(report_data, indent=2))
        log_success(f"Detailed report saved to: {output_file}")


async def output_json_report(
    tenant_reports: list[TenantUsageReport], output_file: str | None
) -> None:
    """Output usage report as JSON."""

    report_data = {
        "generated_at": datetime.utcnow().isoformat(),
        "data_source": "mcp_endpoint",
        "tenant_count": len(tenant_reports),
        "summary": {
            "total_requests": sum(r.total_requests for r in tenant_reports),
            "total_input_tokens": sum(r.total_input_tokens for r in tenant_reports),
            "total_output_tokens": sum(r.total_output_tokens for r in tenant_reports),
            "total_embedding_tokens": sum(r.total_embedding_tokens for r in tenant_reports),
            "total_tokens": sum(r.total_tokens for r in tenant_reports),
        },
        "tenants": [report.to_dict() for report in tenant_reports],
    }

    json_output = json.dumps(report_data, indent=2, default=str)

    if output_file:
        Path(output_file).write_text(json_output)
        log_success(f"JSON report saved to: {output_file}")
    else:
        console.print(json_output)


async def output_csv_report(
    tenant_reports: list[TenantUsageReport], output_file: str | None
) -> None:
    """Output usage report as CSV, sorted by requests descending."""

    # Sort by requests descending
    sorted_reports = sorted(tenant_reports, key=lambda r: r.total_requests, reverse=True)

    csv_lines = ["tenant_id,total_requests,tier,billing_period"]

    for report in sorted_reports:
        tier = report.billing_limits.get("tier", "unknown") if report.billing_limits else "unknown"
        billing_period = report.billing_period_start or report.earliest_month or ""
        csv_lines.append(f"{report.tenant_id},{report.total_requests},{tier},{billing_period}")

    csv_output = "\n".join(csv_lines)

    if output_file:
        Path(output_file).write_text(csv_output)
        log_success(f"CSV report saved to: {output_file}")
    else:
        console.print(csv_output)


@app.command()
def summary(
    days: int = typer.Option(30, "--days", "-d", help="Number of days to look back"),
    tenant: str | None = typer.Option(None, "--tenant", help="Show summary for specific tenant"),
) -> None:
    """Show a quick usage summary from MCP endpoint."""

    # Calculate date range
    until_dt = datetime.utcnow()
    since_dt = until_dt - timedelta(days=days)

    console.print(f"[blue]📊 Usage Summary from MCP Endpoint (Last {days} days)[/blue]")
    console.print(
        f"[dim]From: {since_dt.strftime('%Y-%m-%d')} to {until_dt.strftime('%Y-%m-%d')}[/dim]"
    )
    console.print()

    # Run the async summary generation
    asyncio.run(
        generate_usage_report(
            output=None,
            since=since_dt,
            until=until_dt,
            specific_tenant=tenant,
            output_format="table",
            max_parallel=10,
        )
    )


@app.command()
def reset_trial(
    tenant: str = typer.Option(..., "--tenant", help="Tenant ID to reset trial for"),
    date: str | None = typer.Option(
        None, "--date", help="Trial start date (YYYY-MM-DD format), defaults to current time"
    ),
) -> None:
    """Reset trial for a tenant by updating trial_start_at to current time and clearing billing cache."""

    console.print(f"[blue]🔄 Resetting trial for tenant: {tenant}[/blue]")
    console.print()

    # Parse date if provided
    trial_date = None
    if date:
        try:
            trial_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            log_error("Invalid date format. Use YYYY-MM-DD")
            raise typer.Exit(1)

    # Run the async reset trial logic
    asyncio.run(perform_reset_trial(tenant, trial_date))


async def perform_reset_trial(tenant_id: str, trial_date: datetime | None = None) -> None:
    """Main reset trial logic."""

    log_info("Starting trial reset process...")

    # Validate environment
    try:
        control_db_url, redis_url = validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    # Test connectivity
    log_info("Testing database and Redis connectivity...")

    if not await test_database_connectivity(control_db_url):
        log_error("Cannot connect to control database")
        raise typer.Exit(1)
    log_success("Control database connection successful")

    if not await test_redis_connectivity():
        log_error("Cannot connect to Redis")
        raise typer.Exit(1)
    log_success("Redis connection successful")

    # Check if tenant exists
    log_info(f"Checking if tenant {tenant_id} exists...")
    try:
        conn = await asyncpg.connect(control_db_url)
        try:
            tenant_row = await conn.fetchrow(
                "SELECT id, trial_start_at FROM tenants WHERE id = $1", tenant_id
            )
            if not tenant_row:
                log_error(f"Tenant {tenant_id} not found in control database")
                raise typer.Exit(1)

            current_trial_start = tenant_row["trial_start_at"]
            log_info(f"Current trial_start_at: {current_trial_start}")

        finally:
            await conn.close()
    except Exception as e:
        log_error(f"Failed to check tenant: {e}")
        raise typer.Exit(1)

    # Update trial_start_at to specified date or current time
    new_trial_start = trial_date if trial_date else datetime.now(UTC)
    log_info(f"Updating trial_start_at to: {new_trial_start}...")
    try:
        conn = await asyncpg.connect(control_db_url)
        try:
            await conn.execute(
                "UPDATE tenants SET trial_start_at = $1 WHERE id = $2", new_trial_start, tenant_id
            )
            log_success(f"Updated trial_start_at to: {new_trial_start}")

        finally:
            await conn.close()
    except Exception as e:
        log_error(f"Failed to update trial_start_at: {e}")
        raise typer.Exit(1)

    # Send trial_start_at update to PostHog
    log_info("Sending trial_start_at update to PostHog...")
    try:
        posthog_service = get_posthog_service()

        # Capture event
        posthog_service.capture(
            distinct_id=tenant_id,
            event="trial_start_overridden",
            properties={
                "tenant_id": tenant_id,
                "trial_start_at": new_trial_start.isoformat(),
            },
        )

        # Update person properties
        posthog_service.set(
            distinct_id=tenant_id,
            properties={
                "trial_start_at": new_trial_start.isoformat(),
            },
        )

        # Flush to ensure events are sent
        posthog_service.flush()

        log_success("Successfully sent trial_start_at update to PostHog")

    except Exception as e:
        log_warning(f"Failed to send trial_start_at to PostHog (non-critical): {e}")

    # Clear Redis billing cache
    log_info("Clearing Redis billing cache...")
    try:
        redis_client = await get_redis_client()
        cache_key = f"billing_limits:{tenant_id}"

        deleted_count = await redis_client.delete(cache_key)
        if deleted_count > 0:
            log_success(f"Cleared Redis cache key: {cache_key}")
        else:
            log_warning(f"Redis cache key {cache_key} was not found (may already be cleared)")

    except Exception as e:
        log_error(f"Failed to clear Redis cache: {e}")
        raise typer.Exit(1)

    console.print()
    log_success("✅ Trial reset completed successfully!")
    console.print(f"[green]• Updated trial_start_at for tenant {tenant_id}[/green]")
    console.print("[green]• Sent trial_start_at update to PostHog[/green]")
    console.print(
        "[green]• Cleared billing cache - fresh limits will be calculated on next request[/green]"
    )


@app.command()
def set_enterprise_plan(
    tenant: str = typer.Argument(..., help="Tenant ID (16 hex chars)"),
    request_limit: int = typer.Argument(..., help="Monthly request limit (must be > 0)"),
) -> None:
    """
    Set enterprise plan request limit for a tenant.

    This will enable enterprise billing mode with a custom monthly request limit.
    Any existing Stripe subscriptions will be ignored.

    Example:
        uv run python -m src.usage.cli set-enterprise-plan abc123def456 50000
    """
    if request_limit <= 0:
        log_error("Request limit must be greater than 0")
        raise typer.Exit(code=1)

    asyncio.run(_set_enterprise_plan_async(tenant, request_limit))


@app.command()
def remove_enterprise_plan(
    tenant: str = typer.Argument(..., help="Tenant ID (16 hex chars)"),
) -> None:
    """
    Remove enterprise plan from a tenant.

    This will revert the tenant to standard billing (Stripe subscriptions/trial).

    Example:
        uv run python -m src.usage.cli remove-enterprise-plan abc123def456
    """
    asyncio.run(_remove_enterprise_plan_async(tenant))


@app.command()
def show_enterprise_plan(
    tenant: str = typer.Argument(..., help="Tenant ID (16 hex chars)"),
) -> None:
    """
    Show enterprise plan details for a tenant.

    Example:
        uv run python -m src.usage.cli show-enterprise-plan abc123def456
    """
    asyncio.run(_show_enterprise_plan_async(tenant))


async def _set_enterprise_plan_async(tenant_id: str, request_limit: int) -> None:
    """Set enterprise plan request limit."""
    try:
        control_db_url, _ = validate_environment()
        conn = await asyncpg.connect(control_db_url)

        try:
            # Update the tenant record
            result = await conn.execute(
                """
                UPDATE tenants
                SET enterprise_plan_request_limit = $1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $2
                """,
                request_limit,
                tenant_id,
            )

            if result == "UPDATE 0":
                log_error(f"Tenant {tenant_id} not found")
                raise typer.Exit(code=1)

            # Clear the Redis billing cache
            redis_client = await get_redis_client()
            cache_key = f"billing_limits:{tenant_id}"
            await redis_client.delete(cache_key)

            log_success(
                f"Set enterprise plan for tenant {tenant_id} with {request_limit:,} monthly requests"
            )
            log_info("Redis billing cache cleared - new limits will take effect immediately")

        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Failed to set enterprise plan: {e}")
        raise typer.Exit(code=1)


async def _remove_enterprise_plan_async(tenant_id: str) -> None:
    """Remove enterprise plan."""
    try:
        control_db_url, _ = validate_environment()
        conn = await asyncpg.connect(control_db_url)

        try:
            # Get current value before removing
            row = await conn.fetchrow(
                "SELECT enterprise_plan_request_limit FROM tenants WHERE id = $1",
                tenant_id,
            )

            if not row:
                log_error(f"Tenant {tenant_id} not found")
                raise typer.Exit(code=1)

            if row["enterprise_plan_request_limit"] is None:
                log_warning(f"Tenant {tenant_id} does not have an enterprise plan")
                return

            # Remove the enterprise plan
            await conn.execute(
                """
                UPDATE tenants
                SET enterprise_plan_request_limit = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                tenant_id,
            )

            # Clear the Redis billing cache
            redis_client = await get_redis_client()
            cache_key = f"billing_limits:{tenant_id}"
            await redis_client.delete(cache_key)

            log_success(
                f"Removed enterprise plan from tenant {tenant_id} "
                f"(was {row['enterprise_plan_request_limit']:,} monthly requests)"
            )
            log_info("Redis billing cache cleared - tenant will revert to standard billing")

        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Failed to remove enterprise plan: {e}")
        raise typer.Exit(code=1)


async def _show_enterprise_plan_async(tenant_id: str) -> None:
    """Show enterprise plan details."""
    try:
        control_db_url, _ = validate_environment()
        conn = await asyncpg.connect(control_db_url)

        try:
            row = await conn.fetchrow(
                """
                SELECT id, billing_mode, enterprise_plan_request_limit,
                       created_at, updated_at
                FROM tenants
                WHERE id = $1
                """,
                tenant_id,
            )

            if not row:
                log_error(f"Tenant {tenant_id} not found")
                raise typer.Exit(code=1)

            # Create a table for the output
            table = Table(title=f"Enterprise Plan Details: {tenant_id}", box=box.ROUNDED)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="white")

            table.add_row("Tenant ID", row["id"])
            table.add_row("Billing Mode", row["billing_mode"])

            if row["enterprise_plan_request_limit"] is not None:
                table.add_row(
                    "Enterprise Plan",
                    f"✅ ACTIVE - {row['enterprise_plan_request_limit']:,} monthly requests",
                    style="green",
                )
            else:
                table.add_row("Enterprise Plan", "❌ Not set", style="yellow")

            table.add_row("Created", row["created_at"].strftime("%Y-%m-%d %H:%M:%S"))
            table.add_row("Last Updated", row["updated_at"].strftime("%Y-%m-%d %H:%M:%S"))

            console.print(table)

        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Failed to show enterprise plan: {e}")
        raise typer.Exit(code=1)


@app.command()
def reset_usage(
    tenant: str = typer.Option(..., "--tenant", help="Tenant ID to reset usage for"),
) -> None:
    """Reset usage for a tenant by deleting all usage records and clearing Redis cache."""

    console.print(f"[blue]🔄 Resetting usage for tenant: {tenant}[/blue]")
    console.print()

    # Run the async reset usage logic
    asyncio.run(perform_reset_usage(tenant))


async def _reset_usage_data(tenant_id: str) -> tuple[int, int, bool, bool]:
    """
    Internal function to reset usage data without validation.

    Returns:
        Tuple of (deleted_records_count, deleted_redis_keys_count, db_success, redis_success)
    """
    # Delete all usage records from tenant database
    log_info("Deleting all usage records from tenant database...")
    deleted_records = 0
    db_success = False
    try:
        # Import tenant_db_manager to access tenant database
        from src.clients.tenant_db import tenant_db_manager

        async with tenant_db_manager.acquire_connection(tenant_id) as conn:
            # Delete all usage records
            result = await conn.execute("DELETE FROM usage_records")
            deleted_records = int(result.split()[-1]) if result.split()[-1].isdigit() else 0

            log_success(f"Deleted {deleted_records} usage records from tenant database")
            db_success = True

    except Exception as e:
        log_error(f"Failed to delete usage records from tenant database: {e}")
        # Don't raise - continue with Redis cleanup

    # Clear all Redis usage keys for this tenant
    log_info("Clearing all Redis usage keys...")
    deleted_redis_keys = 0
    redis_success = False
    try:
        redis_client = await get_redis_client()

        # Find all usage keys for this tenant
        # Pattern: usage:{tenant_id}:*
        pattern = f"usage:{tenant_id}:*"

        # Use SCAN to find all matching keys
        deleted_keys = []
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
            if keys:
                # Delete the keys
                await redis_client.delete(*keys)
                deleted_keys.extend(keys)

            if cursor == 0:
                break

        deleted_redis_keys = len(deleted_keys)
        if deleted_keys:
            log_success(f"Cleared {deleted_redis_keys} Redis usage keys")
        else:
            log_warning("No Redis usage keys found (may already be cleared)")
        redis_success = True

    except Exception as e:
        log_error(f"Failed to clear Redis usage keys: {e}")
        # Don't raise - we've done what we can

    return deleted_records, deleted_redis_keys, db_success, redis_success


async def perform_reset_usage(tenant_id: str) -> None:
    """Main reset usage logic."""

    log_info("Starting usage reset process...")

    # Validate environment
    try:
        control_db_url, redis_url = validate_environment()
    except ValueError as e:
        log_error(str(e))
        raise typer.Exit(1)

    # Test connectivity
    log_info("Testing database and Redis connectivity...")

    if not await test_database_connectivity(control_db_url):
        log_error("Cannot connect to control database")
        raise typer.Exit(1)
    log_success("Control database connection successful")

    if not await test_redis_connectivity():
        log_error("Cannot connect to Redis")
        raise typer.Exit(1)
    log_success("Redis connection successful")

    # Check if tenant exists
    log_info(f"Checking if tenant {tenant_id} exists...")
    try:
        conn = await asyncpg.connect(control_db_url)
        try:
            tenant_row = await conn.fetchrow("SELECT id FROM tenants WHERE id = $1", tenant_id)
            if not tenant_row:
                log_error(f"Tenant {tenant_id} not found in control database")
                raise typer.Exit(1)

            log_success(f"Tenant {tenant_id} found")

        finally:
            await conn.close()
    except Exception as e:
        log_error(f"Failed to check tenant: {e}")
        raise typer.Exit(1)

    # Reset usage data
    deleted_records, deleted_redis_keys, db_success, redis_success = await _reset_usage_data(
        tenant_id
    )

    console.print()

    # Show results with visual indicators
    if db_success and redis_success:
        log_success("✅ Usage reset completed successfully!")
    elif db_success or redis_success:
        log_warning("⚠️  Usage reset partially completed")
    else:
        log_error("❌ Usage reset failed")

    # Database deletion result
    if db_success:
        console.print(
            f"[green]✅ Deleted {deleted_records} usage records from tenant database[/green]"
        )
    else:
        console.print("[red]❌ Failed to delete usage records from tenant database[/red]")

    # Redis clearing result
    if redis_success:
        console.print(f"[green]✅ Cleared {deleted_redis_keys} Redis usage keys[/green]")
    else:
        console.print("[red]❌ Failed to clear Redis usage keys[/red]")


if __name__ == "__main__":
    app()
