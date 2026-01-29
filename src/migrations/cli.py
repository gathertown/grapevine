#!/usr/bin/env python3
"""
Corporate Context Database Migration CLI

A comprehensive tool for managing database migrations across control and tenant databases.
"""

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import asyncpg
import typer
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn
from rich.table import Table

# Import shared migration functionality
from src.migrations.core import (
    MIGRATION_TABLE,
    MigrationError,
    ensure_migrations_table,
    extract_version_from_filename,
    get_applied_migrations,
    get_control_migrations_dir,
    get_migration_files,
    get_tenant_migrations_dir,
    mark_migration_as_applied,
    migrate_database,
    unmark_migration_as_applied,
    validate_migration_exists,
)

# Load environment variables
load_dotenv()

app = typer.Typer(
    name="migrations",
    help="Database migration management for Corporate Context",
    add_completion=False,
)
console = Console()

# Configuration
CONTROL_MIGRATIONS_DIR = get_control_migrations_dir()
TENANT_MIGRATIONS_DIR = get_tenant_migrations_dir()


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


def slugify(text: str) -> str:
    """Convert text to a slug suitable for filenames."""
    # Convert to lowercase and replace non-alphanumeric chars with underscores
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower())
    # Remove leading/trailing underscores and collapse multiple underscores
    slug = re.sub(r"^_+|_+$", "", slug)
    slug = re.sub(r"_+", "_", slug)
    return slug


def generate_timestamp() -> str:
    """Generate timestamp for migration filename."""
    return datetime.now().strftime("%Y%m%d%H%M%S")


def validate_environment() -> tuple[str, str | None, str | None, str | None, str | None]:
    """Validate required environment variables and return database connection info."""
    control_db_url = os.getenv("CONTROL_DATABASE_URL")
    if not control_db_url:
        raise MigrationError("CONTROL_DATABASE_URL environment variable is required")

    # Tenant database credentials (optional)
    tenant_host = os.getenv("PG_TENANT_DATABASE_HOST")
    tenant_port = os.getenv("PG_TENANT_DATABASE_PORT", "5432")
    tenant_username = os.getenv("PG_TENANT_DATABASE_ADMIN_USERNAME")
    tenant_password = os.getenv("PG_TENANT_DATABASE_ADMIN_PASSWORD")

    return control_db_url, tenant_host, tenant_port, tenant_username, tenant_password


def validate_local_environment() -> tuple[str, str | None, str | None, str | None, str | None]:
    """Validate that we're running in a local development environment and return database connection info."""
    # Get database connection info from validate_environment
    control_db_url, tenant_host, tenant_port, tenant_username, tenant_password = (
        validate_environment()
    )

    console.print("Running in [bold]local development environment[/bold]")

    # Check that PG_TENANT_DATABASE_HOST is localhost (if provided)
    if tenant_host == None or (
        tenant_host and tenant_host not in ["localhost", "127.0.0.1", "::1"]
    ):
        raise MigrationError(
            f"PG_TENANT_DATABASE_HOST must be localhost for local environments. Current value: {tenant_host}"
        )

    # Check that CONTROL_DATABASE_URL points to localhost
    if control_db_url:
        # Parse the database URL to extract the host
        from urllib.parse import urlparse

        parsed_url = urlparse(control_db_url)
        console.print("control db url: ", control_db_url, parsed_url.hostname)
        if parsed_url.hostname == None or (
            parsed_url.hostname and parsed_url.hostname not in ["localhost", "127.0.0.1", "::1"]
        ):
            raise MigrationError(
                f"CONTROL_DATABASE_URL must point to localhost for local environments. Current host: {parsed_url.hostname}"
            )

    return control_db_url, tenant_host, tenant_port, tenant_username, tenant_password


def build_tenant_db_url(
    username: str | None, password: str | None, host: str | None, port: str | None, database: str
) -> str:
    """Build a tenant database URL with properly encoded credentials."""
    if not username or not password or not host or not port:
        raise MigrationError("Tenant database credentials are required")
    return f"postgresql://{quote_plus(username)}:{quote_plus(password)}@{host}:{port}/{database}"


async def test_database_connectivity(db_url: str, timeout: int = 10) -> bool:
    """Test if we can connect to a database."""
    try:
        conn = await asyncio.wait_for(asyncpg.connect(db_url), timeout=timeout)
        await conn.execute("SELECT 1")
        await conn.close()
        return True
    except Exception:
        return False


async def get_provisioned_tenant_ids(control_db_url: str) -> list[str]:
    """Get list of provisioned tenant IDs from control database.

    Only returns tenants with state='provisioned'. Tenants in other states
    (pending, provisioning, error, deactivating) are excluded from migrations.
    """
    try:
        conn = await asyncpg.connect(control_db_url)
        try:
            # Only migrate tenants that are fully provisioned
            # Excludes: pending, provisioning, error, deactivating
            rows = await conn.fetch(
                "SELECT id FROM tenants WHERE state = 'provisioned' AND deleted_at IS NULL"
            )
            return [row["id"] for row in rows]
        finally:
            await conn.close()
    except Exception as e:
        log_error(f"Failed to get tenant IDs: {e}")
        return []


