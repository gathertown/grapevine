"""Core migration functionality shared between CLI and steward service."""

import asyncio
import os
from pathlib import Path

import asyncpg
import sqlparse

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Constants
MIGRATION_TABLE = "schema_migrations"


class MigrationError(Exception):
    """Custom exception for migration-related errors."""

    pass


def get_migrations_dir() -> Path:
    """Get the migrations directory path."""
    # Default to repository migrations directory
    default_path = Path(__file__).parent.parent.parent / "migrations"
    migrations_dir = os.getenv("MIGRATIONS_DIR", str(default_path))
    return Path(migrations_dir)


def get_tenant_migrations_dir() -> Path:
    """Get the tenant migrations directory path."""
    return get_migrations_dir() / "tenant"


def get_control_migrations_dir() -> Path:
    """Get the control migrations directory path."""
    return get_migrations_dir() / "control"


def get_migration_files(directory: Path) -> list[Path]:
    """Get all migration files from a directory, sorted by timestamp."""
    if not directory.exists():
        return []

    sql_files = list(directory.glob("*.sql"))
    # Sort by filename (timestamp prefix ensures correct order)
    return sorted(sql_files)


def extract_version_from_filename(filename: str) -> str:
    """Extract version timestamp from migration filename."""
    return filename.split("_")[0]


def parse_sql_statements(sql_content: str) -> list[str]:
    """Parse SQL content into individual statements."""
    statements = []
    for statement in sqlparse.split(sql_content):
        stmt = statement.strip()
        if stmt:
            statements.append(stmt)
    return statements


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    """Ensure the schema_migrations table exists with proper setup."""
    # Create the table if it doesn't exist
    await conn.execute(f"""
        CREATE TABLE IF NOT EXISTS public.{MIGRATION_TABLE} (
            version VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
    """)

    # Set ownership to postgres user (for consistency with other tables)
    # This is a no-op if already owned by postgres
    await conn.execute(f"""
        ALTER TABLE public.{MIGRATION_TABLE} OWNER TO postgres;
    """)


