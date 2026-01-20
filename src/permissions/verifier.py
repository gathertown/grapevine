from __future__ import annotations

import asyncpg

from src.permissions.models import PermissionAudience
from src.permissions.utils import can_access_document, should_include_private_documents
from src.utils.logging import get_logger

logger = get_logger(__name__)


async def batch_verify_document_access(
    document_ids: list[str],
    permission_token: str | None,
    permission_audience: PermissionAudience | None,
    conn: asyncpg.Connection,
) -> set[str]:
    if not document_ids:
        return set()

    if not should_include_private_documents(permission_audience, permission_token):
        tenant_docs = await _get_tenant_policy_documents(document_ids, conn)
        return tenant_docs

    assert permission_token is not None, "permission_token must be set when including private docs"

    try:
        permissions_query = """
            SELECT document_id, permission_policy, permission_allowed_tokens
            FROM document_permissions
            WHERE document_id = ANY($1::varchar[])
        """
        permission_rows = await conn.fetch(permissions_query, document_ids)

        permissions_map = {
            row["document_id"]: {
                "permission_policy": row["permission_policy"],
                "permission_allowed_tokens": row["permission_allowed_tokens"],
            }
            for row in permission_rows
        }

        accessible_docs = set()
        documents_without_permissions = []

        for doc_id in document_ids:
            if doc_id not in permissions_map:
                documents_without_permissions.append(doc_id)
                continue

            permissions = permissions_map[doc_id]
            permission_policy = permissions["permission_policy"]
            permission_allowed_tokens = permissions["permission_allowed_tokens"]

            has_access = can_access_document(
                permission_policy=permission_policy,
                permission_allowed_tokens=permission_allowed_tokens,
                permission_token=permission_token,
            )

            if has_access:
                accessible_docs.add(doc_id)

        if documents_without_permissions:
            logger.warning(
                "Found documents without permission entries. Denying access by default.",
                documents=documents_without_permissions,
            )

        return accessible_docs

    except Exception as e:
        logger.error(f"Error during batch permission verification: {e}")
        return set()


async def _get_tenant_policy_documents(
    document_ids: list[str], conn: asyncpg.Connection
) -> set[str]:
    try:
        query = """
            SELECT document_id
            FROM document_permissions
            WHERE document_id = ANY($1::varchar[])
              AND permission_policy = 'tenant'
        """
        rows = await conn.fetch(query, document_ids)
        return {row["document_id"] for row in rows}
    except Exception as e:
        logger.error(f"Error querying tenant policy documents: {e}")
        return set()


def filter_results_by_permissions[T](
    results: list[T],
    accessible_document_ids: set[str],
    get_document_id_func,
) -> list[T]:
    if not accessible_document_ids:
        return []

    filtered_results = []
    for result in results:
        doc_id = get_document_id_func(result)
        if doc_id in accessible_document_ids:
            filtered_results.append(result)

    return filtered_results
