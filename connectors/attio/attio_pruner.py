"""Attio entity pruner for handling complete deletion flow."""

import logging
from collections.abc import Callable

import asyncpg

from connectors.base import BasePruner
from connectors.base.doc_ids import (
    get_attio_company_doc_id,
    get_attio_deal_doc_id,
    get_attio_person_doc_id,
)

logger = logging.getLogger(__name__)


class AttioPruner(BasePruner):
    """Singleton class for handling Attio entity deletions across all data stores."""

    async def delete_company(self, record_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete an Attio company record from all data stores.

        Args:
            record_id: The Attio company record ID
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        return await self._delete_record(
            record_id=record_id,
            object_type="company",
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_attio_company_doc_id,
        )

    async def delete_person(self, record_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete an Attio person record from all data stores.

        Args:
            record_id: The Attio person record ID
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        return await self._delete_record(
            record_id=record_id,
            object_type="person",
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_attio_person_doc_id,
        )

    async def delete_deal(self, record_id: str, tenant_id: str, db_pool: asyncpg.Pool) -> bool:
        """
        Delete an Attio deal record from all data stores.

        Args:
            record_id: The Attio deal record ID
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        return await self._delete_record(
            record_id=record_id,
            object_type="deal",
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=get_attio_deal_doc_id,
        )

    async def _delete_record(
        self,
        record_id: str,
        object_type: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        document_id_resolver: Callable[[str], str],
    ) -> bool:
        """
        Delete an Attio record from all data stores using the standardized template method.

        This handles:
        - Artifact deletion from PostgreSQL
        - Document and chunks removal from PostgreSQL
        - OpenSearch index cleanup
        - Turbopuffer cleanup

        Args:
            record_id: The Attio record ID
            object_type: The type of Attio object ("company", "person", or "deal")
            tenant_id: The tenant ID
            db_pool: Database connection pool
            document_id_resolver: Function to convert record_id to document_id

        Returns:
            True if deletion was successful, False otherwise
        """
        if not record_id:
            logger.warning(f"No record_id provided for Attio {object_type} deletion")
            return False

        logger.info(f"Deleting Attio {object_type}: {record_id}")

        # Use the template method from BasePruner
        return await self.delete_entity(
            entity_id=record_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
            document_id_resolver=document_id_resolver,
            entity_type=f"attio_{object_type}",
        )


# Singleton instance
attio_pruner = AttioPruner()
