"""Google Drive file pruner for handling complete deletion flow."""

import logging

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_google_drive_doc_id

logger = logging.getLogger(__name__)


class GoogleDrivePruner(BasePruner):
    """Singleton class for handling Google Drive file deletions across all data stores."""

    async def delete_file(
        self,
        file_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> bool:
        """
        Delete a Google Drive file from all data stores using the standardized template method.

        Args:
            file_id: Google Drive file ID
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not file_id:
            logger.warning("No file_id provided for Google Drive deletion")
            return False

        logger.info(f"Deleting Google Drive file: {file_id}")

        # Use the template method from BasePruner
        # Pass the google drive document ID resolver directly
        return await self.delete_entity(
            entity_id=file_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_google_drive_doc_id,
            entity_type="google_drive_file",
        )


google_drive_pruner = GoogleDrivePruner()
