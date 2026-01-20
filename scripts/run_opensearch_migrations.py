#!/usr/bin/env python3
"""
Run migrations on all tenant OpenSearch indexes.

Login to AWS, then run this script with:
    uv run python scripts/run_opensearch_migrations.py <REMAINING_ARGS_HERE>

Usage:
    # Delete a property from all tenant indexes
    python scripts/run_opensearch_migrations.py delete-property --property "metadata.old_field"

    # Delete a multi-field sub-field from all tenant indexes
    python scripts/run_opensearch_migrations.py delete-property --property "content.fields.raw"

    # Add a property to all tenant indexes
    python scripts/run_opensearch_migrations.py add-property --property "new_field" --mapping '{"type": "keyword"}'

    # Update index settings
    python scripts/run_opensearch_migrations.py update-settings --settings '{"number_of_replicas": 1}'

    # Dry run to see what would be changed
    python scripts/run_opensearch_migrations.py delete-property --property "metadata.old_field" --dry-run

    # Run on specific tenant only
    python scripts/run_opensearch_migrations.py delete-property --property "metadata.old_field" --tenant abc123def456
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.clients.opensearch import OpenSearchClient


def get_tenant_index_name(tenant_id: str) -> str:
    return f"tenant-{tenant_id}-v1"


def get_control_database_url() -> str:
    """Get control database URL from environment variable."""
    url = os.environ.get("CONTROL_DATABASE_URL")
    if not url:
        print("Error: CONTROL_DATABASE_URL environment variable is required")
        sys.exit(1)
    return url


async def create_opensearch_client_with_aws_auth() -> OpenSearchClient:
    """Create an OpenSearch client using AWS SigV4 authentication.

    Returns:
        OpenSearchClient configured with AWS SigV4 auth

    Raises:
        RuntimeError: If required environment variables are missing or client creation fails
    """
    # Get OpenSearch host from environment
    host = os.environ.get("OPENSEARCH_DOMAIN_HOST")
    if not host:
        raise RuntimeError(
            "OPENSEARCH_DOMAIN_HOST environment variable is required. "
            "Set it to your OpenSearch domain host (e.g., search-domain.us-east-1.es.amazonaws.com)"
        )

    port = os.environ.get("OPENSEARCH_PORT", "443")
    # Default to HTTPS for port 443, HTTP for other ports
    default_ssl = "true" if port == "443" else "false"
    use_ssl = os.environ.get("OPENSEARCH_USE_SSL", default_ssl).lower() in ("true", "1", "yes")
    protocol = "https" if use_ssl else "http"

    print(f"OpenSearch host: {host}:{port}")
    print(f"Protocol: {protocol}")
    print(f"SSL enabled: {use_ssl}")
    print("Using AWS SigV4 authentication")

    try:
        # Create client with AWS SigV4 auth
        opensearch_url = f"{protocol}://{host}:{port}"
        client = OpenSearchClient(opensearch_url)
        print("Successfully created OpenSearch client with AWS SigV4 authentication")

        # Test connectivity
        try:
            info = await client.client.info()
            print(f"Connected to OpenSearch cluster: {info.get('cluster_name', 'unknown')}")
            print(f"OpenSearch version: {info.get('version', {}).get('number', 'unknown')}")
        except Exception as info_error:
            print(f"Warning: Could not retrieve cluster info: {info_error}")

        return client
    except Exception as e:
        raise RuntimeError(
            f"Failed to create OpenSearch client: {e}. "
            "Check your credentials and OpenSearch domain accessibility."
        )


async def get_tenant_ids(control_db_url: str) -> list[str]:
    """Get all tenant IDs from the control database."""
    conn = await asyncpg.connect(control_db_url)
    try:
        rows = await conn.fetch("SELECT id FROM tenants WHERE state = 'provisioned'")
        return [row["id"] for row in rows]
    finally:
        await conn.close()


async def get_index_mapping(client: OpenSearchClient, index_name: str) -> dict[str, Any]:
    """Get the current mapping for an index."""
    try:
        response = await client.client.indices.get_mapping(index=index_name)
        return response.get(index_name, {}).get("mappings", {})
    except Exception as e:
        raise RuntimeError(f"Failed to get mapping for index {index_name}: {e}")


async def update_index_mapping(
    client: OpenSearchClient, index_name: str, mapping_update: dict[str, Any]
) -> dict[str, Any]:
    """Update the mapping for an index."""
    try:
        response = await client.client.indices.put_mapping(index=index_name, body=mapping_update)
        return response
    except Exception as e:
        raise RuntimeError(f"Failed to update mapping for index {index_name}: {e}")


def delete_property_from_mapping(
    mapping: dict[str, Any], property_path: str
) -> tuple[dict[str, Any], bool]:
    """Delete a property from a mapping using dot notation path.

    Args:
        mapping: The mapping dictionary to modify
        property_path: Dot-separated path to the property
                      Examples: "metadata.old_field", "content.fields.raw", "metadata.user.fields.keyword"

    Returns:
        Tuple of (modified_mapping, was_changed)
    """
    # Deep copy to avoid modifying original
    modified_mapping = json.loads(json.dumps(mapping))

    # Parse the path to handle both regular properties and multi-field sub-fields
    path_parts = property_path.split(".")
    current = modified_mapping.get("properties", {})

    # Navigate to the parent of the target property
    i = 0
    while i < len(path_parts) - 1:
        part = path_parts[i]

        if part not in current:
            # Property doesn't exist
            return mapping, False

        # Check if the next part is "fields" - this indicates a multi-field navigation
        next_part = path_parts[i + 1] if i + 1 < len(path_parts) else None

        if next_part == "fields" and "fields" in current[part]:
            # Navigate into the fields of this multi-field property
            current = current[part]["fields"]
            # Skip both current part and "fields" part
            i += 2
        elif current[part].get("type") == "object" and "properties" in current[part]:
            # Navigate into object properties
            current = current[part]["properties"]
            i += 1
        else:
            # Can't navigate further, property doesn't exist or isn't navigable
            return mapping, False

    # Delete the final property
    final_property = path_parts[-1]
    if final_property in current:
        del current[final_property]
        return modified_mapping, True
    else:
        # Property doesn't exist
        return mapping, False


def add_property_to_mapping(
    mapping: dict[str, Any], property_path: str, property_mapping: dict[str, Any]
) -> tuple[dict[str, Any], bool]:
    """Add a property to a mapping using dot notation path.

    Args:
        mapping: The mapping dictionary to modify
        property_path: Dot-separated path to the property (e.g., "new_field" or "metadata.new_field")
        property_mapping: The mapping definition for the new property

    Returns:
        Tuple of (modified_mapping, was_changed)
    """
    # Deep copy to avoid modifying original
    modified_mapping = json.loads(json.dumps(mapping))

    # Ensure properties exists
    if "properties" not in modified_mapping:
        modified_mapping["properties"] = {}

    # Navigate to the correct location and add the property
    path_parts = property_path.split(".")
    current = modified_mapping["properties"]

    # Navigate/create path to parent of target property
    for part in path_parts[:-1]:
        if part not in current:
            # Create the intermediate object property
            current[part] = {"type": "object", "properties": {}}

        if current[part].get("type") == "object":
            if "properties" not in current[part]:
                current[part]["properties"] = {}
            current = current[part]["properties"]
        else:
            # Can't add property here, existing field is not an object
            return mapping, False

    # Add the final property
    final_property = path_parts[-1]
    if final_property in current:
        # Property already exists
        return mapping, False

    current[final_property] = property_mapping
    return modified_mapping, True


async def run_delete_property_migration(
    tenant_id: str,
    property_path: str,
    client: OpenSearchClient,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run delete property migration on a single tenant index."""
    index_name = get_tenant_index_name(tenant_id)
    result = {
        "tenant_id": tenant_id,
        "index_name": index_name,
        "success": False,
        "message": "",
        "changed": False,
    }

    try:
        # Check if index exists
        if not await client.index_exists(index_name):
            result["message"] = f"Index {index_name} does not exist"
            result["success"] = True  # Not an error, just no work to do
            return result

        # Get current mapping
        current_mapping = await get_index_mapping(client, index_name)

        # Delete property from mapping
        new_mapping, was_changed = delete_property_from_mapping(current_mapping, property_path)

        if not was_changed:
            result["message"] = (
                f"Property '{property_path}' not found in mapping. Keys in mapping: {list(new_mapping.keys())}"
            )
            result["success"] = True
            return result

        if dry_run:
            result["message"] = f"Would delete property '{property_path}' from mapping"
            result["success"] = True
            result["changed"] = True
            return result

        # Update the mapping
        await update_index_mapping(client, index_name, new_mapping)

        result["message"] = f"Successfully deleted property '{property_path}' from mapping"
        result["success"] = True
        result["changed"] = True

    except Exception as e:
        result["message"] = f"Error: {e}"
        result["success"] = False

    return result