@app.command()
def create(
    migration_type: str = typer.Argument(..., help="Migration type: 'control' or 'tenant'"),
    description: str = typer.Argument(..., help="Brief description of the migration"),
) -> None:
    """Create a new migration file with proper naming and template."""

    if migration_type not in ["control", "tenant"]:
        log_error("Migration type must be 'control' or 'tenant'")
        raise typer.Exit(1)

    # Determine target directory
    target_dir = CONTROL_MIGRATIONS_DIR if migration_type == "control" else TENANT_MIGRATIONS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    timestamp = generate_timestamp()
    slug = slugify(description)
    filename = f"{timestamp}_{slug}.sql"
    filepath = target_dir / filename

    # Check if file already exists
    if filepath.exists():
        log_error(f"File already exists: {filepath}")
        raise typer.Exit(1)

    # Create migration template
    template = f"""-- {migration_type.title()} DB Migration: {description}
-- Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

BEGIN;

-- Add your migration SQL here
-- Example:
-- CREATE TABLE example_table (
--     id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
--     name TEXT NOT NULL,
--     created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
-- );

-- Remember to add indexes for performance:
-- CREATE INDEX idx_example_table_name ON example_table(name);

-- Don't forget to add constraints:
-- ALTER TABLE example_table ADD CONSTRAINT example_table_name_check CHECK (length(name) > 0);

COMMIT;
"""

    # Write migration file
    filepath.write_text(template)

    log_success(f"Created migration file: {filepath}")

    # Show next steps
    console.print()
    log_info("Next steps:")
    console.print(f"1. Edit the migration file: {filepath}")
    console.print("2. Add your SQL migration code")
    console.print("3. Test locally: ./migrations/cli migrate --control --all-tenants")
    console.print("4. Commit and push to deploy")
    console.print()

    # Show recent migrations for context
    log_info(f"Recent migrations in {migration_type}:")
    recent_files = get_migration_files(target_dir)[-5:]  # Last 5 migrations
    for file in recent_files:
        console.print(f"  - {file.name}")


@app.command("list")
def list_command(
    control: bool = typer.Option(False, "--control", help="List control migrations only"),
    tenant: bool = typer.Option(False, "--tenant", help="List tenant migrations only"),
) -> None:
    """List available migration files."""

    if not control and not tenant:
        # Show both by default
        control = tenant = True

    if control:
        console.print("[blue]Control Database Migrations:[/blue]")
        control_files = get_migration_files(CONTROL_MIGRATIONS_DIR)
        if control_files:
            for file in control_files:
                console.print(f"  {file.name}")
        else:
            console.print("  No migrations found")
        console.print()

    if tenant:
        console.print("[blue]Tenant Database Migrations:[/blue]")
        tenant_files = get_migration_files(TENANT_MIGRATIONS_DIR)
        if tenant_files:
            for file in tenant_files:
                console.print(f"  {file.name}")
        else:
            console.print("  No migrations found")


@app.command()
def migrate(
    control: bool = typer.Option(False, "--control", help="Migrate control database"),
    all_tenants: bool = typer.Option(False, "--all-tenants", help="Migrate all tenant databases"),
    tenant: str | None = typer.Option(None, "--tenant", help="Migrate specific tenant database"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without executing"
    ),
    retries: int = typer.Option(3, "--retries", help="Number of retry attempts"),
    timeout: int = typer.Option(300, "--timeout", help="Migration timeout in seconds"),
    max_parallel: int = typer.Option(
        5, "--max-parallel", help="Maximum parallel tenant migrations"
    ),
) -> None:
    """Run database migrations."""

    # Validate that at least one target is specified
    if not control and not all_tenants and not tenant:
        log_error("Must specify at least one target: --control, --all-tenants, or --tenant <id>")
        raise typer.Exit(1)

    # Run the async migration
    asyncio.run(
        run_migrations(
            control=control,
            all_tenants=all_tenants,
            tenant=tenant,
            dry_run=dry_run,
            retries=retries,
            timeout=timeout,
            max_parallel=max_parallel,
        )
    )


