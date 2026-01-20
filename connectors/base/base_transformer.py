"""Base transformer class for converting artifacts to documents."""

import logging
from abc import ABC, abstractmethod
from typing import Any

import asyncpg

from connectors.base import BaseDocument
from connectors.base.document_source import DocumentSource

logger = logging.getLogger(__name__)


class BaseTransformer[T: BaseDocument[Any, Any]](ABC):
    """Base class for transforming ingest artifacts into documents."""

    def __init__(self, source_name: DocumentSource):
        """Initialize the transformer.

        Args:
            source_name: Name of the source (DocumentSource enum)
        """
        self.source_name = source_name

    @abstractmethod
    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[T]:
        """Transform specific artifacts into documents.

        This method transforms a specified list of entity artifacts into document instances
        ready for indexing. The transformer should query the database for artifacts
        matching the provided entity_ids and convert them into the appropriate document format.

        Args:
            entity_ids: Required list of specific entity IDs to transform. Each entity_id
                       corresponds to an artifact's entity_id field in the database.
            readonly_db_pool: Database connection pool for querying artifacts

        Returns:
            List of document instances ready for indexing. The number of returned documents
            may be less than the number of entity_ids if some entities cannot be transformed
            or are not found.

        Raises:
            Exception: If database queries fail or transformation encounters critical errors
        """
        pass