async def get_applied_migrations(conn: asyncpg.Connection) -> set[str]:
    """Get set of applied migration versions."""
    # Check if migrations table exists
    exists = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = $1
        )
    """,
        MIGRATION_TABLE,
    )

    if not exists:
        return set()

    rows = await conn.fetch(f"SELECT version FROM public.{MIGRATION_TABLE}")
    return {row["version"] for row in rows}


async def apply_migration_file(
    conn: asyncpg.Connection, migration_file: Path, timeout: int = 300, dry_run: bool = False
) -> bool:
    """Apply a single migration file with proper transaction handling."""
    version = extract_version_from_filename(migration_file.name)

    if dry_run:
        logger.info(f"DRY RUN: Would apply {migration_file.name}")
        return True

    try:
        # Read migration content
        migration_sql = migration_file.read_text()

        # Execute in a transaction that includes tracking
        async with conn.transaction():
            # Set statement timeout
            await conn.execute(f"SET statement_timeout = '{timeout}s'")

            # Execute the migration
            await conn.execute(migration_sql)

            # Record migration as applied
            await conn.execute(
                f"INSERT INTO public.{MIGRATION_TABLE} (version) VALUES ($1)", version
            )

        logger.info(f"Applied migration {migration_file.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to apply migration {migration_file.name}: {e}")
        return False


async def apply_migration_statements(
    conn: asyncpg.Connection, version: str, statements: list[str], timeout: int = 300
) -> None:
    """Apply migration statements with proper transaction handling and tracking."""
    async with conn.transaction():
        # Set statement timeout
        await conn.execute(f"SET statement_timeout = '{timeout}s'")

        # Execute all statements
        for statement in statements:
            if statement:
                await conn.execute(statement)

        # Record migration as applied
        await conn.execute(f"INSERT INTO public.{MIGRATION_TABLE} (version) VALUES ($1)", version)

    logger.info(f"Applied migration version {version}")


async def migrate_database(
    db_url: str,
    migrations_dir: Path,
    timeout: int = 300,
    retries: int = 3,
    dry_run: bool = False,
) -> tuple[int, int, bool]:
    """
    Migrate a single database.
    Returns (applied_count, total_count, success).
    """
    # Extract database name from URL
    from urllib.parse import urlparse

    parsed_url = urlparse(db_url)
    db_name = parsed_url.path.lstrip("/")  # Remove leading slash

    if not migrations_dir.exists():
        logger.warning(f"Migration directory {migrations_dir} not found, skipping {db_name}")
        return 0, 0, False

    migration_files = get_migration_files(migrations_dir)
    if not migration_files:
        logger.info(f"No migrations found for {db_name}")
        return 0, 0, False

    # Try to connect with retries
    conn = None
    for attempt in range(retries):
        try:
            conn = await asyncpg.connect(db_url)
            break
        except Exception as e:
            if attempt == retries - 1:
                logger.error(f"Failed to connect to {db_name} after {retries} attempts: {e}")
                return 0, 0, False
            await asyncio.sleep(2**attempt)  # Exponential backoff

    try:
        # Ensure migrations table exists
        if not dry_run:
            await ensure_migrations_table(conn)

        # Get applied migrations
        applied_migrations = await get_applied_migrations(conn) if not dry_run else set()

        applied_count = 0
        total_count = len(migration_files)
        has_failure = False

        for migration_file in migration_files:
            version = extract_version_from_filename(migration_file.name)

            if version in applied_migrations:
                logger.info(f"Skipping {migration_file.name} (already applied to {db_name})")
                continue

            logger.info(f"Applying {migration_file.name} to {db_name}...")

            success = await apply_migration_file(conn, migration_file, timeout, dry_run)
            if success:
                applied_count += 1
                logger.info(f"Applied {migration_file.name} to {db_name}")
            else:
                logger.error(f"Failed to apply {migration_file.name} to {db_name}")
                has_failure = True
                break

        return applied_count, total_count, not has_failure

    finally:
        if conn:
            await conn.close()


def load_tenant_migrations() -> list[tuple[str, list[str]]]:
    """Load and parse all tenant migration files once at startup.

    Returns an ordered list of (version, statements) tuples.
    Migration files are loaded in chronological order based on timestamp prefix.
    """
    migrations_dir = get_tenant_migrations_dir()

    logger.info(f"Looking for tenant migrations in directory: {migrations_dir}")
    if not migrations_dir.exists():
        raise MigrationError(f"Tenant migrations directory not found: {migrations_dir}")

    migrations = []

    # Load all timestamped migration files
    migration_files = get_migration_files(migrations_dir)
    logger.info(f"Found {len(migration_files)} tenant migration files")

    for migration_file in migration_files:
        version = extract_version_from_filename(migration_file.name)

        with open(migration_file) as f:
            migration_sql = f.read()
        migrations.append((version, parse_sql_statements(migration_sql)))

    logger.info(f"Loaded {len(migrations)} tenant migrations")
    for version, statements in migrations:
        logger.debug(f"Migration {version}: {len(statements)} statements")

    return migrations


async def mark_migration_as_applied(conn: asyncpg.Connection, version: str) -> None:
    """Mark a migration as applied in the schema_migrations table."""
    await ensure_migrations_table(conn)

    # Check if already applied
    exists = await conn.fetchval(
        f"SELECT EXISTS(SELECT 1 FROM public.{MIGRATION_TABLE} WHERE version = $1)", version
    )

    if exists:
        logger.warning(f"Migration {version} is already marked as applied")
        return

    # Insert the migration record
    await conn.execute(f"INSERT INTO public.{MIGRATION_TABLE} (version) VALUES ($1)", version)
    logger.info(f"Marked migration {version} as applied")


async def unmark_migration_as_applied(conn: asyncpg.Connection, version: str) -> bool:
    """
    Unmark a migration as applied (remove from schema_migrations table).
    Returns True if migration was unmarked, False if it wasn't applied.
    """
    await ensure_migrations_table(conn)

    # Remove the migration record
    result = await conn.execute(f"DELETE FROM public.{MIGRATION_TABLE} WHERE version = $1", version)

    # Check if any rows were affected
    if result == "DELETE 0":
        logger.warning(f"Migration {version} was not marked as applied")
        return False
    else:
        logger.info(f"Unmarked migration {version} (removed from applied migrations)")
        return True


def validate_migration_exists(version: str, migrations_dir: Path) -> tuple[bool, str | None]:
    """
    Validate that a migration file exists for the given version.
    Returns (exists, filename) tuple.
    """
    if not migrations_dir.exists():
        return False, None

    # Look for migration file with matching version prefix
    migration_files = get_migration_files(migrations_dir)

    for migration_file in migration_files:
        file_version = extract_version_from_filename(migration_file.name)
        if file_version == version:
            return True, migration_file.name

    return False, None
