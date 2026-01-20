"""
Base extractor class for ingest pipeline.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Sequence
from typing import Any, Protocol, get_args, overload

import asyncpg
from pydantic import BaseModel

from connectors.base.base_ingest_artifact import BaseIngestArtifact
from connectors.base.document_source import DocumentSource
from src.ingest.repositories import ArtifactRepository

logger = logging.getLogger(__name__)


# Type definition for the trigger_indexing callback used by extractors
class TriggerIndexingCallback(Protocol):
    @overload
    def __call__(
        self,
        entity_ids: list[str],
        source: DocumentSource,
        tenant_id: str,
        backfill_id: str | None,
        suppress_notification: bool = ...,
    ) -> Awaitable[None]: ...
    @overload
    def __call__(
        self, entity_ids: list[str], source: DocumentSource, tenant_id: str
    ) -> Awaitable[None]: ...
    def __call__(
        self,
        entity_ids: list[str],
        source: DocumentSource,
        tenant_id: str,
        backfill_id: str | None = ...,
        suppress_notification: bool = ...,
    ) -> Awaitable[None]: ...


class BaseExtractor[ConfigType: BaseModel](ABC):
    """Base class for all extractors that process ingest jobs."""

    source_name: str
    _config_type: type[ConfigType] | None = None

    def __init__(self):
        """Initialize the base extractor."""
        if not hasattr(self, "source_name") or self.source_name is None:
            raise TypeError(f"{self.__class__.__name__} must define 'source_name' class attribute")

        # Find the config type from the generic inheritance chain
        self._config_type = self._find_config_type()

    def _find_config_type(self) -> type[ConfigType] | None:
        """Find the ConfigType from the inheritance chain."""
        # Check all classes in the MRO (Method Resolution Order)
        for cls in self.__class__.__mro__:
            if hasattr(cls, "__orig_bases__"):
                for base in cls.__orig_bases__:
                    if hasattr(base, "__origin__"):
                        origin = base.__origin__
                        # Check if this is a BaseExtractor or its subclass
                        if origin is BaseExtractor or (
                            hasattr(origin, "__mro__") and BaseExtractor in origin.__mro__
                        ):
                            args = get_args(base)
                            if args:
                                return args[0]
        return None

    def parse_config(self, config: dict[str, Any]) -> ConfigType:
        """Parse and validate config using the extractor's config class.

        Args:
            config: Raw configuration dictionary or JSON string

        Returns:
            Validated config instance
        """
        if isinstance(config, str):  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
            config = json.loads(config)  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
        if self._config_type is None:
            raise ValueError("Config type not properly initialized")
        # `config` can be very large - only use this for debugging
        # logger.info(f"Job {self.source_name} config: {config}")
        return self._config_type(**config)

    @abstractmethod
    async def process_job(
        self,
        job_id: str,
        config: ConfigType,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process an ingest job.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to the extractor
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing for entity IDs (takes entity_ids, source, tenant_id, backfill_id)

        Raises:
            Exception: If processing fails
        """
        pass

    async def store_artifact(self, db_pool: asyncpg.Pool, artifact: BaseIngestArtifact) -> None:
        """Store a single artifact using the repository."""
        logger.debug(f"Storing {self.source_name} artifact {artifact.entity} {artifact.entity_id}")
        repo = ArtifactRepository(db_pool)
        await repo.upsert_artifact(artifact)

    async def store_artifacts_batch(
        self, db_pool: asyncpg.Pool, artifacts: Sequence[BaseIngestArtifact]
    ) -> None:
        """Store multiple artifacts using the repository."""
        if not artifacts or len(artifacts) == 0:
            return

        repo = ArtifactRepository(db_pool)
        await repo.upsert_artifacts_batch(artifacts)

        # Only log for large batches to reduce noise
        if len(artifacts) >= 500:
            logger.info(f"Stored {len(artifacts)} {self.source_name} artifacts")
        else:
            logger.debug(f"Stored {len(artifacts)} {self.source_name} artifacts")

    async def force_store_artifacts_batch(
        self, db_pool: asyncpg.Pool, artifacts: Sequence[BaseIngestArtifact]
    ) -> None:
        """Force store multiple artifacts, bypassing timestamp checks.

        This is useful when metadata must be updated regardless of source_updated_at,
        such as when member profile data changes but content timestamps don't reflect it.
        """
        if not artifacts or len(artifacts) == 0:
            return

        repo = ArtifactRepository(db_pool)
        await repo.force_upsert_artifacts_batch(artifacts)

        # Only log for large batches to reduce noise
        if len(artifacts) >= 500:
            logger.info(f"Force stored {len(artifacts)} {self.source_name} artifacts")
        else:
            logger.debug(f"Force stored {len(artifacts)} {self.source_name} artifacts")