async def run_migrations(
    control: bool,
    all_tenants: bool,
    tenant: str | None,
    dry_run: bool,
    retries: int,
    timeout: int,
    max_parallel: int,
) -> None:
    """Main migration execution logic."""

    log_info("Starting database migrations...")

    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No changes will be made[/yellow]")
        console.print()

    # Validate environment
    try:
        control_db_url, tenant_host, tenant_port, tenant_username, tenant_password = (
            validate_environment()
        )
    except MigrationError as e:
        log_error(str(e))
        raise typer.Exit(1)

    # Test control database connectivity
    if control or all_tenants:
        log_info("Testing control database connectivity...")
        if not await test_database_connectivity(control_db_url):
            log_error("Cannot connect to control database")
            raise typer.Exit(1)
        log_success("Control database connection successful")

    total_applied = 0
    total_migrations = 0
    any_failures = False

    # Migrate control database
    if control:
        console.print()
        console.print("[blue]🎯 Migrating control database[/blue]")
        applied, total, success = await migrate_database(
            control_db_url,
            CONTROL_MIGRATIONS_DIR,
            timeout=timeout,
            retries=retries,
            dry_run=dry_run,
        )
        total_applied += applied
        total_migrations += total
        if not success:
            any_failures = True

        if applied > 0:
            log_success(f"Control database: {applied} migrations applied")
        else:
            log_info("Control database: No new migrations to apply")

    # Migrate specific tenant
    if tenant:
        if not all([tenant_host, tenant_username, tenant_password]):
            log_error("Tenant database credentials not configured")
            log_error(
                "Set PG_TENANT_DATABASE_HOST, PG_TENANT_DATABASE_ADMIN_USERNAME, and PG_TENANT_DATABASE_ADMIN_PASSWORD"
            )
            raise typer.Exit(1)

        console.print()
        console.print(f"[blue]🏠 Migrating tenant: {tenant}[/blue]")

        tenant_db_url = build_tenant_db_url(tenant_username, tenant_password, tenant_host, tenant_port, f"db_{tenant}")

        applied, total, success = await migrate_database(
            tenant_db_url,
            TENANT_MIGRATIONS_DIR,
            timeout=timeout,
            retries=retries,
            dry_run=dry_run,
        )
        total_applied += applied
        total_migrations += total
        if not success:
            any_failures = True

        if applied > 0:
            log_success(f"Tenant {tenant}: {applied} migrations applied")
        else:
            log_info(f"Tenant {tenant}: No new migrations to apply")

    # Migrate all tenants
    if all_tenants:
        if not all([tenant_host, tenant_username, tenant_password]):
            log_warning("Tenant database credentials not configured, skipping tenant migrations")
            log_info(
                "Set PG_TENANT_DATABASE_HOST, PG_TENANT_DATABASE_ADMIN_USERNAME, and PG_TENANT_DATABASE_ADMIN_PASSWORD"
            )
        else:
            console.print()
            console.print("[blue]🏠 Migrating all tenant databases[/blue]")

            # Get tenant IDs
            tenant_ids = await get_provisioned_tenant_ids(control_db_url)

            if not tenant_ids:
                log_warning("No provisioned tenants found")
            else:
                log_info(f"Found {len(tenant_ids)} provisioned tenants")

                # Migrate tenants in parallel batches
                semaphore = asyncio.Semaphore(max_parallel)

                async def migrate_tenant_with_semaphore(tenant_id: str) -> tuple[int, int, bool]:
                    async with semaphore:
                        tenant_db_url = build_tenant_db_url(tenant_username, tenant_password, tenant_host, tenant_port, f"db_{tenant_id}")
                        return await migrate_database(
                            tenant_db_url,
                            TENANT_MIGRATIONS_DIR,
                            timeout=timeout,
                            retries=retries,
                            dry_run=dry_run,
                        )

                # Execute migrations with progress tracking
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task("Migrating tenants...", total=len(tenant_ids))

                    # Execute all tenant migrations in parallel
                    tasks = [migrate_tenant_with_semaphore(tenant_id) for tenant_id in tenant_ids]
                    results = await asyncio.gather(*tasks)
                    progress.update(task, advance=len(tenant_ids))

                # Summarize results
                tenant_applied = sum(result[0] for result in results)
                tenant_total = sum(result[1] for result in results)
                successful_tenants = sum(1 for result in results if result[2])
                failed_tenants = sum(1 for result in results if not result[2])

                total_applied += tenant_applied
                total_migrations += tenant_total
                if failed_tenants > 0:
                    any_failures = True

                if tenant_applied > 0:
                    log_success(
                        f"All tenants: {tenant_applied} total migrations applied across {successful_tenants} tenants"
                    )
                else:
                    log_info("All tenants: No new migrations to apply")

                if failed_tenants > 0:
                    log_error(f"Migration failures occurred on {failed_tenants} tenant databases")

    # Final summary
    console.print()
    console.print("=" * 50)

    if dry_run:
        log_info(f"DRY RUN COMPLETE: Would apply {total_applied} migrations")
    else:
        if any_failures:
            log_error(f"Migration FAILED: {total_applied} migrations applied but some failed")
        else:
            log_success(f"Migration complete: {total_applied} migrations applied")

    # Only show "up to date" message if there were no failures
    if total_applied == 0 and total_migrations > 0 and not any_failures:
        console.print("[dim]All migrations are up to date! 🎉[/dim]")

    # Exit with error code if any failures occurred
    if any_failures:
        raise typer.Exit(1)


