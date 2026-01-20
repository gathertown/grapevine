"""
Calculate referrers for documents by finding all docs that reference them.

This module provides functionality to efficiently find all documents that reference
a given document by its reference ID, using the database's GIN index for optimal performance.
"""

import logging
import math

import asyncpg

logger = logging.getLogger(__name__)


async def calculate_referrers(
    reference_id: str,
    readonly_db_pool: asyncpg.Pool,
) -> dict[str, int]:
    """Calculate referrers for a document by finding all docs that reference it.

    Args:
        reference_id: The reference ID of the document to find referrers for
        readonly_db_pool: Database pool for queries

    Returns:
        Dict mapping referring document reference_ids to reference counts
    """
    async with readonly_db_pool.acquire() as conn:
        # Use GIN index to find all documents that reference our document
        # Require reference_id to be non-null to skip docs that haven't been migrated yet
        # or are broken. We can't use a doc without its reference_id.
        referring_docs = await conn.fetch(
            """
            SELECT reference_id, referenced_docs, metadata
            FROM documents
            WHERE reference_id IS NOT NULL AND referenced_docs ? $1
            """,
            reference_id,
        )

        referrers: dict[str, int] = {}

        for row in referring_docs:
            # This should always be a dict given our type codec in TenantDBManager
            referenced_docs = (
                row["referenced_docs"] if isinstance(row["referenced_docs"], dict) else {}
            )

            if reference_id in referenced_docs:
                reference_count = referenced_docs[reference_id]
                referrers[row["reference_id"]] = reference_count
            else:
                logger.error(
                    f"Document returned from referrers query but does not have {reference_id} in its referenced_docs"
                )

        logger.info(f"Found {len(referrers)} referrers for reference_id {reference_id}")
        return referrers


def calculate_referrer_score(referrers: dict[str, int]) -> float:
    """Calculate referrer score by summing over log_10(x+9) for each positive reference count.

    Args:
        referrers: Dict mapping referring document reference_ids to reference counts
    """
    return sum(math.log10(count + 9) if count > 0 else 0 for count in referrers.values())
