"""HubSpot entity pruner for handling complete deletion flow."""

import logging
from functools import partial

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_hubspot_doc_id

logger = logging.getLogger(__name__)


class HubspotPruner(BasePruner):
    """Singleton class for handling HubSpot entity deletions across all data stores."""

    async def delete_record(
        self, record_id: str, object_type: str, tenant_id: str, db_pool: asyncpg.Pool
    ) -> bool:
        """
        Delete a HubSpot record from all data stores using the standardized template method.

        This handles:
        - Artifact deletion from PostgreSQL
        - Document and chunks removal from PostgreSQL
        - OpenSearch index cleanup
        - Turbopuffer cleanup
        - Referrer updates

        Args:
            record_id: The HubSpot record ID
            object_type: The type of HubSpot object ("company" or "deal")
            tenant_id: The tenant ID
            db_pool: Database connection pool (required)

        Returns:
            True if deletion was successful, False otherwise
        """
        if not record_id:
            logger.warning(f"No record_id provided for HubSpot {object_type} deletion")
            return False

        logger.info(f"Deleting HubSpot {object_type}: {record_id}")

        # Create document ID resolver for this object type
        document_id_resolver = partial(get_hubspot_doc_id, object_type)

        # Use the template method from BasePruner
        return await self.delete_entity(
            entity_id=record_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=document_id_resolver,
            entity_type=f"hubspot_{object_type}",
        )


# Singleton instance
hubspot_pruner = HubspotPruner()