@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed information"),
    control: bool = typer.Option(False, "--control", help="Show control database status only"),
    all_tenants: bool = typer.Option(
        False, "--all-tenants", help="Show all tenant database status"
    ),
    tenant: str | None = typer.Option(None, "--tenant", help="Show specific tenant status"),
) -> None:
    """Show migration status for databases."""

    # If no specific target, show all
    if not control and not all_tenants and not tenant:
        control = all_tenants = True

    # Run the async status check
    asyncio.run(
        show_migration_status(
            verbose=verbose,
            control=control,
            all_tenants=all_tenants,
            tenant=tenant,
        )
    )


async def show_migration_status(
    verbose: bool,
    control: bool,
    all_tenants: bool,
    tenant: str | None,
) -> None:
    """Show migration status for specified databases."""

    console.print("[blue]🔍 Database Migration Status[/blue]")
    console.print("=" * 50)
    console.print()

    # Validate environment
    try:
        control_db_url, tenant_host, tenant_port, tenant_username, tenant_password = (
            validate_environment()
        )
    except MigrationError as e:
        log_error(str(e))
        raise typer.Exit(1)

    # Control database status
    if control:
        await show_database_status(
            control_db_url, CONTROL_MIGRATIONS_DIR, "Control Database", verbose
        )

    # Specific tenant status
    if tenant:
        if not all([tenant_host, tenant_username, tenant_password]):
            log_error("Tenant database credentials not configured")
            raise typer.Exit(1)

        tenant_db_url = build_tenant_db_url(tenant_username, tenant_password, tenant_host, tenant_port, f"db_{tenant}")
        await show_database_status(
            tenant_db_url, TENANT_MIGRATIONS_DIR, f"Tenant Database ({tenant})", verbose
        )

    # All tenants status
    if all_tenants:
        if not all([tenant_host, tenant_username, tenant_password]):
            log_warning("Tenant database credentials not configured, skipping tenant status")
        else:
            tenant_ids = await get_provisioned_tenant_ids(control_db_url)

            if not tenant_ids:
                log_warning("No provisioned tenants found")
            else:
                for tenant_id in tenant_ids:
                    tenant_db_url = build_tenant_db_url(tenant_username, tenant_password, tenant_host, tenant_port, f"db_{tenant_id}")
                    await show_database_status(
                        tenant_db_url,
                        TENANT_MIGRATIONS_DIR,
                        f"Tenant Database ({tenant_id})",
                        verbose,
                    )


async def show_database_status(
    db_url: str, migrations_dir: Path, db_name: str, verbose: bool
) -> None:
    """Show migration status for a single database."""

    console.print(f"[cyan]📋 {db_name}[/cyan]")

    if not migrations_dir.exists():
        log_warning(f"Migration directory {migrations_dir} not found")
        console.print()
        return

    # Test connectivity
    if not await test_database_connectivity(db_url):
        log_error(f"Cannot connect to {db_name}")
        console.print()
        return

    try:
        conn = await asyncpg.connect(db_url)

        try:
            # Get applied migrations
            applied_migrations = await get_applied_migrations(conn)

            # Get available migration files
            migration_files = get_migration_files(migrations_dir)

            if not migration_files:
                log_warning("No migration files found")
                console.print()
                return

            # Create status table
            table = Table(box=box.ROUNDED)
            table.add_column("Version", style="dim")
            table.add_column("Status", justify="center")
            table.add_column("Applied At", style="dim")
            table.add_column("Description")

            applied_count = 0
            pending_count = 0

            for migration_file in migration_files:
                version = extract_version_from_filename(migration_file.name)
                description = (
                    migration_file.name.replace(f"{version}_", "")
                    .replace(".sql", "")
                    .replace("_", " ")
                )

                if version in applied_migrations:
                    status = "[green]✅ APPLIED[/green]"
                    applied_count += 1

                    # Get applied timestamp if verbose
                    applied_at = ""
                    if verbose:
                        try:
                            row = await conn.fetchrow(
                                f"SELECT applied_at FROM public.{MIGRATION_TABLE} WHERE version = $1",
                                version,
                            )
                            if row:
                                applied_at = row["applied_at"].strftime("%Y-%m-%d %H:%M:%S")
                        except Exception:
                            applied_at = "Unknown"
                else:
                    status = "[red]❌ PENDING[/red]"
                    applied_at = ""
                    pending_count += 1

                # Always show all migrations
                table.add_row(version, status, applied_at, description)

            console.print(table)

            # Summary
            total_count = len(migration_files)
            summary_style = "green" if pending_count == 0 else "yellow"
            console.print(
                f"[{summary_style}]Summary: {applied_count} applied, {pending_count} pending, {total_count} total[/{summary_style}]"
            )

            if pending_count == 0:
                console.print("[green]✅ All migrations are up to date[/green]")
            else:
                console.print(f"[yellow]⚠️  {pending_count} migrations need to be applied[/yellow]")

        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Error checking status for {db_name}: {e}")

    console.print()


