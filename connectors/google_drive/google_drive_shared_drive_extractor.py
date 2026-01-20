import logging
import math
import time
from datetime import UTC, datetime
from typing import Any
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
from connectors.google_drive.google_drive_models import GoogleDriveSharedDriveConfig
from src.clients.google_drive import GoogleDriveClient
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = logging.getLogger(__name__)

PERMISSION_CHECK_BATCH_SIZE = 10


class GoogleDriveSharedDriveExtractor(BaseExtractor[GoogleDriveSharedDriveConfig]):
    """Extractor for processing a specific shared drive."""

    source_name = "google_drive_shared_drive"

    def __init__(self):
        super().__init__()
        self.ssm_client = SSMClient()

    async def process_job(
        self,
        job_id: str,
        config: GoogleDriveSharedDriveConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.time()
        try:
            # Get admin email from SSM
            admin_email = await self.ssm_client.get_google_drive_admin_email(config.tenant_id)
            if not admin_email:
                raise ValueError(f"No admin email found for tenant {config.tenant_id}")

            drive_client = GoogleDriveClient(
                tenant_id=config.tenant_id, admin_email=admin_email, ssm_client=self.ssm_client
            )

            logger.info(
                f"Processing shared drive '{config.drive_name}' (ID: {config.drive_id}, job {job_id})"
            )

            all_file_ids = await self._process_shared_drive(
                drive_client,
                config.drive_id,
                config.drive_name,
                job_id,
                config.tenant_id,
                db_pool,
                trigger_indexing,
            )

            total_index_batches = math.ceil(len(all_file_ids) / DEFAULT_INDEX_BATCH_SIZE)
            if config.backfill_id and total_index_batches > 0:
                await increment_backfill_total_index_jobs(
                    config.backfill_id, config.tenant_id, total_index_batches
                )

            for i in range(0, len(all_file_ids), DEFAULT_INDEX_BATCH_SIZE):
                batched_file_ids = all_file_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batched_file_ids,
                    DocumentSource.GOOGLE_DRIVE,
                    config.tenant_id,
                    config.backfill_id,
                )

            if config.backfill_id:
                await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

            duration = time.time() - start_time
            logger.info(
                f"Successfully completed processing shared drive '{config.drive_name}' in {duration:.2f} seconds"
            )

        except Exception as e:
            logger.error(f"Job {job_id} failed for shared drive '{config.drive_name}': {e}")
            raise
        finally:
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )

    async def _check_folder_permissions_batch(
        self,
        drive_client: GoogleDriveClient,
        folders: list[dict[str, Any]],
        domain_accessible_folder_ids: set[str],
    ) -> None:
        """Check permissions for a batch of folders and update the domain-accessible set.

        Args:
            drive_client: Google Drive client
            folders: List of folder metadata dicts to check
            domain_accessible_folder_ids: Set to update with domain-accessible folder IDs
        """
        folder_ids = [f["id"] for f in folders]
        permissions_map = await drive_client.get_file_permissions_batch(folder_ids)

        for folder in folders:
            folder_id = folder["id"]
            permissions = permissions_map.get(folder_id, [])
            logger.debug(f"Folder '{folder.get('name')}' ({folder_id}) permissions: {permissions}")

            if drive_client.is_domain_accessible(permissions):
                domain_accessible_folder_ids.add(folder_id)

    def _expand_domain_accessible_folders(
        self,
        domain_accessible_folder_ids: set[str],
        folder_hierarchy: dict[str, list[str]],
    ) -> set[str]:
        """Recursively expand domain-accessible folders to include all descendants.

        Args:
            domain_accessible_folder_ids: Set of folder IDs that have domain access
            folder_hierarchy: Map of parent folder ID -> list of child folder IDs

        Returns:
            Expanded set including all descendant folders
        """
        expanded_folder_ids = set(domain_accessible_folder_ids)
        folders_to_process = list(domain_accessible_folder_ids)

        while folders_to_process:
            current_folder = folders_to_process.pop()
            child_folders = folder_hierarchy.get(current_folder, [])

            for child_folder_id in child_folders:
                if child_folder_id not in expanded_folder_ids:
                    expanded_folder_ids.add(child_folder_id)
                    folders_to_process.append(child_folder_id)

        return expanded_folder_ids

    async def _identify_domain_accessible_folders(
        self,
        drive_client: GoogleDriveClient,
        folders_with_augmented_perms: list[dict[str, Any]],
        folder_hierarchy: dict[str, list[str]],
    ) -> set[str]:
        """Check folder permissions and recursively expand to include descendants.

        Args:
            drive_client: Google Drive client
            folders_with_augmented_perms: Folders that need permission checks
            folder_hierarchy: Map of parent folder ID -> child folder IDs

        Returns:
            Set of all domain-accessible folder IDs (including descendants)
        """
        domain_accessible_folder_ids: set[str] = set()

        for i in range(0, len(folders_with_augmented_perms), PERMISSION_CHECK_BATCH_SIZE):
            batch = folders_with_augmented_perms[i : i + PERMISSION_CHECK_BATCH_SIZE]
            await self._check_folder_permissions_batch(
                drive_client, batch, domain_accessible_folder_ids
            )

        expanded_folder_ids = self._expand_domain_accessible_folders(
            domain_accessible_folder_ids, folder_hierarchy
        )

        return expanded_folder_ids

    def _filter_files_to_check(
        self,
        all_files: list[dict[str, Any]],
        domain_accessible_folder_ids: set[str],
    ) -> list[dict[str, Any]]:
        """Filter files that need permission checks.

        Files are included if they're in domain-accessible folders OR have augmented permissions.

        Args:
            all_files: All files found in the shared drive
            domain_accessible_folder_ids: Set of domain-accessible folder IDs

        Returns:
            List of files that need permission checks
        """
        files_to_check: list[dict[str, Any]] = []

        for file_metadata in all_files:
            parent_folders = file_metadata.get("parents", [])
            in_domain_accessible_folder = bool(set(parent_folders) & domain_accessible_folder_ids)
            has_augmented_perms = file_metadata.get("hasAugmentedPermissions", False)

            if in_domain_accessible_folder or has_augmented_perms:
                files_to_check.append(file_metadata)

        return files_to_check

    async def _process_files_in_batches(
        self,
        drive_client: GoogleDriveClient,
        files_to_check: list[dict[str, Any]],
        drive_name: str,
        job_id: str,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Process files in batches, checking permissions and storing artifacts.

        Args:
            drive_client: Google Drive client
            files_to_check: Files that need permission checks
            drive_name: Shared drive name
            job_id: Job ID
            db_pool: Database connection pool

        Returns:
            List of processed file IDs
        """
        all_file_ids: list[str] = []

        for i in range(0, len(files_to_check), PERMISSION_CHECK_BATCH_SIZE):
            batch = files_to_check[i : i + PERMISSION_CHECK_BATCH_SIZE]
            processed_file_ids = await self._process_permission_batch(
                drive_client,
                batch,
                drive_name,
                job_id,
                db_pool,
            )
            all_file_ids.extend(processed_file_ids)

        return all_file_ids

    async def _scan_and_build_hierarchy(
        self,
        drive_client: GoogleDriveClient,
        drive_id: str,
        drive_name: str,
    ) -> tuple[dict[str, list[str]], list[dict[str, Any]], list[dict[str, Any]]]:
        folder_hierarchy: dict[str, list[str]] = {}
        folders_with_augmented_perms: list[dict[str, Any]] = []
        all_files: list[dict[str, Any]] = []
        page_token = None

        while True:
            result = await drive_client.list_files(
                query="trashed = false",
                page_token=page_token,
                include_team_drives=True,
                drive_id=drive_id,
                include_permissions=False,
            )

            items = result.get("files", [])

            for item in items:
                mime_type = item.get("mimeType", "")

                if mime_type == "application/vnd.google-apps.folder":
                    folder_id = item["id"]

                    parent_folders = item.get("parents", [])
                    for parent_id in parent_folders:
                        if parent_id not in folder_hierarchy:
                            folder_hierarchy[parent_id] = []
                        folder_hierarchy[parent_id].append(folder_id)

                    if item.get("hasAugmentedPermissions", False):
                        folders_with_augmented_perms.append(item)
                else:
                    all_files.append(item)

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return folder_hierarchy, folders_with_augmented_perms, all_files

    async def _process_shared_drive(
        self,
        drive_client: GoogleDriveClient,
        drive_id: str,
        drive_name: str,
        job_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> list[str]:
        if not drive_client._domain:
            logger.error("No domain found in drive client")
            return []

        (
            folder_hierarchy,
            folders_with_augmented_perms,
            all_files,
        ) = await self._scan_and_build_hierarchy(drive_client, drive_id, drive_name)

        domain_accessible_folder_ids = await self._identify_domain_accessible_folders(
            drive_client, folders_with_augmented_perms, folder_hierarchy
        )

        files_to_check = self._filter_files_to_check(all_files, domain_accessible_folder_ids)

        processed_file_ids = await self._process_files_in_batches(
            drive_client, files_to_check, drive_name, job_id, db_pool
        )

        logger.info(
            f"Finished processing shared drive '{drive_name}'. "
            f"Total domain-accessible files indexed: {len(processed_file_ids)}"
        )

        return processed_file_ids

    async def _process_permission_batch(
        self,
        drive_client: GoogleDriveClient,
        files: list[dict[str, Any]],
        drive_name: str,
        job_id: str,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Process a batch of files, checking permissions concurrently."""
        file_ids = [f["id"] for f in files]
        permissions_map = await drive_client.get_file_permissions_batch(file_ids)

        processed_file_ids = []

        for file_metadata in files:
            file_id = file_metadata["id"]
            permissions = permissions_map.get(file_id, [])

            if not drive_client.is_domain_accessible(permissions):
                continue

            file_metadata["permissions"] = permissions

            artifact = await self._create_file_artifact(
                drive_client, file_metadata, job_id, drive_name
            )

            if artifact:
                self._sanitize_google_drive_artifact(artifact)
                await self.store_artifact(db_pool, artifact)
                processed_file_ids.append(file_id)

        return processed_file_ids

    async def _create_file_artifact(
        self,
        drive_client: GoogleDriveClient,
        file_metadata: dict[str, Any],
        job_id: str,
        drive_name: str,
    ) -> GoogleDriveFileArtifact | None:
        """Create a file artifact from metadata."""
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
                    drive_id=file_metadata.get("driveId"),
                    drive_name=drive_name,
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

            return artifact

        except Exception as e:
            logger.error(f"Failed to create artifact for file {file_metadata.get('id')}: {e}")
            return None

    def _sanitize_google_drive_artifact(self, artifact: GoogleDriveFileArtifact) -> None:
        """Sanitize Google Drive artifact content to remove PostgreSQL-incompatible characters."""
        if artifact.content:
            if artifact.content.content:
                artifact.content.content = artifact.content.content.replace("\x00", "")

            if artifact.content.name:
                artifact.content.name = artifact.content.name.replace("\x00", "")

            if artifact.content.description:
                artifact.content.description = artifact.content.description.replace("\x00", "")

            if artifact.content.drive_name:
                artifact.content.drive_name = artifact.content.drive_name.replace("\x00", "")
