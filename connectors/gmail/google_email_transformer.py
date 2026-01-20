import logging

import asyncpg

from connectors.base import ArtifactEntity, BaseTransformer
from connectors.base.doc_ids import get_google_email_doc_id
from connectors.base.document_source import DocumentSource
from connectors.gmail.google_email_artifacts import GoogleEmailMessageArtifact
from connectors.gmail.google_email_message_document import GoogleEmailMessageDocument
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.permissions.utils import make_email_permission_token

logger = logging.getLogger(__name__)


class GoogleEmailTransformer(BaseTransformer):
    supported_entities = {ArtifactEntity.GOOGLE_EMAIL_MESSAGE}

    def __init__(self):
        super().__init__(source_name=DocumentSource.GOOGLE_EMAIL)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[GoogleEmailMessageDocument]:
        repo = ArtifactRepository(readonly_db_pool)

        artifacts = await repo.get_artifacts_by_entity_ids(GoogleEmailMessageArtifact, entity_ids)
        logger.info(
            f"Loaded {len(artifacts)} Google Email message artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        for artifact in artifacts:
            try:
                doc = await self._transform_artifact(artifact)
                if doc:
                    documents.append(doc)
            except Exception as e:
                logger.error(f"Failed to transform artifact {artifact.entity_id}: {e}")
                continue

        logger.info(f"Transformed {len(documents)} Google Email message artifacts into documents")
        return documents

    async def _transform_artifact(
        self, artifact: GoogleEmailMessageArtifact
    ) -> GoogleEmailMessageDocument | None:
        try:
            content = artifact.content
            metadata = artifact.metadata
            entity_id = artifact.entity_id

            # Create raw_data with processed content
            raw_data = {
                "entity_id": entity_id,
                "content": content.model_dump(),
                "metadata": metadata.model_dump(),
                "processed_content": content.body,
                "source_updated_at": artifact.source_updated_at.isoformat(),
            }

            doc_metadata = {
                "message_id": content.message_id,
                "thread_id": content.thread_id,
                "subject": content.subject,
                "body": content.body,
                "source_created_at": content.source_created_at,
                "user_id": content.user_id,
                "user_email": content.user_email,
                "from_address": content.from_address,
                "to_addresses": content.to_addresses,
                "cc_addresses": content.cc_addresses,
                "bcc_addresses": content.bcc_addresses,
                "labels": metadata.labels,
                "size_estimate": metadata.size_estimate,
                "internal_date": metadata.internal_date,
            }

            document = GoogleEmailMessageDocument(
                id=get_google_email_doc_id(str(entity_id)),
                raw_data=raw_data,
                metadata=doc_metadata,
                source_updated_at=artifact.source_updated_at,
                permission_policy="private",
                permission_allowed_tokens=[
                    make_email_permission_token(content.user_email),
                    make_email_permission_token(content.from_address),
                ],
            )

            logger.debug(
                f"Transformed Google Email message {entity_id} into document (chunking will be handled by document.to_embedding_chunks())"
            )
            return document

        except Exception as e:
            logger.error(f"Failed to transform Google Email message artifact: {e}")
            return None