@app.command()
def mark(
    apply_version: str | None = typer.Option(
        None, "--apply", help="Mark migration version as applied"
    ),
    unapply_version: str | None = typer.Option(
        None, "--unapply", help="Unmark migration version (remove from applied)"
    ),
    dangerous_apply_all: bool = typer.Option(
        False,
        "--DANGEROUS-apply-all",
        help="Mark ALL migrations as applied (use with extreme caution!)",
    ),
    control: bool = typer.Option(False, "--control", help="Target control database"),
    all_tenants: bool = typer.Option(False, "--all-tenants", help="Target all tenant databases"),
    tenant: str | None = typer.Option(None, "--tenant", help="Target specific tenant database"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without executing"
    ),
    force: bool = typer.Option(
        False, "--force", help="Skip validation checks and force the operation"
    ),
) -> None:
    """Mark or unmark migrations as applied in the schema_migrations table."""

    # Validate arguments
    options_count = sum([bool(apply_version), bool(unapply_version), dangerous_apply_all])

    if options_count == 0:
        log_error("Must specify one of: --apply, --unapply, or --DANGEROUS-apply-all")
        raise typer.Exit(1)

    if options_count > 1:
        log_error("Cannot specify multiple operations (--apply, --unapply, --DANGEROUS-apply-all)")
        raise typer.Exit(1)

    # Validate targeting
    if not control and not all_tenants and not tenant:
        log_error("Must specify target: --control, --all-tenants, or --tenant <id>")
        raise typer.Exit(1)

    if dangerous_apply_all:
        version = None
        operation = "apply_all"
    else:
        version = apply_version or unapply_version
        operation = "apply" if apply_version else "unapply"

    # Run the async operation
    asyncio.run(
        run_mark_operation(
            version=version,
            operation=operation,
            control=control,
            all_tenants=all_tenants,
            tenant=tenant,
            dry_run=dry_run,
            force=force,
        )
    )