async def run_add_property_migration(
    tenant_id: str,
    property_path: str,
    property_mapping: dict[str, Any],
    client: OpenSearchClient,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run add property migration on a single tenant index."""
    index_name = get_tenant_index_name(tenant_id)
    result = {
        "tenant_id": tenant_id,
        "index_name": index_name,
        "success": False,
        "message": "",
        "changed": False,
    }

    try:
        # Check if index exists
        if not await client.index_exists(index_name):
            result["message"] = f"Index {index_name} does not exist"
            result["success"] = True  # Not an error, just no work to do
            return result

        # Get current mapping
        current_mapping = await get_index_mapping(client, index_name)

        # Add property to mapping
        new_mapping, was_changed = add_property_to_mapping(
            current_mapping, property_path, property_mapping
        )

        if not was_changed:
            result["message"] = f"Property '{property_path}' already exists or cannot be added"
            result["success"] = True
            return result

        if dry_run:
            result["message"] = f"Would add property '{property_path}' to mapping"
            result["success"] = True
            result["changed"] = True
            return result

        # Update the mapping
        await update_index_mapping(client, index_name, new_mapping)

        result["message"] = f"Successfully added property '{property_path}' to mapping"
        result["success"] = True
        result["changed"] = True

    except Exception as e:
        result["message"] = f"Error: {e}"
        result["success"] = False

    return result


async def main():
    parser = argparse.ArgumentParser(description="Run migrations on all tenant OpenSearch indexes")
    subparsers = parser.add_subparsers(dest="command", help="Migration command to run")

    # Delete property command
    delete_parser = subparsers.add_parser(
        "delete-property", help="Delete a property from index mappings"
    )
    delete_parser.add_argument(
        "--property", required=True, help="Property path to delete (e.g., 'metadata.old_field')"
    )

    # Add property command
    add_parser = subparsers.add_parser("add-property", help="Add a property to index mappings")
    add_parser.add_argument(
        "--property", required=True, help="Property path to add (e.g., 'new_field')"
    )
    add_parser.add_argument(
        "--mapping", required=True, help="JSON mapping definition for the property"
    )

    # Common arguments
    for subparser in [delete_parser, add_parser]:
        subparser.add_argument(
            "--dry-run", action="store_true", help="Show what would be done without executing"
        )
        subparser.add_argument("--tenant", help="Run migration only on specific tenant ID")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load environment variables
    load_dotenv()

    # Get control database URL
    control_db_url = get_control_database_url()

    # Create OpenSearch client
    try:
        client = await create_opensearch_client_with_aws_auth()
    except Exception as e:
        print(f"Error creating OpenSearch client: {e}")
        sys.exit(1)

    # Get tenant IDs
    if args.tenant:
        tenant_ids = [args.tenant]
        print(f"Running migration on single tenant: {args.tenant}")
    else:
        print("Connecting to control database...")
        tenant_ids = await get_tenant_ids(control_db_url)
        print(f"Found {len(tenant_ids)} provisioned tenants")

    if not tenant_ids:
        print("No tenants found")
        return

    if args.dry_run:
        print("\n--- DRY RUN MODE ---")

    print(f"\nRunning {args.command} migration...")
    print(f"OpenSearch host: {os.environ.get('OPENSEARCH_DOMAIN_HOST', 'unknown')}")

    # Run migrations
    results = []
    success_count = 0
    failed_count = 0
    changed_count = 0

    for tenant_id in tenant_ids:
        try:
            if args.command == "delete-property":
                result = await run_delete_property_migration(
                    tenant_id=tenant_id,
                    property_path=args.property,
                    client=client,
                    dry_run=args.dry_run,
                )
            elif args.command == "add-property":
                try:
                    property_mapping = json.loads(args.mapping)
                except json.JSONDecodeError as e:
                    print(f"Error parsing mapping JSON: {e}")
                    sys.exit(1)

                result = await run_add_property_migration(
                    tenant_id=tenant_id,
                    property_path=args.property,
                    property_mapping=property_mapping,
                    client=client,
                    dry_run=args.dry_run,
                )
            else:
                print(f"Unknown command: {args.command}")
                sys.exit(1)

            results.append(result)

            if result["success"]:
                success_count += 1
                if result["changed"]:
                    changed_count += 1
                    status = "✓ (changed)" if not args.dry_run else "✓ (would change)"
                else:
                    status = "✓ (no change)"
            else:
                failed_count += 1
                status = "✗ (failed)"

            print(f"{status} {tenant_id}: {result['message']}")

        except Exception as e:
            failed_count += 1
            print(f"✗ (failed) {tenant_id}: Unexpected error: {e}")

    # Summary
    print("\n" + "=" * 60)
    action = "would be changed" if args.dry_run else "changed"
    print(
        f"Migration complete: {success_count} successful, {failed_count} failed, {changed_count} {action}"
    )

    if failed_count > 0:
        print("\nFailed migrations:")
        for result in results:
            if not result["success"]:
                print(f"  - {result['tenant_id']}: {result['message']}")
        sys.exit(1)

    await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
