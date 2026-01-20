import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from connectors.base import (
    BaseExtractor,
    BaseIngestArtifact,
    TriggerIndexingCallback,
    get_google_drive_file_entity_id,
)
from connectors.base.document_source import DocumentSource
from connectors.google_drive.google_drive_artifacts import (
    GoogleDriveFileArtifact,
    GoogleDriveFileContent,
    GoogleDriveFileMetadata,
    GoogleDriveFileOwner,
)
from connectors.google_drive.google_drive_pruner import google_drive_pruner
from src.clients.google_drive import GoogleDriveClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


class GoogleDriveWebhookConfig(BaseModel):
    body: dict[str, Any]
    headers: dict[str, str]
    tenant_id: str


class GoogleDriveWebhookExtractor(BaseExtractor[GoogleDriveWebhookConfig]):
    source_name = "google_drive_webhook"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def get_google_drive_client(self, tenant_id: str) -> GoogleDriveClient:
        """Get GoogleDriveClient for the specified tenant."""
        admin_email = await self.ssm_client.get_google_drive_admin_email(tenant_id)
        if not admin_email:
            raise ValueError(f"No Google Drive admin email configured for tenant {tenant_id}")
        return GoogleDriveClient(
            tenant_id=tenant_id, admin_email=admin_email, ssm_client=self.ssm_client
        )

    async def process_job(
        self,
        job_id: str,
        config: GoogleDriveWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a Google Drive webhook ingest job.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to Google Drive webhooks
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing for entity IDs

        Raises:
            Exception: If processing fails
        """
        try:
            headers = config.headers
            tenant_id = config.tenant_id

            resource_state = headers.get("x-goog-resource-state", "")
            resource_uri = headers.get("x-goog-resource-uri", "")
            channel_id = headers.get("x-goog-channel-id", "")

            logger.info(
                f"Processing Google Drive webhook job {job_id} for tenant {tenant_id} "
                f"(state: {resource_state}, channel: {channel_id})"
            )

            if not resource_state:
                logger.warning(f"No resource state in Google Drive webhook headers: {headers}")
                return

            if not resource_uri:
                logger.warning(f"No resource URI in Google Drive webhook headers: {headers}")
                return

            if resource_state == "sync":
                logger.info("Google Drive webhook sync event - ignoring")
                return

            artifacts = []

            if resource_state == "change":
                page_token = self._extract_page_token_from_uri(resource_uri)
                if not page_token:
                    logger.warning(
                        f"Could not extract page token from resource URI: {resource_uri}"
                    )
                    return

                logger.info(f"Processing Google Drive changes from page token: {page_token}")
                artifacts = await self._handle_changes(
                    job_id, page_token, channel_id, tenant_id, db_pool
                )

            elif resource_state in ["add", "update", "untrash"]:
                file_id = self._extract_file_id_from_uri(resource_uri)
                if not file_id:
                    logger.warning(f"Could not extract file ID from resource URI: {resource_uri}")
                    return

                logger.info(
                    f"Processing Google Drive file {resource_state} event for file {file_id}"
                )
                artifacts = await self._handle_file_change(job_id, file_id, tenant_id, db_pool)

            elif resource_state in ["remove", "trash"]:
                file_id = self._extract_file_id_from_uri(resource_uri)
                if not file_id:
                    logger.warning(f"Could not extract file ID from resource URI: {resource_uri}")
                    return

                logger.info(
                    f"Processing Google Drive file {resource_state} event for file {file_id}"
                )
                await self._handle_file_removal(file_id, tenant_id, db_pool)
                return

            else:
                logger.info(f"Ignoring Google Drive event with state: {resource_state}")
                return

            if artifacts:
                entity_ids = []
                for artifact in artifacts:
                    await self.store_artifact(db_pool, artifact)
                    entity_ids.append(artifact.entity_id)

                if entity_ids:
                    await trigger_indexing(entity_ids, DocumentSource.GOOGLE_DRIVE, tenant_id)
                    logger.info(f"Processed {len(entity_ids)} Google Drive artifacts from webhook")

        except Exception as e:
            logger.error(f"Failed to process Google Drive webhook job {job_id}: {e}")
            raise

    def _extract_page_token_from_uri(self, resource_uri: str) -> str | None:
        """Extract page token from Google Drive changes URI.

        Args:
            resource_uri: The resource URI from X-Goog-Resource-URI header

        Returns:
            Page token or None if extraction fails
        """
        try:
            # Expected format: https://www.googleapis.com/drive/v3/changes?alt=json&pageToken=XXX&restrictToMyDrive=true
            if "pageToken=" in resource_uri:
                parts = resource_uri.split("pageToken=")
                if len(parts) > 1:
                    token_part = parts[1].split("&")[0]
                    return token_part
            return None
        except Exception as e:
            logger.error(f"Error extracting page token from URI {resource_uri}: {e}")
            return None

    def _extract_file_id_from_uri(self, resource_uri: str) -> str | None:
        """Extract file ID from Google Drive resource URI for direct file events.

        Args:
            resource_uri: The resource URI from X-Goog-Resource-URI header

        Returns:
            File ID or None if extraction fails
        """
        try:
            # Expected format for file events: https://www.googleapis.com/drive/v3/files/{fileId}
            if "/files/" in resource_uri:
                parts = resource_uri.split("/files/")
                if len(parts) > 1:
                    file_id = parts[1].split("?")[0]  # Remove query parameters if any
                    return file_id
            return None
        except Exception as e:
            logger.error(f"Error extracting file ID from URI {resource_uri}: {e}")
            return None

    async def _handle_changes(
        self,
        job_id: str,
        page_token: str,
        channel_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> list[BaseIngestArtifact]:
        """Handle Google Drive changes by fetching from the Changes API.

        Args:
            job_id: The ingest job ID
            page_token: Page token from the webhook
            channel_id: Channel ID for this webhook
            tenant_id: Tenant ID
            db_pool: Database connection pool

        Returns:
            List of artifacts created from the changes
        """
        try:
            drive_client = await self.get_google_drive_client(tenant_id)

            # First, we need to determine which user this channel belongs to
            # Extract user email from channel token if available
            async with db_pool.acquire() as conn:
                # Get webhook config to find the user for this channel
                config_row = await conn.fetchrow(
                    "SELECT value FROM config WHERE key = 'GOOGLE_DRIVE_WEBHOOKS'"
                )

                if not config_row:
                    logger.warning(f"No webhook config found for tenant {tenant_id}")
                    return []

                import json

                webhook_config = json.loads(config_row["value"])

                # Find the user or drive for this channel
                user_email = None
                drive_id = None

                for email, channel_info in webhook_config.get("users", {}).items():
                    if channel_info["channel_id"] == channel_id:
                        user_email = email
                        break

                if not user_email:
                    for drive_id_key, channel_info in webhook_config.get(
                        "shared_drives", {}
                    ).items():
                        if channel_info["channel_id"] == channel_id:
                            drive_id = drive_id_key
                            break

                if not user_email and not drive_id:
                    logger.warning(f"Could not find user or drive for channel {channel_id}")
                    return []

            # Get changes using the appropriate client
            if user_email:
                # Impersonate the user to get their changes
                user_client = await drive_client.impersonate_user(user_email)
                changes_response = await user_client.list_changes(page_token)
                changes = changes_response.get("changes", [])
                logger.info(f"Found {len(changes)} changes for user {user_email}")
            elif drive_id:
                # Get changes for the shared drive
                changes_response = await drive_client.list_changes(page_token, drive_id=drive_id)
                changes = changes_response.get("changes", [])
                logger.info(f"Found {len(changes)} changes for shared drive {drive_id}")
            else:
                return []

            artifacts = []
            for change in changes:
                try:
                    if change.get("removed") or change.get("file", {}).get("trashed"):
                        # File was removed or trashed
                        if "fileId" in change:
                            await self._handle_file_removal(change["fileId"], tenant_id, db_pool)
                    else:
                        # File was added or updated
                        file_data = change.get("file")
                        if file_data and file_data.get("id"):
                            file_artifacts = await self._handle_file_change(
                                job_id, file_data["id"], tenant_id, db_pool
                            )
                            artifacts.extend(file_artifacts)
                except Exception as e:
                    logger.error(f"Error processing change {change}: {e}")
                    continue

            logger.info(f"Processed {len(changes)} changes, created {len(artifacts)} artifacts")
            return artifacts

        except Exception as e:
            logger.error(f"Failed to handle changes for page token {page_token}: {e}")
            return []

    async def _handle_file_change(
        self,
        job_id: str,
        file_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,  # noqa: ARG002
    ) -> list[BaseIngestArtifact]:
        """Handle file add/update/untrash events."""
        try:
            drive_client = await self.get_google_drive_client(tenant_id)

            # Get current file metadata
            file_metadata = await drive_client.get_file_metadata(file_id)

            # Skip folders
            if file_metadata.get("mimeType") == "application/vnd.google-apps.folder":
                logger.debug(f"Skipping folder: {file_id}")
                return []

            # Get file permissions to check domain accessibility
            permissions = await drive_client.get_file_permissions(file_id)
            if not drive_client.is_domain_accessible(permissions):
                logger.info(f"File {file_id} is not domain accessible, deleting if exists")
                await google_drive_pruner.delete_file(file_id, tenant_id, db_pool)
                return []

            # Get file content
            content = await drive_client.get_file_content(
                file_id, file_metadata.get("mimeType", "")
            )
            if not content:
                logger.warning(f"No content extracted for file {file_id}, skipping")
                return []

            # Create artifact
            artifact = await self._create_file_artifact(
                file_metadata, content, permissions, job_id, tenant_id
            )

            if artifact:
                return [artifact]
            else:
                return []

        except Exception as e:
            logger.error(f"Failed to handle file change for {file_id}: {e}")
            return []

    async def _handle_file_removal(
        self, file_id: str, tenant_id: str, db_pool: asyncpg.Pool
    ) -> None:
        """Handle file remove/trash events by marking for pruning."""
        try:
            # Use pruner to handle file removal
            await google_drive_pruner.delete_file(file_id, tenant_id, db_pool)
            logger.info(f"Marked Google Drive file {file_id} for pruning")
        except Exception as e:
            logger.error(f"Failed to handle file removal for {file_id}: {e}")

    async def _create_file_artifact(
        self,
        file_metadata: dict[str, Any],
        content: str,
        permissions: list[dict[str, Any]],
        job_id: str,
        tenant_id: str,  # noqa: ARG002
    ) -> GoogleDriveFileArtifact | None:
        """Create a Google Drive file artifact from metadata and content."""
        try:
            file_id = file_metadata["id"]
            file_name = file_metadata.get("name", "")

            # Extract owners
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

            # Extract last modifying user
            last_modifying_user = None
            if file_metadata.get("lastModifyingUser"):
                user_data = file_metadata["lastModifyingUser"]
                last_modifying_user = GoogleDriveFileOwner(
                    display_name=user_data.get("displayName", "Unknown"),
                    email_address=user_data.get("emailAddress"),
                    permission_id=user_data.get("permissionId"),
                    photo_link=user_data.get("photoLink"),
                )

            # Extract file extension
            file_extension = None
            if "." in file_name:
                file_extension = file_name.rsplit(".", 1)[-1].lower()

            # Determine drive info
            drive_id = file_metadata.get("driveId")
            if drive_id:
                # This is from a shared drive - we'd need to get drive name
                drive_name = f"Shared Drive {drive_id}"  # Simplified for now
            else:
                # This is from a personal drive
                drive_name = f"{owners[0].email_address}'s Drive" if owners else "Unknown Drive"

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
                    drive_id=drive_id,
                    drive_name=drive_name,
                ),
                metadata=GoogleDriveFileMetadata(
                    mime_type=file_metadata.get("mimeType", ""),
                    file_extension=file_extension,
                    parent_folder_ids=file_metadata.get("parents", []),
                    web_view_link=file_metadata.get("webViewLink"),
                    size_bytes=int(file_metadata["size"]) if file_metadata.get("size") else None,
                    permissions=permissions,
                    starred=file_metadata.get("starred", False),
                ),
            )

            # Sanitize artifact content
            self._sanitize_google_drive_artifact(artifact)

            logger.debug(f"Created artifact for Google Drive file {file_id}: {file_name}")
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
