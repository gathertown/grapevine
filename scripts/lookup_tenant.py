#!/usr/bin/env python
"""
Look up tenant information by tenant ID or WorkOS organization ID.

This script accepts a tenant ID or WorkOS org ID (org_*) and displays:
- Tenant ID (internal identifier)
- WorkOS organization ID (external identifier)
- Organization name (from WorkOS)
- Billing mode (grapevine_managed or gather_managed)
- Provisioning state and dates
- Organization creation date

Usage:
    python scripts/lookup_tenant.py <tenant_id|workos_org_id>
    python scripts/lookup_tenant.py org_01J123ABC456XYZ
    python scripts/lookup_tenant.py 1234567890abcdef
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from workos import WorkOSClient

from src.utils.config import get_config_value, get_control_database_url


def initialize_workos() -> WorkOSClient:
    """Initialize WorkOS client using environment variables."""
    api_key = get_config_value("WORKOS_API_KEY")
    client_id = get_config_value("WORKOS_CLIENT_ID")

    if not api_key:
        raise ValueError("WORKOS_API_KEY environment variable is required")
    if not client_id:
        raise ValueError("WORKOS_CLIENT_ID environment variable is required")

    return WorkOSClient(api_key=api_key, client_id=client_id)


async def lookup_by_workos_org_id(workos_org_id: str) -> dict | None:
    """Look up tenant information by WorkOS organization ID."""
    control_db_url = get_control_database_url()

    conn = await asyncpg.connect(control_db_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT id, workos_org_id, state, billing_mode, error_message,
                   created_at, updated_at, provisioned_at, deleted_at
            FROM public.tenants
            WHERE workos_org_id = $1
            """,
            workos_org_id,
        )
        if row:
            return dict(row)
        return None
    finally:
        await conn.close()


async def lookup_by_tenant_id(tenant_id: str) -> dict | None:
    """Look up tenant information by internal tenant ID."""
    control_db_url = get_control_database_url()

    conn = await asyncpg.connect(control_db_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT id, workos_org_id, state, billing_mode, error_message,
                   created_at, updated_at, provisioned_at, deleted_at
            FROM public.tenants
            WHERE id = $1
            """,
            tenant_id,
        )
        if row:
            return dict(row)
        return None
    finally:
        await conn.close()


def get_workos_org_name(workos_client: WorkOSClient, workos_org_id: str) -> str | None:
    """Get organization name from WorkOS."""
    try:
        org = workos_client.organizations.get_organization(workos_org_id)
        return org.name if org else None
    except Exception as e:
        print(f"Warning: Could not fetch organization name from WorkOS: {e}", file=sys.stderr)
        return None


def format_datetime(dt) -> str:
    """Format datetime for display."""
    if dt is None:
        return "N/A"
    return str(dt)


def format_billing_mode(billing_mode: str) -> str:
    """Format billing mode for display."""
    if billing_mode == "grapevine_managed":
        return "Grapevine Managed"
    elif billing_mode == "gather_managed":
        return "Gather Managed"
    return billing_mode or "Unknown"


async def main():
    if len(sys.argv) != 2:
        print(
            "Usage: python scripts/lookup_tenant.py <tenant_id|workos_org_id>",
            file=sys.stderr,
        )
        print("\nExamples:", file=sys.stderr)
        print("  python scripts/lookup_tenant.py org_01J123ABC456XYZ", file=sys.stderr)
        print("  python scripts/lookup_tenant.py 1234567890abcdef", file=sys.stderr)
        print("\nRequired environment variables:", file=sys.stderr)
        print("  CONTROL_DATABASE_URL - Control database connection string", file=sys.stderr)
        print("  WORKOS_API_KEY - WorkOS API key (for org name lookup)", file=sys.stderr)
        print("  WORKOS_CLIENT_ID - WorkOS client ID (for org name lookup)", file=sys.stderr)
        sys.exit(1)

    identifier = sys.argv[1]

    try:
        # Step 1: Look up tenant information from control database
        tenant_info = None

        if identifier.startswith("org_"):
            # It's a WorkOS org ID
            tenant_info = await lookup_by_workos_org_id(identifier)
        else:
            # Assume it's a tenant ID
            tenant_info = await lookup_by_tenant_id(identifier)

        if not tenant_info:
            print(f"❌ No tenant found for identifier: {identifier}", file=sys.stderr)
            sys.exit(1)

        # Step 2: Get organization name from WorkOS
        workos_client = initialize_workos()
        org_name = get_workos_org_name(workos_client, tenant_info["workos_org_id"])

        # Step 3: Display results
        print("\n" + "=" * 80)
        print("TENANT INFORMATION")
        print("=" * 80)
        print(f"Tenant ID:              {tenant_info['id']}")
        print(f"WorkOS Organization ID: {tenant_info['workos_org_id']}")
        print(f"Organization Name:      {org_name or 'Unknown'}")
        print(f"Billing Mode:           {format_billing_mode(tenant_info['billing_mode'])}")
        print()
        print(f"State:                  {tenant_info['state']}")
        print(f"Created At:             {format_datetime(tenant_info['created_at'])}")
        print(f"Updated At:             {format_datetime(tenant_info['updated_at'])}")
        print(f"Provisioned At:         {format_datetime(tenant_info['provisioned_at'])}")
        print(f"Deleted At:             {format_datetime(tenant_info['deleted_at'])}")

        if tenant_info["error_message"]:
            print(f"\n⚠️  Error Message:        {tenant_info['error_message']}")

        print("=" * 80)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
