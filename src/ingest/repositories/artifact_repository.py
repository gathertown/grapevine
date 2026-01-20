"""Repository for managing ingest artifacts."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, TypeVar

import asyncpg

from connectors.base.base_ingest_artifact import BaseIngestArtifact
from src.ingest.services.exclusion_rules import ExclusionRulesService

T = TypeVar("T", bound=BaseIngestArtifact)

logger = logging.getLogger(__name__)


class ArtifactCache(Protocol):
    async def get_artifacts_by_entity_ids[T: BaseIngestArtifact](
        self, artifact_class: type[T], entity_ids: list[str], apply_exclusions: bool = True
    ) -> list[T]: ...


class MemoryArtifactCache(ArtifactCache):
    cache: dict[str, dict[str, BaseIngestArtifact]]

    def __init__(self) -> None:
        self.cache = {}

    def add_batch(self, artifacts: Sequence[BaseIngestArtifact]) -> None:
        for artifact in artifacts:
            class_cache = self.cache.setdefault(artifact.entity.value, {})
            class_cache[artifact.entity_id] = artifact

    async def get_artifacts_by_entity_ids[T: BaseIngestArtifact](
        self, artifact_class: type[T], entity_ids: list[str], apply_exclusions: bool = True
    ) -> list[T]:
        entity_field = artifact_class.model_fields.get("entity")
        if not entity_field or not entity_field.default:
            raise ValueError(
                f"Artifact class {artifact_class.__name__} does not have a default entity field"
            )

        class_cache = self.cache.setdefault(entity_field.default, {})

        classless_artifacts = [
            class_cache[entity_id] for entity_id in entity_ids if entity_id in class_cache
        ]
        return [
            artifact for artifact in classless_artifacts if isinstance(artifact, artifact_class)
        ]


class ArtifactRepository(ArtifactCache):
    """Repository for managing ingest artifacts with type-safe methods."""

    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool

    async def upsert_artifact(self, artifact: BaseIngestArtifact) -> None:
        """Insert or update an artifact (updates only if newer via `source_updated_at`).

        Args:
            artifact: The artifact to upsert
        """
        artifact_data = artifact.model_dump()

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ingest_artifact (id, entity, entity_id, ingest_job_id, metadata, content, source_updated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
                ON CONFLICT (entity, entity_id) DO UPDATE SET
                    id = EXCLUDED.id,
                    ingest_job_id = EXCLUDED.ingest_job_id,
                    metadata = EXCLUDED.metadata,
                    content = EXCLUDED.content,
                    source_updated_at = EXCLUDED.source_updated_at
                WHERE ingest_artifact.source_updated_at < EXCLUDED.source_updated_at
                """,
                str(artifact.id),
                artifact.entity,
                artifact.entity_id,
                str(artifact.ingest_job_id),
                json.dumps(artifact_data["metadata"]),
                json.dumps(artifact_data["content"]),
                artifact.source_updated_at,
            )

    async def force_upsert_artifact(
        self, artifact: BaseIngestArtifact, backfill_id: str | None = None
    ) -> None:
        """Force insert or update an artifact, bypassing timestamp checks.

        TODO: Consolidate this method with upsert_artifact. Pass an additional flag
        to upsert_artifact called force_update (default False). When True, the WHERE
        clause checking source_updated_at is omitted.

        Args:
            artifact: The artifact to force upsert
            backfill_id: Optional backfill ID to track which sync last saw this artifact
        """
        artifact_data = artifact.model_dump()

        async with self.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ingest_artifact (id, entity, entity_id, ingest_job_id, metadata, content, source_updated_at, last_seen_backfill_id)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
                ON CONFLICT (entity, entity_id) DO UPDATE SET
                    id = EXCLUDED.id,
                    ingest_job_id = EXCLUDED.ingest_job_id,
                    metadata = EXCLUDED.metadata,
                    content = EXCLUDED.content,
                    source_updated_at = EXCLUDED.source_updated_at,
                    last_seen_backfill_id = EXCLUDED.last_seen_backfill_id
                """,
                str(artifact.id),
                artifact.entity,
                artifact.entity_id,
                str(artifact.ingest_job_id),
                json.dumps(artifact_data["metadata"]),
                json.dumps(artifact_data["content"]),
                artifact.source_updated_at,
                backfill_id,
            )

    async def upsert_artifacts_batch(self, artifacts: Sequence[BaseIngestArtifact]) -> None:
        """Batch inserts or updates artifacts efficiently (updates only if newer via `source_updated_at`).

        Args:
            artifacts: List of artifacts to upsert
        """
        if not artifacts:
            return

        upsert_rows = []
        for artifact in artifacts:
            artifact_data = artifact.model_dump()
            upsert_rows.append(
                (
                    str(artifact.id),
                    artifact.entity,
                    artifact.entity_id,
                    str(artifact.ingest_job_id),
                    json.dumps(artifact_data["metadata"]),
                    json.dumps(artifact_data["content"]),
                    artifact.source_updated_at,
                )
            )

        async with self.db_pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO ingest_artifact (id, entity, entity_id, ingest_job_id, metadata, content, source_updated_at)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
                ON CONFLICT (entity, entity_id) DO UPDATE SET
                    id = EXCLUDED.id,
                    ingest_job_id = EXCLUDED.ingest_job_id,
                    metadata = EXCLUDED.metadata,
                    content = EXCLUDED.content,
                    source_updated_at = EXCLUDED.source_updated_at
                WHERE ingest_artifact.source_updated_at < EXCLUDED.source_updated_at
                """,
                upsert_rows,
            )

    async def force_upsert_artifacts_batch(
        self, artifacts: Sequence[BaseIngestArtifact], backfill_id: str | None = None
    ) -> None:
        """Force batch inserts or updates artifacts, bypassing timestamp checks.

        This is useful when metadata must be updated regardless of source_updated_at,
        such as when workspace attribution or permission data changes.

        Args:
            artifacts: List of artifacts to force upsert
            backfill_id: Optional backfill ID to track which sync last saw these artifacts
        """
        if not artifacts:
            return

        upsert_rows = []
        for artifact in artifacts:
            artifact_data = artifact.model_dump()
            upsert_rows.append(
                (
                    str(artifact.id),
                    artifact.entity,
                    artifact.entity_id,
                    str(artifact.ingest_job_id),
                    json.dumps(artifact_data["metadata"]),
                    json.dumps(artifact_data["content"]),
                    artifact.source_updated_at,
                    backfill_id,
                )
            )

        async with self.db_pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO ingest_artifact (id, entity, entity_id, ingest_job_id, metadata, content, source_updated_at, last_seen_backfill_id)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8)
                ON CONFLICT (entity, entity_id) DO UPDATE SET
                    id = EXCLUDED.id,
                    ingest_job_id = EXCLUDED.ingest_job_id,
                    metadata = EXCLUDED.metadata,
                    content = EXCLUDED.content,
                    source_updated_at = EXCLUDED.source_updated_at,
                    last_seen_backfill_id = EXCLUDED.last_seen_backfill_id
                """,
                upsert_rows,
            )

    async def get_artifacts(self, artifact_class: type[T]) -> list[T]:
        """Get typed artifacts using Pydantic models."""
        where_clause, bind_variables = self._build_entity_type_filter(artifact_class)

        query = f"SELECT id, entity, entity_id, ingest_job_id, content, metadata, source_updated_at FROM ingest_artifact {where_clause}"
        rows: list[asyncpg.Record] = await self.db_pool.fetch(query, *bind_variables)
        artifacts = self._deserialize_rows(artifact_class, rows)
        return await self._exclude_artifacts(artifact_class, artifacts)

    async def get_artifacts_by_entity_ids(
        self, artifact_class: type[T], entity_ids: list[str], apply_exclusions: bool = True
    ) -> list[T]:
        """Get typed artifacts by a list of entity IDs.

        Args:
            artifact_class: The Pydantic model class to instantiate
            entity_ids: List of entity IDs to fetch
            apply_exclusions: Whether to apply exclusion rules (default: True)

        Returns:
            List of typed artifact instances matching the entity IDs
        """
        if not entity_ids:
            return []

        where_clause, bind_variables = self._build_entity_ids_filter(artifact_class, entity_ids)
        query = f"SELECT id, entity, entity_id, ingest_job_id, content, metadata, source_updated_at FROM ingest_artifact {where_clause}"

        rows: list[asyncpg.Record] = await self.db_pool.fetch(query, *bind_variables)
        artifacts = self._deserialize_rows(artifact_class, rows)

        if apply_exclusions:
            return await self._exclude_artifacts(artifact_class, artifacts)

        return artifacts

    async def get_artifacts_by_metadata_filter(
        self,
        artifact_class: type[T],
        metadata_filter: dict[str, Any] | None = None,
        batches: dict[str, list[str]] | None = None,
        ranges: dict[str, tuple[datetime, datetime]] | None = None,
    ) -> list[T]:
        """Get typed artifacts by filtering on metadata fields.

        Args:
            artifact_class: The Pydantic model class to instantiate
            metadata_filter: Dictionary of metadata field filters (e.g., {"meeting_id": "123"})
            batches: Dictionary of metadata fields to lists of values for batch filtering (e.g., {"ticket_id": ["1", "2", "3"]})
                       - useful for querying multiple IDs at once
            ranges: Dictionary of metadata fields to (start, end) tuples for date range filtering
                      - useful for getting artifacts within specific time windows

        Returns:
            List of typed artifact instances matching the metadata filter
        """
        no_filtering_specified = not metadata_filter and not batches and not ranges
        if no_filtering_specified:
            return []

        where_clause, bind_variables = self._build_metadata_filter(
            artifact_class, metadata_filter, batches, ranges
        )

        query = f"SELECT id, entity, entity_id, ingest_job_id, content, metadata, source_updated_at FROM ingest_artifact {where_clause}"
        rows: list[asyncpg.Record] = await self.db_pool.fetch(query, *bind_variables)
        artifacts = self._deserialize_rows(artifact_class, rows)
        return await self._exclude_artifacts(artifact_class, artifacts)

    async def delete_artifacts_by_metadata_filter(
        self,
        artifact_class: type[T],
        metadata_filter: dict[str, Any] | None = None,
        batches: dict[str, list[str]] | None = None,
        ranges: dict[str, tuple[datetime, datetime]] | None = None,
    ) -> int:
        no_filtering_specified = not metadata_filter and not batches and not ranges
        if no_filtering_specified:
            return 0

        where_clause, bind_variables = self._build_metadata_filter(
            artifact_class, metadata_filter, batches, ranges
        )
        if not where_clause:
            raise ValueError("WHERE clause must be non-empty to delete artifacts.")

        query = f"DELETE FROM ingest_artifact {where_clause}"
        result = await self.db_pool.execute(query, *bind_variables)
        return int(result.split()[-1])  # Extract count from "DELETE N"

    async def delete_artifacts_by_entity_ids(
        self, artifact_class: type[T], entity_ids: list[str]
    ) -> int:
        where_clause, bind_variables = self._build_entity_ids_filter(artifact_class, entity_ids)
        if not where_clause:
            raise ValueError("WHERE clause must be non-empty to delete artifacts.")

        query = f"DELETE FROM ingest_artifact {where_clause}"
        result = await self.db_pool.execute(query, *bind_variables)
        return int(result.split()[-1])  # Extract count from "DELETE N"

    async def _exclude_artifacts(self, artifact_class: type[T], artifacts: list[T]) -> list[T]:
        entity_type = self._get_entity_type(artifact_class)

        exclusion_service = ExclusionRulesService()
        filtered_artifacts: list[T] = []
        excluded_count = 0

        for artifact in artifacts:
            should_exclude = await exclusion_service.should_exclude(
                artifact.entity_id, entity_type, self.db_pool
            )
            if should_exclude:
                logger.info(f"Excluding artifact based on rules: {artifact.entity_id}")
                excluded_count += 1
            else:
                filtered_artifacts.append(artifact)

        if excluded_count > 0:
            logger.info(
                f"Excluded {excluded_count} artifacts out of {len(artifacts)} based on exclusion rules"
            )

        return filtered_artifacts

    def _build_entity_type_filter(
        self,
        artifact_class: type[T],
    ) -> tuple[str, list[Any]]:
        return "WHERE entity = $1", [self._get_entity_type(artifact_class)]

    def _build_entity_ids_filter(
        self,
        artifact_class: type[T],
        entity_ids: list[str],
    ) -> tuple[str, list[Any]]:
        return "WHERE entity = $1 AND entity_id = ANY($2)", [
            self._get_entity_type(artifact_class),
            entity_ids,
        ]

    def _build_metadata_filter(
        self,
        artifact_class: type[T],
        metadata_filter: dict[str, Any] | None = None,
        batches: dict[str, list[str]] | None = None,
        ranges: dict[str, tuple[datetime, datetime]] | None = None,
    ) -> tuple[str, list[Any]]:
        bind_variables: list[Any] = []
        bind_index = 1

        where_clause = f"WHERE entity = ${bind_index}"
        bind_variables.append(self._get_entity_type(artifact_class))
        bind_index += 1

        # Build the query with JSONB containment operator (@>)
        # This checks if metadata contains all key-value pairs in metadata_filter
        if metadata_filter:
            where_clause += f" AND metadata @> ${bind_index}::jsonb"
            bind_variables.append(json.dumps(metadata_filter))
            bind_index += 1

        if batches:
            for key, value in batches.items():
                where_clause += f" AND metadata ->> ${bind_index} = ANY(${bind_index + 1})"
                bind_variables.append(key)
                bind_variables.append(value)
                bind_index += 2

        if ranges:
            for key, (start, end) in ranges.items():
                where_clause += f" AND (metadata ->> ${bind_index})::timestamptz BETWEEN ${bind_index + 1} AND ${bind_index + 2}"
                bind_variables.append(key)
                bind_variables.append(start)
                bind_variables.append(end)
                bind_index += 3

        return where_clause, bind_variables

    def _get_entity_type(self, artifact_class: type[T]) -> str:
        entity_field = artifact_class.model_fields.get("entity")
        if not entity_field or not entity_field.default:
            raise ValueError(
                f"Artifact class {artifact_class.__name__} must have an 'entity' field with a default value"
            )

        return entity_field.default

    def _deserialize_rows(
        self,
        artifact_class: type[T],
        rows: list[asyncpg.Record],
    ) -> list[T]:
        return [self._deserialize_row(artifact_class, row) for row in rows]

    def _deserialize_row(
        self,
        artifact_class: type[T],
        row: asyncpg.Record,
    ) -> T:
        data = dict(row)

        # Parse JSON strings back to dictionaries
        if isinstance(data.get("content"), str):
            data["content"] = json.loads(data["content"])
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])

        return artifact_class(**data)
