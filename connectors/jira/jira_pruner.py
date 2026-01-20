"""Jira issue pruner for handling complete deletion flow."""

import logging

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_jira_doc_id

logger = logging.getLogger(__name__)


class JiraPruner(BasePruner):
    """Singleton class for handling Jira issue deletions across all data stores."""

    async def delete_issue(self, issue_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete a Jira issue from all data stores using the standardized template method.

        Args:
            issue_id: The Jira internal issue ID (numeric string format, e.g., "10218")
            tenant_id: The tenant ID
            db_pool: Database connection pool (required)

        Returns:
            True if deletion was successful, False otherwise
        """
        if not issue_id:
            logger.warning("No issue_id provided for Jira issue deletion")
            return False

        logger.info(f"Deleting Jira issue: {issue_id}")

        # Use the template method from BasePruner
        # Pass the jira document ID resolver directly
        return await self.delete_entity(
            entity_id=issue_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_jira_doc_id,
            entity_type="jira_issue",
        )


# Singleton instance
jira_pruner = JiraPruner()
