"""GitHub file pruner for handling complete deletion flow."""

import logging

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_github_file_doc_id

logger = logging.getLogger(__name__)


class GitHubPruner(BasePruner):
    """Singleton class for handling GitHub file deletions across all data stores."""

    async def delete_file(
        self,
        file_path: str,
        repo_name: str,
        organization: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> bool:
        """
        Delete a GitHub file from all data stores using the standardized template method.

        Args:
            file_path: Path to the file in the repository
            repo_name: Name of the repository
            organization: Organization/owner of the repository
            tenant_id: The tenant ID
            db_pool: Database connection pool (required)

        Returns:
            True if deletion was successful, False otherwise
        """
        if not file_path or not repo_name or not organization:
            logger.warning(
                "Incomplete file deletion data: missing file_path, repo_name, or organization"
            )
            return False

        # Construct the entity_id - for GitHub files, this is org/repo/file_path
        entity_id = f"{organization}/{repo_name}/{file_path}"

        logger.info(f"Deleting GitHub file: {file_path} in {organization}/{repo_name}")

        # Use the template method from BasePruner
        # For GitHub files, document_id is "github_file_{entity_id}"
        return await self.delete_entity(
            entity_id=entity_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_github_file_doc_id,
            entity_type="github_file",
        )


# Singleton instance
github_pruner = GitHubPruner()
