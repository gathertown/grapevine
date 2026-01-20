#!/usr/bin/env python3
"""
Script to repair tenant table permissions for all tenants using control database.
Supports multiple tables and can be easily extended for emergency permission repairs.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncpg

from src.steward.models import TenantCredentials
from src.steward.postgres import _harden_pg_schema
from src.utils.config import get_control_database_url
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def get_tenant_connection_info():
    """Get tenant connection information from control database."""
    try:
        control_db_url = get_control_database_url()
    except ValueError as e:
        logger.error(f"Control database configuration error: {e}")
        logger.error("Please set CONTROL_DATABASE_URL environment variable")
        raise

    try:
        conn = await asyncpg.connect(control_db_url)
    except Exception as e:
        logger.error(f"Failed to connect to control database: {e}")
        raise

    try:
        # Get all provisioned tenants - assuming the control DB has tenant connection info
        tenants = await conn.fetch("""
            SELECT id, workos_org_id, state
            FROM tenants
            WHERE state = 'provisioned'
            ORDER BY id
        """)
        return tenants
    finally:
        await conn.close()


async def connect_to_tenant_directly(tenant_id: str, db_url: str):
    """Connect directly to a tenant database using provided URL."""
    try:
        conn = await asyncpg.connect(db_url)
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to tenant {tenant_id}: {e}")
        return None


async def repair_tenant_permissions(tenant_id: str, tenant_db_url: str, dry_run: bool = False):
    """Repair table permissions for a tenant."""
    logger.info(f"Processing tenant: {tenant_id}")

    conn = await connect_to_tenant_directly(tenant_id, tenant_db_url)
    if not conn:
        return False

    try:
        # Find the tenant app role (must match exact pattern {tenant_id}_app_rw)
        role_result = await conn.fetchrow(
            """
            SELECT rolname
            FROM pg_roles
            WHERE rolcanlogin = true
            AND rolsuper = false
            AND rolname = $1
        """,
            f"{tenant_id}_app_rw",
        )

        if not role_result:
            logger.error(
                f"No tenant app role found for {tenant_id}. Expected role: {tenant_id}_app_rw"
            )
            return False

        role_name = role_result["rolname"]
        logger.info(f"Found tenant app role: {role_name}")

        # Discover all tables in the tenant database
        all_tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """)

        if not all_tables:
            logger.warning(f"No tables found in tenant {tenant_id}")
            return False

        table_names = [table["table_name"] for table in all_tables]

        print(f"\nTenant {tenant_id}:")
        print(f"  Role: {role_name}")
        print(f"  Tables found: {', '.join(table_names)}")

        overall_success = True

        # Use the steward's hardening function for exact consistency
        print("  Applying steward hardening function:")

        if dry_run:
            print("    Would run: _harden_pg_schema() from steward")
            print("    This includes:")
            print("      - REVOKE ALL ON SCHEMA public FROM PUBLIC")
            print("      - GRANT ALL ON SCHEMA public")
            print("      - GRANT ALL ON ALL TABLES/SEQUENCES/FUNCTIONS")
            print("      - ALTER DEFAULT PRIVILEGES for future objects")
        else:
            try:
                # Create TenantCredentials object for steward function
                # Extract database name from connection (format: db_{tenant_id})
                db_name = f"db_{tenant_id}"
                creds = TenantCredentials(
                    tenant_id=tenant_id,
                    db_name=db_name,
                    db_rw_user=role_name,
                    db_rw_pass="",  # Not needed for hardening function
                )

                await _harden_pg_schema(creds)
                print("    ✅ Applied steward hardening (all permissions granted)")

            except Exception as e:
                print(f"    ❌ Failed to apply steward hardening: {e}")
                overall_success = False

        if overall_success and not dry_run:
            logger.info(f"Successfully processed permissions for tenant {tenant_id}")
        elif dry_run:
            logger.info(f"Dry run completed for tenant {tenant_id}")

        return True

    finally:
        await conn.close()


def build_tenant_db_url(tenant_id: str) -> str:
    """Build tenant database URL from environment variables."""
    import os

    host = os.environ.get("PG_TENANT_DATABASE_HOST")
    port = os.environ.get("PG_TENANT_DATABASE_PORT", "5432")
    username = os.environ.get("PG_TENANT_DATABASE_ADMIN_USERNAME")
    password = os.environ.get("PG_TENANT_DATABASE_ADMIN_PASSWORD")

    if not all([host, username, password]):
        missing = []
        if not host:
            missing.append("PG_TENANT_DATABASE_HOST")
        if not username:
            missing.append("PG_TENANT_DATABASE_ADMIN_USERNAME")
        if not password:
            missing.append("PG_TENANT_DATABASE_ADMIN_PASSWORD")

        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    return f"postgresql://{username}:{password}@{host}:{port}/db_{tenant_id}"


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Repair tenant table permissions for all tenants (auto-discovers all tables)"
    )
    parser.add_argument("--tenant-id", help="Specific tenant ID to repair (optional)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--db-url-pattern",
        help="Custom database URL pattern with {tenant_id} placeholder (default: use PG_TENANT_DATABASE_* env vars)",
    )

    args = parser.parse_args()

    # Get tenant info from control database
    tenants = await get_tenant_connection_info()

    if args.tenant_id:
        tenants = [t for t in tenants if t["id"] == args.tenant_id]
        if not tenants:
            logger.error(f"Tenant {args.tenant_id} not found in control database")
            return

    print(f"Processing {len(tenants)} tenant(s)...")
    if args.dry_run:
        print("DRY RUN MODE - No changes will be made")

    success_count = 0
    error_count = 0

    for tenant in tenants:
        tenant_id = tenant["id"]

        # Build tenant database URL
        try:
            if args.db_url_pattern:
                # Use custom pattern if provided
                tenant_db_url = args.db_url_pattern.format(tenant_id=tenant_id)
            else:
                # Use environment variables
                tenant_db_url = build_tenant_db_url(tenant_id)
        except Exception as e:
            logger.error(f"Failed to build database URL for tenant {tenant_id}: {e}")
            error_count += 1
            continue

        try:
            success = await repair_tenant_permissions(tenant_id, tenant_db_url, args.dry_run)
            if success:
                success_count += 1
            else:
                error_count += 1
        except Exception as e:
            logger.error(f"Failed to process tenant {tenant_id}: {e}")
            error_count += 1

    print(f"\nCompleted: {success_count} successful, {error_count} errors")


if __name__ == "__main__":
    asyncio.run(main())
