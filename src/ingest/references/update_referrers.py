"""
Update referrer relationships for documents.

This module provides functionality to update bidirectional referrer relationships
when documents' referenced_docs change, ensuring referrer counts and scores
are kept in sync across all affected documents.
"""

import json
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

import asyncpg

from src.clients.tenant_opensearch import TenantScopedOpenSearchClient
from src.ingest.references.calculate_referrers import calculate_referrer_score

logger = logging.getLogger(__name__)


@dataclass
class ReferrerUpdate:
    """Structure for a referrer update operation."""

    reference_id: str
    referrers: dict[str, int]
    document_id: str

    @property
    def referrer_score(self) -> float:
        """Calculate referrer score from referrers."""
        return calculate_referrer_score(self.referrers)


async def fetch_existing_referenced_docs(
    doc_id: str, readonly_db_pool: asyncpg.Pool
) -> dict[str, int]:
    """Fetch the `referenced_docs` field from an existing document in the database."""
    try:
        async with readonly_db_pool.acquire() as conn:
            result = await conn.fetchrow(
                "SELECT referenced_docs FROM documents WHERE id = $1", doc_id
            )
            if result and result["referenced_docs"]:
                return (
                    result["referenced_docs"] if isinstance(result["referenced_docs"], dict) else {}
                )
            return {}
    except Exception as e:
        logger.error(f"Failed to fetch existing referenced_docs for {doc_id}: {e}")
        return {}


def compute_referenced_docs_diff(
    old_refs: dict[str, int], new_refs: dict[str, int]
) -> dict[Literal["added_or_changed", "removed"], dict[str, int]]:
    """Compute the difference between old and new referenced_docs.

    Args:
        old_refs: Previous referenced_docs mapping
        new_refs: New referenced_docs mapping

    Returns:
        Dict with keys 'added_or_changed', 'removed' containing reference_id -> count mappings
    """
    added_or_changed = {}
    removed = {}

    # Find added and changed references
    for ref_id, new_count in new_refs.items():
        if ref_id not in old_refs or old_refs[ref_id] != new_count:
            added_or_changed[ref_id] = new_count

    # Find removed references
    for ref_id, old_count in old_refs.items():
        if ref_id not in new_refs:
            removed[ref_id] = old_count

    return {"added_or_changed": added_or_changed, "removed": removed}


async def _fetch_current_referrers(
    affected_ref_ids: set[str], conn: asyncpg.Connection
) -> dict[str, tuple[dict[str, int], str]]:
    """Fetch current referrers and document_id for a set of reference_ids."""
    if not affected_ref_ids:
        return {}

    placeholders = ",".join(f"${i + 1}" for i in range(len(affected_ref_ids)))
    query = f"""
        SELECT reference_id, referrers, id
        FROM documents
        WHERE reference_id IN ({placeholders})
    """

    rows = await conn.fetch(query, *list(affected_ref_ids))

    current_referrers_map: dict[str, tuple[dict[str, int], str]] = {}
    for row in rows:
        current_referrers = row["referrers"] if isinstance(row["referrers"], dict) else {}
        current_referrers_map[row["reference_id"]] = (current_referrers, row["id"])

    return current_referrers_map


async def prepare_referrer_updates(
    readonly_db_pool: asyncpg.Pool,
    reference_id: str,
    old_referenced_docs: dict[str, int],
    new_referenced_docs: dict[str, int],
) -> list[ReferrerUpdate]:
    """Prepare referrer updates for all docs affected by `new_doc`'s `referenced_docs` changes.

    Args:
        new_doc: The new document being updated
        readonly_db_pool: Database pool for queries
    """
    # Fetch existing referenced_docs and compute diff against `new_doc.referenced_docs`
    referenced_docs_diff = compute_referenced_docs_diff(old_referenced_docs, new_referenced_docs)

    updates: list[ReferrerUpdate] = []

    # Collect all affected document reference_ids
    affected_ref_ids: set[str] = set()
    for category in referenced_docs_diff.values():
        affected_ref_ids.update(category.keys())

    if not affected_ref_ids:
        return updates

    # Fetch current referrers for all affected documents
    async with readonly_db_pool.acquire() as conn:
        current_referrers_map = await _fetch_current_referrers(affected_ref_ids, conn)

    # Process each affected document that exists in DB
    for ref_id in current_referrers_map:
        current_referrers, document_id = current_referrers_map[ref_id]
        current_referrers = current_referrers.copy()

        # Apply changes based on the diff
        if ref_id in referenced_docs_diff["added_or_changed"]:
            current_referrers[reference_id] = referenced_docs_diff["added_or_changed"][ref_id]

        elif ref_id in referenced_docs_diff["removed"]:
            current_referrers.pop(reference_id, None)

        updates.append(
            ReferrerUpdate(
                reference_id=ref_id, referrers=current_referrers, document_id=document_id
            )
        )

    if len(updates) > 0:
        logger.info(
            f"Prepared {len(updates)} referrer updates for document {reference_id}. "
            f"Updates: {[(update.reference_id, update.referrer_score) for update in updates]}"
        )
    return updates


