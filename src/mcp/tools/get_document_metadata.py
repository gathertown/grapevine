from fastmcp.server.context import Context

from src.mcp.mcp_instance import get_mcp
from src.mcp.middleware.org_context import acquire_connection_from_context
from src.mcp.tools.document_id import DocumentIdAnnotation
from src.mcp.tools.document_id_utils import get_candidate_document_ids, parse_metadata
from src.permissions.verifier import batch_verify_document_access
from src.utils.logging import get_logger

logger = get_logger(__name__)


@get_mcp().tool(
    description="""Retrieve metadata for one document from your organization's internal context without downloading its text content.

Use this tool when you need to inspect document information without the overhead of downloading the full content. This is useful for:
- Checking document size (chunk count) before fetching full content
- Viewing document timestamps and source information
- Inspecting document metadata
- Determining if a document is worth fetching based on its properties

This is faster than get_document since it only retrieves metadata from the database.

READ THE `document_id` PARAM DESCRIPTION CAREFULLY! Be sure your `document_id` is formatted correctly for the `source` type.

Returns:
- Dict with metadata: {document_id, source, metadata, chunk_count, source_created_at, created_at, updated_at}
- If document not found: {document_id, found: False, message}
"""
)
async def get_document_metadata(document_id: DocumentIdAnnotation, context: Context) -> dict:
    if not document_id:
        raise ValueError("document_id is required")

    candidates = get_candidate_document_ids(document_id)

    async with acquire_connection_from_context(context, readonly=True) as conn:
        # Single query with ANY() for array support
        rows = await conn.fetch(
            """
            SELECT
                d.id,
                d.source,
                d.metadata as doc_metadata,
                d.source_created_at,
                d.created_at as doc_created,
                d.updated_at as doc_updated
            FROM documents d
            WHERE d.id = ANY($1)
            ORDER BY array_position($1, d.id)
        """,
            candidates,
        )

        if not rows:
            if len(candidates) == 1:
                logger.warning(f"Document not found with ID {candidates[0]}")
                return {
                    "document_id": candidates[0],
                    "found": False,
                    "message": f"Document not found with ID {candidates[0]}",
                }
            else:
                logger.warning(f"Document not found with any of these IDs: {candidates}")
                return {
                    "document_id": candidates[0],
                    "found": False,
                    "message": f"Document not found with any of these IDs: {candidates}",
                }

        # Use first result (original ID priority due to ORDER BY)
        row = rows[0]
        found_id = row["id"]

        # Verify document permissions
        permission_principal_token = context.get_state("permission_principal_token")
        permission_audience = context.get_state("permission_audience")

        accessible_document_ids = await batch_verify_document_access(
            document_ids=[found_id],
            permission_token=permission_principal_token,
            permission_audience=permission_audience,
            conn=conn,
        )

        if found_id not in accessible_document_ids:
            msg = f"Access denied: You do not have permission to view document {found_id}"
            raise Exception(msg)

        doc_metadata = row["doc_metadata"]

        # Parse metadata safely
        doc_metadata = parse_metadata(doc_metadata)

        return {
            "document_id": row["id"],  # Return the ID that was actually found
            "source": row["source"],
            "metadata": doc_metadata,
            "source_created_at": row["source_created_at"].isoformat()
            if row["source_created_at"]
            else None,
            "created_at": row["doc_created"].isoformat() if row["doc_created"] else None,
            "updated_at": row["doc_updated"].isoformat() if row["doc_updated"] else None,
        }
