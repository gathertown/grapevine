#!/usr/bin/env python
"""
Get configuration value(s) for a tenant from their database.

This script accepts a tenant ID or WorkOS org ID (org_*) and a config key pattern,
connects to the tenant database, and retrieves matching configuration values.

The config key can use SQL LIKE wildcards (% for multiple characters, _ for single character).

Usage:
    python scripts/get_tenant_config.py <tenant_id|workos_org_id> <config_key_pattern>
    python scripts/get_tenant_config.py org_01J123ABC456XYZ SLACK_BOT_QA_ALL_CHANNELS
    python scripts/get_tenant_config.py org_01J123ABC456XYZ "SLACK_BOT%"
    python scripts/get_tenant_config.py 1234567890abcdef "%"
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from src.utils.config import get_control_database_url


async def get_tenant_id_from_workos_org(workos_org_id: str) -> str | None:
    """Look up the internal tenant ID from a WorkOS organization ID."""
    control_db_url = get_control_database_url()

    conn = await asyncpg.connect(control_db_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT id FROM public.tenants
            WHERE workos_org_id = $1
              AND state = 'provisioned'
            """,
            workos_org_id,
        )
        if row:
            return row["id"]
        return None
    finally:
        await conn.close()


def get_ssm_parameter(ssm_client, parameter_name: str) -> str | None:
    """Get a parameter value from AWS SSM Parameter Store."""
    try:
        response = ssm_client.get_parameter(Name=parameter_name, WithDecryption=True)
        return response["Parameter"]["Value"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "ParameterNotFound":
            return None
        raise


async def get_tenant_database_url(tenant_id: str) -> str:
    """Generate the PostgreSQL connection URL for a tenant."""
    region = os.environ.get("AWS_REGION", "us-east-1")

    try:
        ssm = boto3.client("ssm", region_name=region)
    except NoCredentialsError:
        raise RuntimeError(
            "AWS credentials not found. Please configure AWS credentials:\n"
            "  export AWS_PROFILE=gather-ai-tf && aws-login"
        )

    # Get PostgreSQL credentials from SSM
    db_name = get_ssm_parameter(ssm, f"/{tenant_id}/credentials/postgresql/db_name")
    db_user = get_ssm_parameter(ssm, f"/{tenant_id}/credentials/postgresql/db_rw_user")
    db_pass = get_ssm_parameter(ssm, f"/{tenant_id}/credentials/postgresql/db_rw_pass")

    missing = []
    if not db_name:
        missing.append("db_name")
    if not db_user:
        missing.append("db_rw_user")
    if not db_pass:
        missing.append("db_rw_pass")

    if missing:
        raise ValueError(
            f"Missing PostgreSQL SSM credentials for tenant {tenant_id}: {', '.join(missing)}"
        )

    # Get database host/port from environment
    pg_host = os.environ.get("PG_TENANT_DATABASE_HOST")
    if not pg_host:
        raise RuntimeError(
            "PG_TENANT_DATABASE_HOST environment variable is required. "
            "Set it to your tenant database host (e.g., your-db.cluster-xyz.us-east-1.rds.amazonaws.com)"
        )

    pg_port = os.environ.get("PG_TENANT_DATABASE_PORT", "5432")
    sslmode = os.environ.get("PG_TENANT_DATABASE_SSLMODE", "require")

    return f"postgresql://{db_user}:{db_pass}@{pg_host}:{pg_port}/{db_name}?sslmode={sslmode}"


async def get_config_values(tenant_id: str, config_key_pattern: str) -> list[tuple[str, str]]:
    """Get configuration values from the tenant database matching the pattern.

    Returns a list of (key, value) tuples.
    """
    db_url = await get_tenant_database_url(tenant_id)

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            """
            SELECT key, value FROM config
            WHERE key LIKE $1
            ORDER BY key
            """,
            config_key_pattern,
        )
        return [(row["key"], row["value"]) for row in rows]
    finally:
        await conn.close()


async def main():
    if len(sys.argv) != 3:
        print(
            "Usage: python scripts/get_tenant_config.py <tenant_id|workos_org_id> <config_key_pattern>",
            file=sys.stderr,
        )
        print("\nExamples:", file=sys.stderr)
        print(
            "  python scripts/get_tenant_config.py org_01J123ABC456XYZ SLACK_BOT_QA_ALL_CHANNELS",
            file=sys.stderr,
        )
        print(
            "  python scripts/get_tenant_config.py org_01J123ABC456XYZ 'SLACK_BOT%'",
            file=sys.stderr,
        )
        print(
            "  python scripts/get_tenant_config.py 1234567890abcdef '%'",
            file=sys.stderr,
        )
        print("\nConfig key pattern supports SQL LIKE wildcards:", file=sys.stderr)
        print("  % - matches any sequence of characters", file=sys.stderr)
        print("  _ - matches any single character", file=sys.stderr)
        print("\nRequired environment variables:", file=sys.stderr)
        print(
            "  CONTROL_DATABASE_URL - Control database connection string (for WorkOS lookup)",
            file=sys.stderr,
        )
        print("  PG_TENANT_DATABASE_HOST - Tenant database host", file=sys.stderr)
        print("  AWS_REGION - AWS region (default: us-east-1)", file=sys.stderr)
        print("  AWS_PROFILE or AWS credentials - For SSM access", file=sys.stderr)
        sys.exit(1)

    identifier = sys.argv[1]
    config_key_pattern = sys.argv[2]

    try:
        # Step 1: Determine if we have a tenant ID or WorkOS org ID
        if identifier.startswith("org_"):
            # It's a WorkOS org ID, look up the tenant ID
            tenant_id = await get_tenant_id_from_workos_org(identifier)
            if not tenant_id:
                raise ValueError(f"No provisioned tenant found for WorkOS org ID: {identifier}")
            print(f"Found tenant ID: {tenant_id} for WorkOS org: {identifier}", file=sys.stderr)
        else:
            # Assume it's a tenant ID
            tenant_id = identifier
            print(f"Using tenant ID: {tenant_id}", file=sys.stderr)

        # Step 2: Get the config values
        results = await get_config_values(tenant_id, config_key_pattern)

        if results:
            print(f"\nFound {len(results)} config value(s):\n", file=sys.stderr)
            for key, value in results:
                print(f"{key}: {value}")
        else:
            print(
                f"\nNo config keys found matching pattern '{config_key_pattern}' for tenant {tenant_id}",
                file=sys.stderr,
            )
            sys.exit(1)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