async def run_mark_operation(
    version: str | None,
    operation: str,
    control: bool,
    all_tenants: bool,
    tenant: str | None,
    dry_run: bool,
    force: bool,
) -> None:
    """Execute the mark operation."""

    if operation == "apply_all":
        console.print("[red]🚨 DANGEROUS OPERATION: Applying ALL migrations as applied![/red]")
        if not dry_run:
            console.print(
                "[red]⚠️  This will mark ALL migrations as applied WITHOUT running them![/red]"
            )
            console.print("[red]⚠️  This could lead to database inconsistencies![/red]")
    else:
        console.print(f"[blue]🏷️  {operation.title()}ing Migration: {version}[/blue]")

    if dry_run:
        console.print("[yellow]🔍 DRY RUN MODE - No changes will be made[/yellow]")

    console.print()

    # Validate environment
    try:
        control_db_url, tenant_host, tenant_port, tenant_username, tenant_password = (
            validate_environment()
        )
    except MigrationError as e:
        log_error(str(e))
        raise typer.Exit(1)

    # Validate migration files exist (unless force is used or apply_all)
    if not force and operation != "apply_all" and version is not None:
        validation_errors = []

        if control:
            exists, filename = validate_migration_exists(version, CONTROL_MIGRATIONS_DIR)
            if not exists:
                validation_errors.append(f"Control migration file not found for version {version}")
            else:
                log_info(f"Found control migration file: {filename}")

        if all_tenants or tenant:
            exists, filename = validate_migration_exists(version, TENANT_MIGRATIONS_DIR)
            if not exists:
                validation_errors.append(f"Tenant migration file not found for version {version}")
            else:
                log_info(f"Found tenant migration file: {filename}")

        if validation_errors:
            for error in validation_errors:
                log_error(error)
            console.print()
            log_warning("Use --force to skip validation checks")
            raise typer.Exit(1)

    total_operations = 0
    successful_operations = 0

    # Control database operation
    if control:
        console.print("[blue]🎯 Control Database[/blue]")
        try:
            if operation == "apply_all":
                applied_count, total_count = await execute_apply_all_on_database(
                    control_db_url, CONTROL_MIGRATIONS_DIR, "Control Database", dry_run
                )
                total_operations += total_count
                successful_operations += applied_count
                if applied_count == total_count:
                    log_success(f"Applied all {applied_count} migrations to Control Database")
                else:
                    log_warning(
                        f"Applied {applied_count}/{total_count} migrations to Control Database"
                    )
            else:
                assert version is not None  # Guaranteed when operation != "apply_all"
                success = await execute_mark_on_database(
                    control_db_url, version, operation, "Control Database", dry_run
                )
                total_operations += 1
                if success:
                    successful_operations += 1
        except Exception as e:
            log_error(f"Failed to {operation} migration on control database: {e}")
        console.print()

    # Specific tenant operation
    if tenant:
        if not all([tenant_host, tenant_username, tenant_password]):
            log_error("Tenant database credentials not configured")
            raise typer.Exit(1)

        console.print(f"[blue]🏠 Tenant: {tenant}[/blue]")
        tenant_db_url = build_tenant_db_url(tenant_username, tenant_password, tenant_host, tenant_port, f"db_{tenant}")

        try:
            if operation == "apply_all":
                applied_count, total_count = await execute_apply_all_on_database(
                    tenant_db_url, TENANT_MIGRATIONS_DIR, f"Tenant ({tenant})", dry_run
                )
                total_operations += total_count
                successful_operations += applied_count
                if applied_count == total_count:
                    log_success(f"Applied all {applied_count} migrations to Tenant ({tenant})")
                else:
                    log_warning(
                        f"Applied {applied_count}/{total_count} migrations to Tenant ({tenant})"
                    )
            else:
                assert version is not None  # Guaranteed when operation != "apply_all"
                success = await execute_mark_on_database(
                    tenant_db_url, version, operation, f"Tenant ({tenant})", dry_run
                )
                total_operations += 1
                if success:
                    successful_operations += 1
        except Exception as e:
            log_error(f"Failed to {operation} migration on tenant {tenant}: {e}")
        console.print()

    # All tenants operation
    if all_tenants:
        if not all([tenant_host, tenant_username, tenant_password]):
            log_error("Tenant database credentials not configured")
            raise typer.Exit(1)

        console.print("[blue]🏠 All Tenants[/blue]")

        # Get tenant IDs
        tenant_ids = await get_provisioned_tenant_ids(control_db_url)

        if not tenant_ids:
            log_warning("No provisioned tenants found")
        else:
            log_info(f"Found {len(tenant_ids)} provisioned tenants")

            for tenant_id in tenant_ids:
                tenant_db_url = build_tenant_db_url(tenant_username, tenant_password, tenant_host, tenant_port, f"db_{tenant_id}")

                try:
                    if operation == "apply_all":
                        applied_count, tenant_total_count = await execute_apply_all_on_database(
                            tenant_db_url, TENANT_MIGRATIONS_DIR, f"Tenant ({tenant_id})", dry_run
                        )
                        total_operations += tenant_total_count
                        successful_operations += applied_count
                        if applied_count == tenant_total_count:
                            log_success(
                                f"Applied all {applied_count} migrations to Tenant ({tenant_id})"
                            )
                        else:
                            log_warning(
                                f"Applied {applied_count}/{tenant_total_count} migrations to Tenant ({tenant_id})"
                            )
                    else:
                        assert version is not None  # Guaranteed when operation != "apply_all"
                        success = await execute_mark_on_database(
                            tenant_db_url, version, operation, f"Tenant ({tenant_id})", dry_run
                        )
                        total_operations += 1
                        if success:
                            successful_operations += 1
                except Exception as e:
                    log_error(f"Failed to {operation} migration on tenant {tenant_id}: {e}")
        console.print()

    # Summary
    console.print("=" * 50)
    if dry_run:
        if operation == "apply_all":
            log_info(f"DRY RUN COMPLETE: Would apply all {total_operations} migrations")
        else:
            log_info(
                f"DRY RUN COMPLETE: Would {operation} migration {version} on {total_operations} databases"
            )
    else:
        if operation == "apply_all":
            if successful_operations == total_operations:
                log_success(f"Successfully applied all {successful_operations} migrations")
            else:
                log_warning(f"Applied {successful_operations}/{total_operations} migrations")
        else:
            if successful_operations == total_operations:
                log_success(
                    f"Successfully {operation}ed migration {version} on {successful_operations}/{total_operations} databases"
                )
            else:
                log_warning(
                    f"Partially completed: {successful_operations}/{total_operations} databases succeeded"
                )

    # Warning for unapply operations
    if operation == "unapply" and not dry_run and successful_operations > 0:
        console.print()
        log_warning("⚠️  Migration has been unmarked and can now be re-run")
        log_warning("⚠️  Make sure this is intended before running migrate command")

    # Warning for apply_all operations
    if operation == "apply_all" and not dry_run and successful_operations > 0:
        console.print()
        log_warning(
            "🚨 DANGEROUS: All migrations have been marked as applied WITHOUT running them!"
        )
        log_warning("🚨 Ensure your database schema is consistent with the migrations!")
        log_warning("🚨 Running migrate now will skip all these migrations!")


async def execute_mark_on_database(
    db_url: str, version: str, operation: str, db_name: str, dry_run: bool
) -> bool:
    """Execute mark operation on a single database."""

    if dry_run:
        log_info(f"DRY RUN: Would {operation} migration {version} on {db_name}")
        return True

    try:
        # Test connectivity
        if not await test_database_connectivity(db_url):
            log_error(f"Cannot connect to {db_name}")
            return False

        conn = await asyncpg.connect(db_url)
        try:
            if operation == "apply":
                await mark_migration_as_applied(conn, version)
                log_success(f"Marked migration {version} as applied on {db_name}")
                return True
            else:  # unapply
                success = await unmark_migration_as_applied(conn, version)
                if success:
                    log_success(f"Unmarked migration {version} on {db_name}")
                else:
                    log_warning(f"Migration {version} was not marked as applied on {db_name}")
                return success
        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Error {operation}ing migration on {db_name}: {e}")
        return False


