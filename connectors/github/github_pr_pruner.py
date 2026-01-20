"""GitHub PR pruner for handling complete deletion flow."""

import logging

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_github_pr_doc_id

logger = logging.getLogger(__name__)


class GitHubPRPruner(BasePruner):
    """Singleton class for handling GitHub PR deletions across all data stores."""

    async def delete_pr(
        self,
        repo_id: str,
        pr_number: int,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> bool:
        """
        Delete a GitHub PR from all data stores using the standardized template method.

        Args:
            repo_id: The GitHub repository ID (numeric string)
            pr_number: The PR number
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not repo_id or pr_number <= 0:
            logger.warning(f"Invalid PR deletion data: repo_id={repo_id}, pr_number={pr_number}")
            return False

        logger.info(f"Deleting GitHub PR: #{pr_number} in repo {repo_id}")

        # Use the template method from BasePruner
        # For GitHub PRs, entity_id is "{repo_id}_pr_{pr_number}" and document_id uses the same format
        return await self.delete_entity(
            entity_id=f"{repo_id}_pr_{pr_number}",
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=lambda entity_id: get_github_pr_doc_id(repo_id, pr_number),
            entity_type="github_pr",
        )


# Singleton instance
github_pr_pruner = GitHubPRPruner()
