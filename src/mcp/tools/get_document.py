from fastmcp.server.context import Context

from src.mcp.mcp_instance import get_mcp
from src.mcp.middleware.org_context import acquire_connection_from_context
from src.mcp.tools.document_id import DocumentIdAnnotation
from src.mcp.tools.document_id_utils import get_candidate_document_ids, parse_metadata
from src.permissions.verifier import batch_verify_document_access
from src.utils.logging import get_logger

logger = get_logger(__name__)


@get_mcp().tool(
    description="""Return the full raw text of one document from your organization's internal context.

Use this tool when you already have a specific document ID obtained from search results and need to retrieve the complete text content of that document.

DO NOT use this tool to search for documents you aren't 100% sure exist! Use a search tool first instead to find a document ID.

This is useful for:
- Reading the full context after finding relevant documents through search
- Getting the complete content when search results only show snippets
- Accessing documents when you know their exact ID

READ THE `document_id` PARAM DESCRIPTION CAREFULLY! Be sure your `document_id` is formatted correctly for the `source` type.

Returns:
- Dict with document content: {document_id, content, found (optional), message (optional)}
- If document not found: {document_id, content: None, found: False, message}
"""
)
async def get_document(document_id: DocumentIdAnnotation, context: Context) -> dict:
    if not document_id:
        raise ValueError("document_id is required")

    # Get candidate document IDs (handles GITHUB_CODE slash fixing)
    candidates = get_candidate_document_ids(document_id)

    # Acquire tenant-scoped connection
    async with acquire_connection_from_context(context, readonly=True) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, content, metadata, source
            FROM documents
            WHERE id = ANY($1)
            ORDER BY array_position($1, id)
        """,
            candidates,
        )

        if not row:
            if len(candidates) == 1:
                logger.warning(f"Document not found with ID {candidates[0]}")
                return {
                    "document_id": candidates[0],
                    "content": None,
                    "found": False,
                    "message": f"Document not found with ID {candidates[0]}",
                }
            else:
                logger.warning(f"Document not found with any of these IDs: {candidates}")
                return {
                    "document_id": candidates[0],
                    "content": None,
                    "found": False,
                    "message": f"Document not found with any of these IDs: {candidates}",
                }

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

        content = row["content"]
        metadata = row["metadata"]

        # Parse metadata safely
        metadata = parse_metadata(metadata)

        return {
            "document_id": found_id,  # Return the ID that was actually found
            "content": content,
        }