async def prepare_referrer_updates_for_deletion(
    reference_id: str,
    referenced_docs: dict[str, int],
    conn: asyncpg.Connection,
) -> list[ReferrerUpdate]:
    """Prepare referrer updates for documents affected by the deletion of a document.

    When a document is deleted, all documents it referenced need to have it
    removed from their `referrers` fields.

    Args:
        reference_id: The reference_id of the document being deleted
        referenced_docs: The referenced_docs field of the document being deleted
        conn: Database connection for queries
    """
    if not referenced_docs:
        return []

    updates: list[ReferrerUpdate] = []

    # All documents referenced by the deleted document need to be updated
    affected_ref_ids = set(referenced_docs.keys())

    # Fetch current referrers for all affected documents
    current_referrers_map = await _fetch_current_referrers(affected_ref_ids, conn)

    # Process each affected document that exists in DB by removing the deleted document from their `referrers`
    for ref_id in current_referrers_map:
        current_referrers, document_id = current_referrers_map[ref_id]
        current_referrers = current_referrers.copy()

        # Remove the deleted document from referrers
        current_referrers.pop(reference_id, None)
        updates.append(
            ReferrerUpdate(
                reference_id=ref_id, referrers=current_referrers, document_id=document_id
            )
        )

    if len(updates) > 0:
        logger.info(
            f"Prepared {len(updates)} referrer updates for document {reference_id} deletion. "
            f"Updates: {[(update.reference_id, update.referrer_score) for update in updates]}"
        )

    return updates


async def apply_referrer_updates_to_db(
    referrer_updates: list[ReferrerUpdate], conn: asyncpg.Connection
) -> None:
    """Apply referrer updates to affected documents in a single batch query."""
    if not referrer_updates:
        return

    # Sort referrer updates by reference_id for consistent lock ordering to reduce deadlock risk
    sorted_updates = sorted(referrer_updates, key=lambda u: u.reference_id)

    # Build VALUES clause for batch update
    values_clause = []
    update_params: list[str] = []
    param_counter = 1

    for update in sorted_updates:
        values_clause.append(f"(${param_counter}, ${param_counter + 1}, ${param_counter + 2})")
        update_params.extend(
            [
                update.reference_id,
                json.dumps(update.referrers),
                str(update.referrer_score),
            ]
        )
        param_counter += 3

    await conn.execute(
        f"""
        UPDATE documents
        SET referrers = updates.referrers::jsonb,
            referrer_score = updates.referrer_score::real
        FROM (VALUES {",".join(values_clause)}) AS updates(reference_id, referrers, referrer_score)
        WHERE documents.reference_id = updates.reference_id
        """,
        *update_params,
    )


async def apply_referrer_updates_to_opensearch(
    referrer_updates: list[ReferrerUpdate],
    tenant_id: str,
    opensearch_client: TenantScopedOpenSearchClient,
) -> None:
    """Apply referrer score updates to OpenSearch documents using partial updates."""
    if not referrer_updates:
        return

    index_name = f"tenant-{tenant_id}"

    # Use OpenSearch's bulk API for efficient updates
    updates: list[dict[str, Any]] = []
    for update in referrer_updates:
        updates.extend(
            [
                # Action metadata
                {"update": {"_index": index_name, "_id": update.document_id}},
                # Partial document update
                {"doc": {"referrer_score": update.referrer_score}},
            ]
        )

    response = await opensearch_client.bulk(index=index_name, body=updates, refresh=False)

    if response.get("errors"):
        # Log individual failures, then fail the entire operation
        # TODO remove these counts, this is likely a version_conflict_engine_exception, count occurrences per doc_id to double check we aren't double updating in the same batch
        doc_id_counts = Counter(u.document_id for u in referrer_updates)
        for item in response.get("items", []):
            if "update" in item and item["update"].get("error"):
                error = item["update"]["error"]
                doc_id = item["update"]["_id"]

                logger.error(
                    f"Failed to update referrer_score in OpenSearch for document {doc_id} (count: {doc_id_counts[doc_id]}): {error}"
                )
        raise Exception("Failed to update referrer_scores in OpenSearch")
    else:
        logger.info(
            f"✅ Updated referrer_scores for {len(referrer_updates)} doc(s) in OpenSearch from referrer_updates"
        )