async def execute_apply_all_on_database(
    db_url: str, migrations_dir: Path, db_name: str, dry_run: bool
) -> tuple[int, int]:
    """Mark all available migrations as applied on a single database."""

    if not migrations_dir.exists():
        log_warning(f"Migration directory {migrations_dir} not found for {db_name}")
        return 0, 0

    migration_files = get_migration_files(migrations_dir)
    if not migration_files:
        log_info(f"No migrations found for {db_name}")
        return 0, 0

    total_count = len(migration_files)

    if dry_run:
        log_info(f"DRY RUN: Would mark {total_count} migrations as applied on {db_name}")
        return total_count, total_count

    try:
        # Test connectivity
        if not await test_database_connectivity(db_url):
            log_error(f"Cannot connect to {db_name}")
            return 0, total_count

        conn = await asyncpg.connect(db_url)
        try:
            # Ensure migrations table exists
            await ensure_migrations_table(conn)

            # Get already applied migrations
            applied_migrations = await get_applied_migrations(conn)

            applied_count = 0

            for migration_file in migration_files:
                version = extract_version_from_filename(migration_file.name)

                if version in applied_migrations:
                    log_info(f"Migration {version} already applied on {db_name}")
                    applied_count += 1
                    continue

                try:
                    await mark_migration_as_applied(conn, version)
                    applied_count += 1
                    log_success(f"Marked migration {version} as applied on {db_name}")
                except Exception as e:
                    log_error(f"Failed to mark migration {version} as applied on {db_name}: {e}")
                    break

            return applied_count, total_count

        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Error applying all migrations on {db_name}: {e}")
        return 0, total_count


@app.command()
def reset(
    control: bool = typer.Option(False, "--control", help="Reset control database"),
    all_tenants: bool = typer.Option(False, "--all-tenants", help="Reset all tenant databases"),
    tenant: str | None = typer.Option(None, "--tenant", help="Reset specific tenant database"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without executing"
    ),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompts (DANGEROUS!)"),
) -> None:
    """Reset (drop all data from) databases. Only works in local environments."""

    # Validate that at least one target is specified
    if not control and not all_tenants and not tenant:
        log_error("Must specify at least one target: --control, --all-tenants, or --tenant <id>")
        raise typer.Exit(1)

    # Run the async reset operation
    asyncio.run(
        run_reset_operation(
            control=control,
            all_tenants=all_tenants,
            tenant=tenant,
            dry_run=dry_run,
            force=force,
        )
    )


