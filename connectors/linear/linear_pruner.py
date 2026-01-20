"""Linear issue pruner for handling complete deletion flow."""

import logging

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_linear_doc_id

logger = logging.getLogger(__name__)


class LinearPruner(BasePruner):
    """Singleton class for handling Linear issue deletions across all data stores."""

    async def delete_issue(self, issue_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete a Linear issue from all data stores using the standardized template method.

        Args:
            issue_id: The Linear issue ID
            tenant_id: The tenant ID
            db_pool: Database connection pool (required)

        Returns:
            True if deletion was successful, False otherwise
        """
        if not issue_id:
            logger.warning("No issue_id provided for Linear issue deletion")
            return False

        logger.info(f"Deleting Linear issue: {issue_id}")

        # Use the template method from BasePruner
        # Pass the linear document ID resolver directly
        return await self.delete_entity(
            entity_id=issue_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_linear_doc_id,
            entity_type="linear_issue",
        )


# Singleton instance
linear_pruner = LinearPruner()
