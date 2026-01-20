from dataclasses import dataclass

import asyncpg

from connectors.asana.extractors.artifacts.asana_story_artifact import AsanaStoryArtifact
from connectors.asana.extractors.artifacts.asana_task_artifact import (
    AsanaTaskArtifact,
    asana_task_entity_id,
)
from connectors.asana.transformers.asana_task_document import asana_task_document_id
from connectors.base import BasePruner
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AsanaPruneResult:
    tasks_deleted: int
    stories_deleted: int


class AsanaPruner(BasePruner):
    async def prune_tasks_by_gid(
        self,
        db_pool: asyncpg.Pool,
        tenant_id: str,
        task_gids: list[str],
    ) -> AsanaPruneResult:
        artifact_repo = ArtifactRepository(db_pool)

        entity_ids = [asana_task_entity_id(gid) for gid in task_gids]
        document_ids = [asana_task_document_id(gid) for gid in task_gids]

        tasks_deleted = await artifact_repo.delete_artifacts_by_entity_ids(
            AsanaTaskArtifact, entity_ids
        )
        stories_deleted = await artifact_repo.delete_artifacts_by_metadata_filter(
            AsanaStoryArtifact, batches={"task_gid": task_gids}
        )

        await self.delete_documents(document_ids, tenant_id, db_pool)

        return AsanaPruneResult(
            tasks_deleted=tasks_deleted,
            stories_deleted=stories_deleted,
        )
