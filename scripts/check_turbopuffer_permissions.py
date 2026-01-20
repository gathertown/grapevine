#!/usr/bin/env python3
"""
Check TurboPuffer chunks to verify permissions have been applied.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncpg

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


async def check_tenant_permissions(tenant_id: str, sample_size: int = 10) -> None:
    """Check permissions for a sample of chunks from a tenant."""
    logger.info(f"Checking permissions for tenant: {tenant_id}")

    turbopuffer_client = get_turbopuffer_client()

    try:
        # Get a sample of chunks
        chunks = await turbopuffer_client.query_chunks(
            tenant_id=tenant_id,
            query_vector=None,  # No vector search, just metadata
            top_k=sample_size,
            include_attributes=[
                "id",
                "document_id",
                "permission_policy",
                "permission_allowed_tokens",
                "metadata",
            ],
        )

        if not chunks:
            logger.info(f"No chunks found for tenant {tenant_id}")
            return

        logger.info(f"Found {len(chunks)} chunks for tenant {tenant_id}")

        # Check permissions on chunks and show raw JSON
        import json

        has_permissions = 0
        missing_permissions = 0

        for i, chunk in enumerate(chunks):
            chunk_id = chunk.get("id", "unknown")
            doc_id = chunk.get("document_id", "unknown")
            permission_policy = chunk.get("permission_policy")

            logger.info(f"📄 Chunk {i + 1}: {chunk_id[:20]}... (doc: {doc_id[:20]}...)")
            logger.info(f"Raw JSON: {json.dumps(chunk, indent=2, default=str)}")
            logger.info("---")

            if permission_policy is not None:
                has_permissions += 1
            else:
                missing_permissions += 1

        logger.info(
            f"Summary for {tenant_id}: {has_permissions} chunks with permissions, {missing_permissions} without"
        )

    except Exception as e:
        logger.error(f"Failed to check permissions for tenant {tenant_id}: {e}")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Check TurboPuffer permissions")
    parser.add_argument("--tenant-id", help="Specific tenant ID to check (optional)")
    parser.add_argument(
        "--sample-size", type=int, default=10, help="Number of chunks to sample per tenant"
    )

    args = parser.parse_args()

    if args.tenant_id:
        tenant_ids = [args.tenant_id]
    else:
        tenant_ids = await get_tenant_ids()

    logger.info(f"Checking permissions for {len(tenant_ids)} tenant(s)")

    try:
        for tenant_id in tenant_ids:
            await check_tenant_permissions(tenant_id, args.sample_size)
            logger.info("---")

        logger.info("Permission check completed for all tenants")
    finally:
        # Clean up any remaining client connections
        turbopuffer_client = get_turbopuffer_client()
        if hasattr(turbopuffer_client.client, "_client") and hasattr(
            turbopuffer_client.client._client, "aclose"
        ):
            await turbopuffer_client.client._client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
