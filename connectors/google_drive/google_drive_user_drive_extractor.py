import logging
import math
import time
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback, get_google_drive_file_entity_id
from connectors.base.document_source import DocumentSource
from connectors.google_drive.google_drive_artifacts import (
    GoogleDriveFileArtifact,
    GoogleDriveFileContent,
    GoogleDriveFileMetadata,
    GoogleDriveFileOwner,
)
from connectors.google_drive.google_drive_models import GoogleDriveUserDriveConfig
from src.clients.google_drive import GoogleDriveClient
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = logging.getLogger(__name__)


class GoogleDriveUserDriveExtractor(BaseExtractor[GoogleDriveUserDriveConfig]):
    source_name = "google_drive_user_drive"

    def __init__(self):
        super().__init__()
        self.ssm_client = SSMClient()

    async def process_job(
        self,
        job_id: str,
        config: GoogleDriveUserDriveConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.time()
        try:
            admin_email = await self.ssm_client.get_google_drive_admin_email(config.tenant_id)
            if not admin_email:
                raise ValueError(f"No admin email found for tenant {config.tenant_id}")

            drive_client = GoogleDriveClient(
                tenant_id=config.tenant_id,
                admin_email=config.user_email,
                ssm_client=self.ssm_client,
            )

            logger.info(f"Processing personal drive for user {config.user_email} (job {job_id})")

            all_file_ids = await self._process_user_drive(
                drive_client,
                config.user_email,
                job_id,
                config.tenant_id,
                db_pool,
                trigger_indexing,
            )

            # Calculate total number of index batches and track them upfront
            total_index_batches = math.ceil(len(all_file_ids) / DEFAULT_INDEX_BATCH_SIZE)
            if config.backfill_id and total_index_batches > 0:
                await increment_backfill_total_index_jobs(
                    config.backfill_id, config.tenant_id, total_index_batches
                )

            # Trigger indexing in batches
            for i in range(0, len(all_file_ids), DEFAULT_INDEX_BATCH_SIZE):
                batched_file_ids = all_file_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batched_file_ids,
                    DocumentSource.GOOGLE_DRIVE,
                    config.tenant_id,
                    config.backfill_id,
                )

            # Track completion if backfill_id exists
            if config.backfill_id:
                await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

            duration = time.time() - start_time
            logger.info(
                f"Successfully completed processing personal drive for {config.user_email} in {duration:.2f} seconds"
            )

        except Exception as e:
            logger.error(f"Job {job_id} failed for user {config.user_email}: {e}")
            raise
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )

    async def _process_user_drive(
        self,
        drive_client: GoogleDriveClient,
        user_email: str,
        job_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> list[str]:
        all_file_ids = []
        total_processed = 0
        page_token = None

        domain = user_email.split("@")[1]

        while True:
            result = await drive_client.list_files(
                query="trashed = false and 'me' in owners",
                page_token=page_token,
                include_permissions=True,
                include_team_drives=False,
            )

            files = result.get("files", [])

            for file_metadata in files:
                mime_type = file_metadata.get("mimeType", "")

                if mime_type == "application/vnd.google-apps.folder":
                    continue

                permissions = file_metadata.get("permissions", [])
                if not self._is_domain_accessible(permissions, domain):
                    continue

                artifact = await self._create_file_artifact(
                    drive_client, file_metadata, job_id, user_email
                )

                if artifact:
                    self._sanitize_google_drive_artifact(artifact)
                    await self.store_artifact(db_pool, artifact)
                    all_file_ids.append(file_metadata["id"])
                    total_processed += 1

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.info(
            f"Finished processing personal drive for {user_email}. "
            f"Total domain-accessible files: {total_processed}"
        )

        return all_file_ids

    def _is_domain_accessible(self, permissions: list[dict], domain: str) -> bool:
        for permission in permissions:
            if (
                permission.get("type") == "domain"
                and permission.get("domain") == domain
                and permission.get("role") in ["reader", "commenter", "writer", "owner"]
            ):
                return True
        return False

    def _sanitize_google_drive_artifact(self, artifact: GoogleDriveFileArtifact) -> None:
        if artifact.content:
            if artifact.content.content:
                artifact.content.content = artifact.content.content.replace("\x00", "")

            if artifact.content.name:
                artifact.content.name = artifact.content.name.replace("\x00", "")

            if artifact.content.description:
                artifact.content.description = artifact.content.description.replace("\x00", "")

            if artifact.content.drive_name:
                artifact.content.drive_name = artifact.content.drive_name.replace("\x00", "")

    async def _create_file_artifact(
        self,
        drive_client: GoogleDriveClient,
        file_metadata: dict,
        job_id: str,
        user_email: str,
    ) -> GoogleDriveFileArtifact | None:
        try:
            file_id = file_metadata["id"]
            mime_type = file_metadata.get("mimeType", "")

            content = await drive_client.get_file_content(file_id, mime_type, file_metadata)

            owners = []
            for owner_data in file_metadata.get("owners", []):
                owners.append(
                    GoogleDriveFileOwner(
                        display_name=owner_data.get("displayName", "Unknown"),
                        email_address=owner_data.get("emailAddress"),
                        permission_id=owner_data.get("permissionId"),
                        photo_link=owner_data.get("photoLink"),
                    )
                )

            last_modifying_user = None
            if file_metadata.get("lastModifyingUser"):
                user_data = file_metadata["lastModifyingUser"]
                last_modifying_user = GoogleDriveFileOwner(
                    display_name=user_data.get("displayName", "Unknown"),
                    email_address=user_data.get("emailAddress"),
                    permission_id=user_data.get("permissionId"),
                    photo_link=user_data.get("photoLink"),
                )

            file_name = file_metadata.get("name", "")
            file_extension = None
            if "." in file_name:
                file_extension = file_name.rsplit(".", 1)[-1].lower()

            artifact = GoogleDriveFileArtifact(
                entity_id=get_google_drive_file_entity_id(file_id=file_id),
                ingest_job_id=UUID(job_id),
                source_updated_at=datetime.fromisoformat(
                    file_metadata.get("modifiedTime", datetime.now(UTC).isoformat())
                ),
                content=GoogleDriveFileContent(
                    file_id=file_id,
                    name=file_name,
                    content=content,
                    description=file_metadata.get("description"),
                    source_created_at=file_metadata.get("createdTime"),
                    source_modified_at=file_metadata.get("modifiedTime"),
                    owners=owners,
                    last_modifying_user=last_modifying_user,
                    drive_id=None,
                    drive_name=f"{user_email}'s Drive",
                ),
                metadata=GoogleDriveFileMetadata(
                    mime_type=mime_type,
                    file_extension=file_extension,
                    parent_folder_ids=file_metadata.get("parents", []),
                    web_view_link=file_metadata.get("webViewLink"),
                    size_bytes=int(file_metadata["size"]) if file_metadata.get("size") else None,
                    permissions=file_metadata.get("permissions", []),
                    starred=file_metadata.get("starred", False),
                ),
            )

            logger.debug(f"Created artifact for file {file_id}: {file_name}")
            return artifact

        except Exception as e:
            logger.error(f"Failed to create artifact for file {file_metadata.get('id')}: {e}")
            return None