async def run_reset_operation(
    control: bool,
    all_tenants: bool,
    tenant: str | None,
    dry_run: bool,
    force: bool,
) -> None:
    """Execute the reset operation with safety checks."""

    # Show warning about destructive operation
    console.print("[red]🚨 DESTRUCTIVE OPERATION: Database Reset[/red]")
    log_warning("This will permanently delete ALL data from the selected databases!")
    log_warning("This operation cannot be undone!")
    console.print()

    # Validate environment variables
    try:
        control_db_url, tenant_host, tenant_port, tenant_username, tenant_password = (
            validate_local_environment()
        )
    except MigrationError as e:
        log_error(str(e))
        raise typer.Exit(1)

    if dry_run:
        log_info("DRY RUN MODE - No changes will be made[/yellow]")
    elif not force:
        # Require explicit confirmation
        targets = []
        if control:
            targets.append(f"control database: {control_db_url}")
        if all_tenants:
            targets.append(f"all tenant databases: {tenant_host}")
        if tenant:
            targets.append(f"tenant database ({tenant})")

        target_text = ", ".join(targets)
        log_warning(f"You are about to reset {target_text}")

        confirmation = typer.confirm(
            "Are you absolutely sure you want to proceed? Type 'yes' to confirm", default=False
        )
        if not confirmation:
            log_info("Reset operation cancelled")
            return

    console.print()

    total_operations = 0
    successful_operations = 0

    # Reset control database
    if control:
        console.print("[blue]🎯 Resetting control database[/blue]")
        try:
            success = await drop_database_schema(control_db_url, "control database", dry_run)
            total_operations += 1
            if success:
                successful_operations += 1
                if not dry_run:
                    log_success("Control database reset successfully")
            else:
                log_error("Failed to reset control database")
        except Exception as e:
            log_error(f"Error resetting control database: {e}")
        console.print()

    # Reset specific tenant
    if tenant:
        if not all([tenant_host, tenant_username, tenant_password]):
            log_error("Tenant database credentials not configured")
            log_error(
                "Set PG_TENANT_DATABASE_HOST, PG_TENANT_DATABASE_ADMIN_USERNAME, and PG_TENANT_DATABASE_ADMIN_PASSWORD"
            )
            raise typer.Exit(1)

        console.print(f"[blue]🏠 Resetting tenant: {tenant}[/blue]")
        tenant_db_url = build_tenant_db_url(tenant_username, tenant_password, tenant_host, tenant_port, f"db_{tenant}")

        try:
            success = await drop_database_schema(
                tenant_db_url, f"tenant database ({tenant})", dry_run
            )
            total_operations += 1
            if success:
                successful_operations += 1
                if not dry_run:
                    log_success(f"Tenant {tenant} reset successfully")
            else:
                log_error(f"Failed to reset tenant {tenant}")
        except Exception as e:
            log_error(f"Error resetting tenant {tenant}: {e}")
        console.print()

    # Reset all tenants
    if all_tenants:
        if not all([tenant_host, tenant_username, tenant_password]):
            log_error("Tenant database credentials not configured")
            log_error(
                "Set PG_TENANT_DATABASE_HOST, PG_TENANT_DATABASE_ADMIN_USERNAME, and PG_TENANT_DATABASE_ADMIN_PASSWORD"
            )
            raise typer.Exit(1)

        console.print("[blue]🏠 Resetting all tenant databases[/blue]")

        # Get tenant IDs from control database (if it hasn't been reset yet)
        try:
            if control and not dry_run:
                # If we're also resetting control, get tenant IDs first
                tenant_ids = await get_provisioned_tenant_ids(control_db_url)
            else:
                tenant_ids = await get_provisioned_tenant_ids(control_db_url)
        except Exception:
            log_warning("Could not retrieve tenant IDs, you may need to specify tenants manually")
            tenant_ids = []

        if not tenant_ids:
            log_warning("No provisioned tenants found")
        else:
            log_info(f"Found {len(tenant_ids)} provisioned tenants")

            for tenant_id in tenant_ids:
                tenant_db_url = build_tenant_db_url(tenant_username, tenant_password, tenant_host, tenant_port, f"db_{tenant_id}")

                try:
                    success = await drop_database_schema(
                        tenant_db_url, f"tenant database ({tenant_id})", dry_run
                    )
                    total_operations += 1
                    if success:
                        successful_operations += 1
                        if not dry_run:
                            log_success(f"Tenant {tenant_id} reset successfully")
                    else:
                        log_error(f"Failed to reset tenant {tenant_id}")
                except Exception as e:
                    log_error(f"Error resetting tenant {tenant_id}: {e}")

        console.print()

    # Final summary
    console.print("=" * 50)
    if dry_run:
        log_info(f"DRY RUN COMPLETE: Would reset {total_operations} databases")
    else:
        if successful_operations == total_operations:
            log_success(f"Reset complete: {successful_operations} databases reset successfully")
        else:
            log_warning(
                f"Reset partially completed: {successful_operations}/{total_operations} databases reset"
            )

    if not dry_run and successful_operations > 0:
        console.print()
        log_warning("🔄 All data has been permanently deleted!")
        log_info("💡 Run migration commands to recreate the schema:")
        console.print("   mise migrations migrate --control --all-tenants")


async def drop_database_schema(db_url: str, db_name: str, dry_run: bool = False) -> bool:
    """Drop all user-created tables and data from a database, preserving system tables."""
    if dry_run:
        log_info(f"DRY RUN: Would drop all user tables and data from {db_name}")
        return True

    try:
        conn = await asyncpg.connect(db_url)
        try:
            # Get all user-created tables (excluding system schemas)
            query = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE';
            """
            tables = await conn.fetch(query)

            if not tables:
                log_info(f"No user tables found in {db_name}")
                return True

            table_names = [table["table_name"] for table in tables]
            log_warning(
                f"Dropping {len(table_names)} tables from {db_name}: {', '.join(table_names)}"
            )

            # Disable foreign key checks temporarily and drop all tables
            await conn.execute("SET session_replication_role = replica;")

            for table_name in table_names:
                await conn.execute(f'DROP TABLE IF EXISTS public."{table_name}" CASCADE;')
                log_info(f"Dropped table: {table_name}")

            # Re-enable foreign key checks
            await conn.execute("SET session_replication_role = DEFAULT;")

            # Drop any remaining sequences, views, functions, etc.
            sequences_query = """
                SELECT sequence_name
                FROM information_schema.sequences
                WHERE sequence_schema = 'public';
            """
            sequences = await conn.fetch(sequences_query)
            for seq in sequences:
                await conn.execute(
                    f'DROP SEQUENCE IF EXISTS public."{seq["sequence_name"]}" CASCADE;'
                )

            views_query = """
                SELECT table_name
                FROM information_schema.views
                WHERE table_schema = 'public';
            """
            views = await conn.fetch(views_query)
            for view in views:
                await conn.execute(f'DROP VIEW IF EXISTS public."{view["table_name"]}" CASCADE;')

            log_success(f"Successfully reset {db_name} database")
            return True

        finally:
            await conn.close()

    except Exception as e:
        log_error(f"Failed to drop database schema for {db_name}: {e}")
        return False


if __name__ == "__main__":
    app()
