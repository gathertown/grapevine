"""Permissions service for document access control operations."""

import asyncpg

from src.utils.logging import get_logger

from .models import DocumentPermissions

logger = get_logger(__name__)


class PermissionsService:
    """Service for managing document permissions."""

    @staticmethod
    async def get_document_permissions(
        document_id: str,
        conn: asyncpg.Connection,
    ) -> DocumentPermissions | None:
        """Get permissions for a document.

        Args:
            document_id: Document ID to get permissions for
            conn: Database connection

        Returns:
            DocumentPermissions object or None if not found
        """
        try:
            row = await conn.fetchrow(
                """
                SELECT id, document_id, permission_policy, permission_allowed_tokens
                FROM document_permissions
                WHERE document_id = $1
                """,
                document_id,
            )

            if row is None:
                return None

            return DocumentPermissions(
                id=row["id"],
                document_id=row["document_id"],
                permission_policy=row["permission_policy"],
                permission_allowed_tokens=row["permission_allowed_tokens"],
            )
        except Exception as e:
            logger.error(f"Failed to get permissions for document {document_id}: {e}")
            raise

    @staticmethod
    async def batch_upsert_document_permissions(
        permissions_list: list[DocumentPermissions],
        conn: asyncpg.Connection,
    ) -> None:
        """Batch upsert multiple document permissions entries.

        Args:
            permissions_list: List of DocumentPermissions objects to upsert
            conn: Database connection
        """
        if not permissions_list:
            return

        try:
            permission_records = [
                (
                    perm.document_id,
                    perm.permission_policy,
                    perm.permission_allowed_tokens,
                )
                for perm in permissions_list
            ]

            await conn.executemany(
                """
                INSERT INTO document_permissions (document_id, permission_policy, permission_allowed_tokens)
                VALUES ($1, $2, $3)
                ON CONFLICT (document_id)
                DO UPDATE SET
                    permission_policy = EXCLUDED.permission_policy,
                    permission_allowed_tokens = EXCLUDED.permission_allowed_tokens,
                    updated_at = CURRENT_TIMESTAMP
                """,
                permission_records,
            )
            logger.debug(f"Batch upserted permissions for {len(permissions_list)} documents")
        except Exception as e:
            logger.error(
                f"Failed to batch upsert permissions for {len(permissions_list)} documents: {e}"
            )
            raise
