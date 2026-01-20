import logging

import asyncpg

from connectors.base import ArtifactEntity, BaseTransformer
from connectors.base.doc_ids import get_google_drive_doc_id
from connectors.base.document_source import DocumentSource
from connectors.base.utils.pdf_extractor import extract_pdf_text
from connectors.google_drive.google_drive_artifacts import (
    GoogleDriveFileArtifact,
    GoogleDriveFileContent,
)
from connectors.google_drive.google_drive_file_document import GoogleDriveFileDocument
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class GoogleDriveTransformer(BaseTransformer):
    supported_entities = {ArtifactEntity.GOOGLE_DRIVE_FILE}

    def __init__(self):
        super().__init__(source_name=DocumentSource.GOOGLE_DRIVE)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[GoogleDriveFileDocument]:
        repo = ArtifactRepository(readonly_db_pool)

        artifacts = await repo.get_artifacts_by_entity_ids(GoogleDriveFileArtifact, entity_ids)
        logger.info(
            f"Loaded {len(artifacts)} Google Drive file artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}

        for artifact in artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform artifact {artifact.entity_id}", counter
            ):
                doc = await self._transform_artifact(artifact)
                if doc:
                    documents.append(doc)

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Google Drive transformation complete: {successful} successful, {failed} failed. "
            f"Transformed {len(documents)} Google Drive file artifacts into documents"
        )
        return documents

    def _is_supported_mime_type(self, mime_type: str) -> bool:
        """Check if MIME type is supported for text extraction.

        Args:
            mime_type: MIME type to check

        Returns:
            True if the file type is supported for text extraction
        """
        if not mime_type:
            return False

        google_workspace_types = {
            "application/vnd.google-apps.document",
            "application/vnd.google-apps.spreadsheet",
            "application/vnd.google-apps.presentation",
        }

        if mime_type in google_workspace_types:
            return True

        if mime_type == "application/pdf":
            return True

        return mime_type.startswith("text/")

    def _generate_placeholder_content(
        self, file_name: str, mime_type: str, content: GoogleDriveFileContent
    ) -> str:
        """Generate metadata-only content for unsupported file types.

        Args:
            file_name: Name of the file
            mime_type: MIME type of the file
            content: File content metadata

        Returns:
            Formatted metadata string
        """
        lines = [
            f"File: {file_name}",
            f"Type: {mime_type}",
        ]

        if content.source_created_at:
            lines.append(f"Created: {content.source_created_at}")

        if content.source_modified_at:
            lines.append(f"Modified: {content.source_modified_at}")

        owners = content.owners
        if owners:
            owner_names = [owner.display_name or "Unknown" for owner in owners]
            lines.append(f"Owners: {', '.join(owner_names)}")

        return "\n".join(lines)

    def _process_pdf_binary(
        self, binary_content: str, file_name: str, content: GoogleDriveFileContent
    ) -> str:
        """Try to extract text from binary PDF

        Args:
            binary_content: Binary PDF content as string
            file_name: Name of the PDF file
            content: File content metadata for fallback

        Returns:
            Extracted text if successful, placeholder content otherwise
        """
        try:
            pdf_bytes = binary_content.encode("utf-8")
            extracted_text = extract_pdf_text(pdf_bytes, source_identifier=file_name)

            if extracted_text:
                logger.info(
                    f"Successfully extracted {len(extracted_text)} characters from binary PDF: {file_name}"
                )
                return extracted_text
            else:
                logger.info(f"No text content found in binary PDF: {file_name}")
                return self._generate_placeholder_content(file_name, "application/pdf", content)

        except Exception as e:
            logger.warning(f"Failed to process binary PDF content for {file_name}: {e}")
            return self._generate_placeholder_content(file_name, "application/pdf", content)

    async def _transform_artifact(
        self, artifact: GoogleDriveFileArtifact
    ) -> GoogleDriveFileDocument | None:
        try:
            content = artifact.content
            metadata = artifact.metadata
            entity_id = artifact.entity_id
            mime_type = metadata.mime_type or ""
            file_name = content.name or "Untitled"

            file_content = content.content or ""

            if mime_type == "application/pdf" and file_content.startswith("%PDF"):
                file_content = self._process_pdf_binary(file_content, file_name, content)
            elif not self._is_supported_mime_type(mime_type):
                file_content = self._generate_placeholder_content(file_name, mime_type, content)
                logger.info(
                    f"Generated placeholder content for unsupported type {mime_type}: {file_name}"
                )

            # Create raw_data with processed content
            raw_data = {
                "entity_id": entity_id,
                "content": content.model_dump(),
                "metadata": metadata.model_dump(),
                "processed_content": file_content,
                "source_updated_at": artifact.source_updated_at.isoformat(),
            }

            doc_metadata = {
                "file_id": entity_id,
                "file_name": file_name,
                "mime_type": mime_type,
                "drive_id": content.drive_id,
                "drive_name": content.drive_name,
                "parent_folder_ids": metadata.parent_folder_ids or [],
                "web_view_link": metadata.web_view_link,
                "size_bytes": metadata.size_bytes,
                "starred": metadata.starred,
                "source_created_at": content.source_created_at,
                "source_modified_at": content.source_modified_at,
                "owners": [owner.model_dump() for owner in (content.owners or [])],
                "last_modifying_user": content.last_modifying_user.model_dump()
                if content.last_modifying_user
                else None,
                "description": content.description,
            }

            document = GoogleDriveFileDocument(
                id=get_google_drive_doc_id(str(entity_id)),
                raw_data=raw_data,
                metadata=doc_metadata,
                source_updated_at=artifact.source_updated_at,
                permission_policy="tenant",
                permission_allowed_tokens=None,
            )

            logger.debug(
                f"Transformed Google Drive file {entity_id} into document (chunking will be handled by document.to_embedding_chunks())"
            )
            return document

        except Exception as e:
            logger.error(f"Failed to transform Google Drive file artifact: {e}")
            return None
