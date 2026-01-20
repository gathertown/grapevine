from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.asana.client.asana_api_models import AsanaStory
from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class AsanaStoryArtifactMetadata(BaseModel):
    story_gid: str
    task_gid: str


def asana_story_entity_id(story_gid: str) -> str:
    return f"asana_story_{story_gid}"


class AsanaStoryArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.ASANA_STORY
    content: AsanaStory
    metadata: AsanaStoryArtifactMetadata

    @classmethod
    def from_api_story(
        cls, story: AsanaStory, task_gid: str, ingest_job_id: UUID
    ) -> "AsanaStoryArtifact":
        return AsanaStoryArtifact(
            entity_id=asana_story_entity_id(story.gid),
            content=story,
            metadata=AsanaStoryArtifactMetadata(story_gid=story.gid, task_gid=task_gid),
            source_updated_at=datetime.fromisoformat(story.created_at),
            ingest_job_id=ingest_job_id,
        )
