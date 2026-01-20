#!/usr/bin/env python3
"""
Backfill permissions data to OpenSearch and TurboPuffer.

This script updates existing documents and chunks in vector stores to include
cached permissions fields for fast filtering.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncpg

from src.clients.tenant_db import tenant_db_manager
from src.clients.tenant_opensearch import _tenant_opensearch_manager
from src.clients.turbopuffer import get_turbopuffer_client
from src.utils.config import get_control_database_url
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def get_tenant_ids() -> list[str]:
    """Get all tenant IDs from the control database."""
    control_db_url = get_control_database_url()

    conn = await asyncpg.connect(control_db_url)
    try:
        rows = await conn.fetch("""
            SELECT id FROM tenants
            WHERE state = 'provisioned'
            ORDER BY id
        """)
        return [row["id"] for row in rows]
    finally:
        await conn.close()


async def backfill_opensearch_permissions(tenant_id: str) -> None:
    """Backfill permissions for OpenSearch documents."""
    logger.info(f"Backfilling OpenSearch permissions for tenant {tenant_id}")

    async with (
        tenant_db_manager.acquire_pool(tenant_id) as db_pool,
        _tenant_opensearch_manager.acquire_client(tenant_id) as (opensearch_client, index_name),
        db_pool.acquire() as conn,
    ):
        # Get all documents with their permissions
        rows = await conn.fetch("""
                SELECT d.id, dp.permission_policy, dp.permission_allowed_tokens
                FROM documents d
                LEFT JOIN document_permissions dp ON d.id = dp.document_id
            """)

        if not rows:
            logger.info(f"No documents found for tenant {tenant_id}")
            return

        # Prepare bulk update for OpenSearch
        bulk_updates = list[dict[str, Any]]()
        for row in rows:
            doc_id = row["id"]
            permission_policy = row["permission_policy"] or "tenant"  # Default fallback
            permission_allowed_tokens = row["permission_allowed_tokens"] or []

            # OpenSearch bulk format requires metadata line followed by document
            bulk_updates.append(
                {
                    "update": {
                        "_index": index_name,
                        "_id": doc_id,
                    }
                }
            )
            bulk_updates.append(
                {
                    "doc": {
                        "permission_policy": permission_policy,
                        "permission_allowed_tokens": permission_allowed_tokens,
                    },
                    "doc_as_upsert": True,  # Create document with just permissions if it doesn't exist
                }
            )

        if bulk_updates:
            # Execute bulk update
            response = await opensearch_client.client.bulk(body=bulk_updates)
            if response.get("errors", False):
                logger.error(f"OpenSearch bulk update had errors: {response}")
            else:
                logger.info(f"Successfully updated {len(bulk_updates)} documents in OpenSearch")


async def backfill_turbopuffer_permissions(tenant_id: str) -> None:
    """Backfill permissions for TurboPuffer chunks."""
    logger.info(f"Backfilling TurboPuffer permissions for tenant {tenant_id}")

    async with (
        tenant_db_manager.acquire_pool(tenant_id) as db_pool,
        db_pool.acquire() as conn,
    ):
        # Get all documents with their permissions
        rows = await conn.fetch("""
                SELECT d.id, dp.permission_policy, dp.permission_allowed_tokens
                FROM documents d
                LEFT JOIN document_permissions dp ON d.id = dp.document_id
            """)

        if not rows:
            logger.info(f"No documents found for tenant {tenant_id}")
            return

        # Group by document for efficient updates
        doc_permissions = {}
        for row in rows:
            doc_id = row["id"]
            permission_policy = row["permission_policy"] or "tenant"  # Default fallback
            permission_allowed_tokens = row["permission_allowed_tokens"] or []

            doc_permissions[doc_id] = {
                "permission_policy": permission_policy,
                "permission_allowed_tokens": permission_allowed_tokens,
            }

        # Update TurboPuffer chunks in batches
        turbopuffer_client = get_turbopuffer_client()
        namespace = turbopuffer_client._get_namespace(tenant_id)

        # Process documents in batches
        batch_size = 1000  # Process 1000 documents at a time
        doc_items = list(doc_permissions.items())
        total_updated = 0

        for i in range(0, len(doc_items), batch_size):
            batch_docs = doc_items[i : i + batch_size]
            batch_doc_ids = [doc_id for doc_id, _ in batch_docs]

            logger.info(
                f"Processing document batch {i // batch_size + 1}/{(len(doc_items) + batch_size - 1) // batch_size}"
            )

            try:
                # Query chunks for this batch of documents
                chunks = await turbopuffer_client.query_chunks(
                    tenant_id=tenant_id,
                    query_vector=None,  # No vector search, just metadata
                    top_k=1000,  # Get all chunks for these documents
                    filters=("document_id", "In", batch_doc_ids),
                    include_attributes=["id", "document_id"],
                )

                if chunks:
                    # Build patch rows for this batch
                    patch_rows = []
                    for chunk in chunks:
                        doc_id = chunk.get("document_id")
                        if doc_id in doc_permissions:
                            permissions = doc_permissions[doc_id]
                            patch_rows.append(
                                {
                                    "id": chunk["id"],
                                    "permission_policy": permissions["permission_policy"],
                                    "permission_allowed_tokens": permissions[
                                        "permission_allowed_tokens"
                                    ],
                                }
                            )

                    if patch_rows:
                        # Execute batch patch update
                        await namespace.write(patch_rows=patch_rows)
                        total_updated += len(patch_rows)
                        logger.info(
                            f"Updated {len(patch_rows)} chunks in batch {i // batch_size + 1}"
                        )

            except Exception as e:
                logger.error(f"Failed to update batch {i // batch_size + 1}: {e}")
                # Continue with next batch rather than failing completely

        logger.info(
            f"Processed {len(doc_permissions)} documents and updated {total_updated} TurboPuffer chunks total"
        )


async def backfill_tenant_permissions(
    tenant_id: str, opensearch_only: bool = False, turbopuffer_only: bool = False
) -> None:
    """Backfill permissions for a single tenant."""
    logger.info(f"Starting permissions backfill for tenant: {tenant_id}")

    try:
        if not turbopuffer_only:
            await backfill_opensearch_permissions(tenant_id)

        if not opensearch_only:
            await backfill_turbopuffer_permissions(tenant_id)

        logger.info(f"Completed permissions backfill for tenant: {tenant_id}")
    except Exception as e:
        logger.error(f"Error backfilling permissions for tenant {tenant_id}: {e}")
        raise


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Backfill permissions to vector stores")
    parser.add_argument("--tenant-id", help="Specific tenant ID to backfill (optional)")
    parser.add_argument("--opensearch-only", action="store_true", help="Only backfill OpenSearch")
    parser.add_argument("--turbopuffer-only", action="store_true", help="Only backfill TurboPuffer")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        return

    if args.tenant_id:
        tenant_ids = [args.tenant_id]
    else:
        tenant_ids = await get_tenant_ids()

    logger.info(f"Backfilling permissions for {len(tenant_ids)} tenant(s)")

    try:
        for tenant_id in tenant_ids:
            await backfill_tenant_permissions(
                tenant_id=tenant_id,
                opensearch_only=args.opensearch_only,
                turbopuffer_only=args.turbopuffer_only,
            )

        logger.info("Permissions backfill completed for all tenants")
    finally:
        # Clean up any remaining client connections
        from src.clients.tenant_db import tenant_db_manager
        from src.clients.tenant_opensearch import _tenant_opensearch_manager

        await tenant_db_manager.cleanup()
        await _tenant_opensearch_manager.cleanup()

        # Also close any TurboPuffer HTTP sessions
        turbopuffer_client = get_turbopuffer_client()
        if hasattr(turbopuffer_client.client, "_client") and hasattr(
            turbopuffer_client.client._client, "aclose"
        ):
            await turbopuffer_client.client._client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
