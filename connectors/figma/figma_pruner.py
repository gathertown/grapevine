"""Figma entity pruner for handling complete deletion flow."""

import logging

import asyncpg

from connectors.base import BasePruner
from connectors.figma.figma_models import get_figma_entity_id

logger = logging.getLogger(__name__)


class FigmaPruner(BasePruner):
    """Singleton class for handling Figma entity deletions across all data stores."""

    async def delete_file(self, file_key: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete a Figma file from all data stores.

        Args:
            file_key: The Figma file key
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not file_key:
            logger.warning("No file_key provided for Figma file deletion")
            return False

        logger.info(f"Deleting Figma file: {file_key}")

        # Use the template method from BasePruner
        # Entity ID must match the format used by FigmaFileArtifact
        # For Figma, entity_id and document_id use the same format, so use identity resolver
        entity_id = get_figma_entity_id("file", file_key)
        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=lambda _: entity_id,
            entity_type="figma_file",
        )

    async def delete_comment(self, comment_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete a Figma comment from all data stores.

        Args:
            comment_id: The Figma comment ID
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not comment_id:
            logger.warning("No comment_id provided for Figma comment deletion")
            return False

        logger.info(f"Deleting Figma comment: {comment_id}")

        # Use the template method from BasePruner
        # Entity ID must match the format used by FigmaCommentArtifact
        # For Figma, entity_id and document_id use the same format, so use identity resolver
        entity_id = get_figma_entity_id("comment", comment_id)
        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=lambda _: entity_id,
            entity_type="figma_comment",
        )


# Singleton instance
figma_pruner = FigmaPruner()
