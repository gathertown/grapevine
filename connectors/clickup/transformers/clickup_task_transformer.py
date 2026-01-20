import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.clickup.extractors.artifacts.clickup_comment_artifact import ClickupCommentArtifact
from connectors.clickup.extractors.artifacts.clickup_list_artifact import ClickupListArtifact
from connectors.clickup.extractors.artifacts.clickup_task_artifact import ClickupTaskArtifact
from connectors.clickup.extractors.artifacts.clickup_workspace_artifact import (
    ClickupWorkspaceArtifact,
)
from connectors.clickup.transformers.clickup_task_document import ClickupTaskDocument
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


class ClickupTaskTransformer(BaseTransformer[ClickupTaskDocument]):
    def __init__(self):
        super().__init__(DocumentSource.CLICKUP_TASK)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[ClickupTaskDocument]:
        db = ArtifactRepository(readonly_db_pool)

        task_artifacts = await db.get_artifacts_by_entity_ids(ClickupTaskArtifact, entity_ids)
        task_ids = {task_artifact.metadata.task_id for task_artifact in task_artifacts}
        list_ids = {task_artifact.metadata.list_id for task_artifact in task_artifacts}
        workspace_ids = {task_artifact.metadata.workspace_id for task_artifact in task_artifacts}

        comment_artifacts = await db.get_artifacts_by_metadata_filter(
            ClickupCommentArtifact, batches={"task_id": list(task_ids)}
        )
        list_artifacts = await db.get_artifacts_by_metadata_filter(
            ClickupListArtifact, batches={"list_id": list(list_ids)}
        )
        workspace_artifacts = await db.get_artifacts_by_metadata_filter(
            ClickupWorkspaceArtifact, batches={"workspace_id": list(workspace_ids)}
        )

        comment_artifacts_by_task_id: dict[str, list[ClickupCommentArtifact]] = {}
        for comment_artifact in comment_artifacts:
            comment_artifacts_by_task_id.setdefault(comment_artifact.metadata.task_id, []).append(
                comment_artifact
            )

        workspace_artifacts_by_id = {wa.metadata.workspace_id: wa for wa in workspace_artifacts}
        list_artifacts_by_id = {la.metadata.list_id: la for la in list_artifacts}

        documents: list[ClickupTaskDocument] = []
        for artifact in task_artifacts:
            try:
                workspace_artifact = workspace_artifacts_by_id[artifact.metadata.workspace_id]
                list_artifact = list_artifacts_by_id[artifact.metadata.list_id]
            except KeyError as e:
                logger.error(
                    "Missing related artifact for Clickup task, skipped",
                    task_id=artifact.metadata.task_id,
                    error=str(e),
                    workspace_id=artifact.metadata.workspace_id,
                    space_id=artifact.metadata.space_id,
                    list_id=artifact.metadata.list_id,
                )
                continue

            # sort in chronological order, same as clickup UI
            comment_artifacts = comment_artifacts_by_task_id.get(artifact.metadata.task_id, [])
            sorted_comment_artifacts = sorted(
                comment_artifacts, key=lambda ca: int(ca.content.date)
            )

            document = ClickupTaskDocument.from_artifacts(
                task_artifact=artifact,
                comment_artifacts=sorted_comment_artifacts,
                workspace_artifact=workspace_artifact,
                list_artifact=list_artifact,
            )
            documents.append(document)

        logger.info(
            f"Clickup Task transformation complete: Created {len(documents)} documents from {len(entity_ids)} entity_ids and {len(task_artifacts)} task artifacts."
        )

        return documents
