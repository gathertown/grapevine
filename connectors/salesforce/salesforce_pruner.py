"""Salesforce object pruner for handling complete deletion flow."""

import logging
from functools import partial

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import get_salesforce_doc_id
from connectors.salesforce.salesforce_artifacts import (
    SUPPORTED_SALESFORCE_OBJECTS,
    get_salesforce_entity_type,
)

logger = logging.getLogger(__name__)


class SalesforcePruner(BasePruner):
    """Singleton class for handling Salesforce object deletions across all data stores."""

    async def delete_record(
        self,
        record_id: str,
        object_type: SUPPORTED_SALESFORCE_OBJECTS,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> bool:
        """
        Delete a Salesforce record from all data stores using the standardized template method.

        Args:
            record_id: The Salesforce record ID
            object_type: The Salesforce object type (Account, Contact, etc.)
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not record_id:
            logger.warning("No record_id provided for Salesforce record deletion")
            return False

        logger.info(f"Deleting Salesforce {object_type}: {record_id}")

        # Get the entity type for this object type
        entity_type = get_salesforce_entity_type(object_type)

        # Create a partial function with the object_type bound
        document_id_resolver = partial(get_salesforce_doc_id, object_type)

        # Use the template method from BasePruner
        return await self.delete_entity(
            entity_id=record_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=document_id_resolver,
            entity_type=entity_type.value,
        )


# Singleton instance
salesforce_pruner = SalesforcePruner()
