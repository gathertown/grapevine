import logging

import asyncpg
import markdownify
from dateutil.parser import parse

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.confluence.confluence_artifacts import ConfluencePageArtifact
from connectors.confluence.confluence_page_document import (
    ConfluencePageDocument,
)
from src.ingest.repositories import ArtifactRepository

logger = logging.getLogger(__name__)


class ConfluenceTransformer(BaseTransformer[ConfluencePageDocument]):
    def __init__(self):
        super().__init__(DocumentSource.CONFLUENCE)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[ConfluencePageDocument]:
        repo = ArtifactRepository(readonly_db_pool)

        page_artifacts = await repo.get_artifacts_by_entity_ids(ConfluencePageArtifact, entity_ids)

        logger.info(
            f"Loaded {len(page_artifacts)} Confluence page artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        processed_count = 0
        skipped_count = 0
        error_count = 0

        for artifact in page_artifacts:
            try:
                document = await self._create_document(artifact)

                if document:
                    documents.append(document)
                    processed_count += 1

                    if processed_count % 100 == 0:
                        logger.info(
                            f"Processed {processed_count}/{len(page_artifacts)} Confluence pages"
                        )
                else:
                    skipped_count += 1
                    logger.warning(f"Skipped artifact {artifact.entity_id} - no document created")

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to transform artifact {artifact.id}: {e}")
                continue

        logger.info(
            f"Created {len(documents)} Confluence documents from {len(page_artifacts)} artifacts "
            f"(processed: {processed_count}, skipped: {skipped_count}, errors: {error_count})"
        )
        return documents

    def transform_page_artifact_to_document(
        self, artifact: ConfluencePageArtifact
    ) -> ConfluencePageDocument:
        """Transform a single Confluence page artifact to a document."""
        try:
            return self._create_document_sync(artifact)
        except Exception as e:
            logger.error(f"Failed to transform Confluence page artifact {artifact.entity_id}: {e}")
            raise

    def _create_document_sync(self, artifact: ConfluencePageArtifact) -> ConfluencePageDocument:
        """Create a document from artifact synchronously."""
        try:
            metadata = artifact.metadata
            page_id = metadata.page_id

            # Parse source timestamps
            source_created_at = None
            source_updated_at = None

            if metadata.source_created_at:
                try:
                    source_created_at = parse(metadata.source_created_at)
                except Exception:
                    source_created_at = artifact.source_updated_at
            else:
                source_created_at = artifact.source_updated_at

            if metadata.source_updated_at:
                try:
                    source_updated_at = parse(metadata.source_updated_at)
                except Exception:
                    source_updated_at = artifact.source_updated_at
            else:
                source_updated_at = artifact.source_updated_at

            body_html = (
                artifact.content.page_data.get("body", {}).get("export_view", {}).get("value", "")
            )
            body_content = markdownify.markdownify(body_html, heading_style="ATX")

            document_data = {
                "page_id": page_id,
                "page_title": metadata.page_title,
                "page_url": metadata.page_url,
                "space_id": metadata.space_id,
                "participants": metadata.participants,
                "parent_page_id": metadata.parent_page_id,
                "body_content": body_content,
                "source_created_at": source_created_at.isoformat() if source_created_at else None,
                "source_updated_at": source_updated_at.isoformat() if source_updated_at else None,
            }

            document = ConfluencePageDocument(
                id=f"confluence_page_{page_id}",
                raw_data=document_data,
                source_updated_at=artifact.source_updated_at,
                permission_policy="tenant",
                permission_allowed_tokens=None,
            )

            return document

        except Exception as e:
            logger.error(f"Failed to create document for Confluence page {artifact.entity_id}: {e}")
            raise

    async def _create_document(
        self, artifact: ConfluencePageArtifact
    ) -> ConfluencePageDocument | None:
        """Create a document from artifact asynchronously."""
        try:
            return self._create_document_sync(artifact)
        except Exception as e:
            logger.error(f"Failed to create document for Confluence page {artifact.entity_id}: {e}")
            return None
