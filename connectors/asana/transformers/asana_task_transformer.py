import asyncpg

from connectors.asana.extractors.artifacts.asana_project_artifact import (
    AsanaProjectPermissionsArtifact,
)
from connectors.asana.extractors.artifacts.asana_story_artifact import AsanaStoryArtifact
from connectors.asana.extractors.artifacts.asana_task_artifact import AsanaTaskArtifact
from connectors.asana.transformers.asana_task_document import AsanaTaskDocument
from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AsanaTaskTransformer(BaseTransformer[AsanaTaskDocument]):
    def __init__(self):
        super().__init__(DocumentSource.ASANA_TASK)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[AsanaTaskDocument]:
        db = ArtifactRepository(readonly_db_pool)

        task_artifacts = await db.get_artifacts_by_entity_ids(AsanaTaskArtifact, entity_ids)
        task_ids = {task_artifact.metadata.task_gid for task_artifact in task_artifacts}
        project_ids = {
            gid for task_artifact in task_artifacts for gid in task_artifact.metadata.project_gids
        }

        story_artifacts = await db.get_artifacts_by_metadata_filter(
            AsanaStoryArtifact, batches={"task_gid": list(task_ids)}
        )
        project_artifacts = await db.get_artifacts_by_metadata_filter(
            AsanaProjectPermissionsArtifact, batches={"project_gid": list(project_ids)}
        )

        story_artifacts_by_task_id: dict[str, list[AsanaStoryArtifact]] = {}
        for story_artifact in story_artifacts:
            story_artifacts_by_task_id.setdefault(story_artifact.metadata.task_gid, []).append(
                story_artifact
            )

        project_artifacts_by_task_id: dict[str, list[AsanaProjectPermissionsArtifact]] = {}
        for task_artifact in task_artifacts:
            related_project_artifacts = [
                project_artifact
                for project_artifact in project_artifacts
                if project_artifact.metadata.project_gid in task_artifact.metadata.project_gids
            ]
            project_artifacts_by_task_id[task_artifact.metadata.task_gid] = (
                related_project_artifacts
            )

        documents = [
            AsanaTaskDocument.from_artifacts(
                task_artifact=artifact,
                story_artifacts=story_artifacts_by_task_id.get(artifact.metadata.task_gid, []),
                project_artifacts=project_artifacts_by_task_id.get(artifact.metadata.task_gid, []),
            )
            for artifact in task_artifacts
        ]

        logger.info(
            f"Asana Task transformation complete: Created {len(documents)} documents from {len(entity_ids)} entity_ids and {len(task_artifacts)} task artifacts."
        )

        return documents
