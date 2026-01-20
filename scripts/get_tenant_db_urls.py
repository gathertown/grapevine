#!/usr/bin/env python
"""
Generate fully qualified PostgreSQL and OpenSearch URLs for a tenant.

This script accepts either a tenant ID or WorkOS org ID (org_*), retrieves
the database and OpenSearch credentials from AWS SSM Parameter Store, and constructs
the connection URLs.

Usage:
    python scripts/get_tenant_db_urls.py <tenant_id|workos_org_id>
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


async def get_tenant_opensearch_url(tenant_id: str) -> str:
    """Generate the OpenSearch URL for a tenant.

    Note: All tenants now use shared admin credentials. Tenant isolation is enforced
    by application-layer index name filtering.
    """
    # Use shared admin credentials from environment
    os_user = os.environ.get("OPENSEARCH_ADMIN_USERNAME")
    os_pass = os.environ.get("OPENSEARCH_ADMIN_PASSWORD")

    missing = []
    if not os_user:
        missing.append("OPENSEARCH_ADMIN_USERNAME")
    if not os_pass:
        missing.append("OPENSEARCH_ADMIN_PASSWORD")

    if missing:
        raise ValueError(
            f"Missing OpenSearch admin credentials from environment: {', '.join(missing)}"
        )

    # Get OpenSearch host from environment
    host = os.environ.get("OPENSEARCH_DOMAIN_HOST")
    if not host:
        raise RuntimeError(
            "OPENSEARCH_DOMAIN_HOST environment variable is required. "
            "Set it to your OpenSearch domain host (e.g., search-domain.us-east-1.es.amazonaws.com)"
        )

    port = os.environ.get("OPENSEARCH_PORT", "443")

    # Construct and return the OpenSearch URL with shared admin credentials
    return f"https://{os_user}:{os_pass}@{host}:{port}"


async def get_tenant_urls(identifier: str) -> tuple[str, str, str]:
    """Generate both database and OpenSearch URLs for a tenant.

    Args:
        identifier: Either a tenant_id or WorkOS org ID (org_*)

    Returns:
        Tuple of (db_url, os_url, tenant_id)
    """
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

    # Step 2: Verify AWS credentials and get SSM client
    region = os.environ.get("AWS_REGION", "us-east-1")
    try:
        # Create STS client to check account
        sts = boto3.client("sts", region_name=region)
        caller_identity = sts.get_caller_identity()
        account_id = caller_identity["Account"]
        user_arn = caller_identity["Arn"]

        print(f"AWS Account: {account_id}", file=sys.stderr)
        print(f"AWS Identity: {user_arn}", file=sys.stderr)

        ssm = boto3.client("ssm", region_name=region)
    except NoCredentialsError:
        raise RuntimeError(
            "AWS credentials not found. Please configure AWS credentials:\n"
            "  export AWS_PROFILE=gather-ai-tf && aws-login"
        )

    # Step 3: Get PostgreSQL credentials and construct URL
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

    db_url = f"postgresql://{db_user}:{db_pass}@{pg_host}:{pg_port}/{db_name}?sslmode={sslmode}"

    # Step 4: Get OpenSearch URL
    os_url = await get_tenant_opensearch_url(tenant_id)

    return db_url, os_url, tenant_id


async def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python scripts/get_tenant_db_url.py <tenant_id|workos_org_id>", file=sys.stderr
        )
        print("\nExamples:", file=sys.stderr)
        print("  python scripts/get_tenant_db_url.py org_01J123ABC456XYZ", file=sys.stderr)
        print("  python scripts/get_tenant_db_url.py 1234567890abcdef", file=sys.stderr)
        print(
            "\nThis will create a file .env.tenant-<tenant_id> with the connection URLs",
            file=sys.stderr,
        )
        print("\nRequired environment variables:", file=sys.stderr)
        print(
            "  CONTROL_DATABASE_URL - Control database connection string (for WorkOS lookup)",
            file=sys.stderr,
        )
        print("  PG_TENANT_DATABASE_HOST - Tenant database host", file=sys.stderr)
        print("  OPENSEARCH_DOMAIN_HOST - OpenSearch domain host", file=sys.stderr)
        print(
            "  OPENSEARCH_ADMIN_USERNAME - OpenSearch admin username (shared across tenants)",
            file=sys.stderr,
        )
        print(
            "  OPENSEARCH_ADMIN_PASSWORD - OpenSearch admin password (shared across tenants)",
            file=sys.stderr,
        )
        print("  AWS_REGION - AWS region (default: us-east-1)", file=sys.stderr)
        print("  AWS_PROFILE or AWS credentials - For SSM access", file=sys.stderr)
        sys.exit(1)

    identifier = sys.argv[1]

    try:
        db_url, os_url, tenant_id = await get_tenant_urls(identifier)

        # Write to .env.tenant-[id] file
        env_file = f".env.tenant-{tenant_id}"
        with open(env_file, "w") as f:
            f.write(f'TENANT_DATABASE_URL="{db_url}"\n')
            f.write(f'TENANT_OPENSEARCH_URL="{os_url}"\n')

        print(f"\nSuccessfully wrote tenant URLs to {env_file}", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
