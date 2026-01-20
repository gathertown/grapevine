import asyncio
import json
import uuid
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from connectors.base.utils.pdf_extractor import extract_pdf_text
from src.clients.google_drive_utils import sanitize_google_api_error
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)

GOOGLE_EXPORT_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


class GoogleDriveClient:
    def __init__(
        self, tenant_id: str, admin_email: str | None = None, ssm_client: SSMClient | None = None
    ):
        """Initialize Google Drive client with service account authentication.

        Args:
            tenant_id: Tenant identifier for credential retrieval
            admin_email: Admin email to impersonate for domain-wide delegation
            ssm_client: Optional SSM client instance for credential management
        """
        self.tenant_id = tenant_id
        self.admin_email = admin_email
        self.ssm_client = ssm_client or SSMClient()
        self._drive_service = None
        self._admin_service = None
        self._credentials: service_account.Credentials | None = None
        # Extract domain from admin email if provided
        self._domain: str | None = admin_email.split("@")[1] if admin_email else None

    async def _get_credentials(self):
        """Get service account credentials with domain-wide delegation.

        Returns:
            Service account credentials

        Raises:
            ValueError: If no credentials found or invalid
        """
        if self._credentials:
            return self._credentials

        # Get tenant-specific service account from SSM
        service_account_json = await self.ssm_client.get_google_drive_service_account(
            self.tenant_id
        )

        if not service_account_json:
            raise ValueError(
                f"No Google Drive service account found in SSM for tenant {self.tenant_id}"
            )

        logger.info(f"Using tenant-specific service account from SSM for tenant {self.tenant_id}")
        service_account_info = json.loads(service_account_json)

        # Create credentials with proper scopes
        scopes = [
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/admin.directory.user.readonly",
            "https://www.googleapis.com/auth/admin.directory.group.readonly",
        ]

        self._credentials = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=scopes
        )

        # If admin email provided, use domain-wide delegation
        if self.admin_email and self._credentials:
            self._credentials = self._credentials.with_subject(self.admin_email)

        return self._credentials

    async def _get_drive_service(self):
        """Get or create Google Drive API service.

        Returns:
            Google Drive API service instance
        """
        if not self._drive_service:
            credentials = await self._get_credentials()
            self._drive_service = build("drive", "v3", credentials=credentials)
        return self._drive_service

    async def _get_admin_service(self):
        """Get or create Google Admin SDK service.

        Returns:
            Google Admin SDK service instance
        """
        if not self._admin_service:
            if not self.admin_email:
                raise ValueError("Admin email required for Admin SDK operations")
            credentials = await self._get_credentials()
            self._admin_service = build("admin", "directory_v1", credentials=credentials)
        return self._admin_service

    async def list_users(self, max_results: int = 500) -> list[dict[str, Any]]:
        """List all users in the Google Workspace domain.

        Args:
            max_results: Maximum number of users per page

        Returns:
            List of user dictionaries
        """
        admin_service = await self._get_admin_service()
        all_users = []
        page_token = None

        try:
            while True:
                request = admin_service.users().list(
                    domain=self._domain,
                    maxResults=max_results,
                    pageToken=page_token,
                    orderBy="email",
                )
                results = request.execute()

                users = results.get("users", [])
                all_users.extend(users)

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            logger.info(f"Found {len(all_users)} users in domain {self._domain}")
            return all_users

        except HttpError as e:
            logger.error(
                f"Failed to list users: {sanitize_google_api_error(e)}",
                domain=self._domain,
                error_raw=str(e),
            )
            raise

    async def list_shared_drives(self, page_size: int = 100) -> list[dict[str, Any]]:
        """List all shared drives accessible to the service account.

        Args:
            page_size: Number of drives per page

        Returns:
            List of shared drive dictionaries
        """
        drive_service = await self._get_drive_service()
        all_drives = []
        page_token = None

        try:
            while True:
                request = drive_service.drives().list(
                    pageSize=page_size,
                    pageToken=page_token,
                    fields="nextPageToken, drives(id, name, createdTime)",
                )
                results = request.execute()

                drives = results.get("drives", [])
                all_drives.extend(drives)

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            logger.info(f"Found {len(all_drives)} shared drives")
            return all_drives

        except HttpError as e:
            logger.error(
                f"Failed to list shared drives: {sanitize_google_api_error(e)}", error_raw=str(e)
            )
            raise

    async def list_files(
        self,
        query: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
        include_team_drives: bool = True,
        include_permissions: bool = False,
        drive_id: str | None = None,
    ) -> dict[str, Any]:
        """List files from Google Drive.

        Args:
            query: Optional query string to filter files
            page_size: Number of files to return per page
            page_token: Token for pagination
            include_team_drives: Whether to include shared/team drives
            include_permissions: Whether to include permissions in response
            drive_id: Optional specific drive ID to search in

        Returns:
            Dict containing files list and nextPageToken
        """
        drive_service = await self._get_drive_service()

        # Build fields parameter
        fields = "nextPageToken, files(id, name, mimeType, modifiedTime, createdTime, "
        fields += "size, parents, owners, lastModifyingUser, description, starred, "
        fields += "webViewLink, driveId"

        # Add permissions and hasAugmentedPermissions for shared drives
        if include_permissions:
            fields += ", permissions"
        fields += ", hasAugmentedPermissions"

        fields += ")"

        params = {
            "pageSize": page_size,
            "fields": fields,
            "supportsAllDrives": include_team_drives,
            "includeItemsFromAllDrives": include_team_drives,
        }

        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token
        if drive_id:
            params["driveId"] = drive_id
            params["corpora"] = "drive"

        try:
            request = drive_service.files().list(**params)
            return request.execute()
        except HttpError as e:
            logger.error(
                f"Failed to list files: {sanitize_google_api_error(e)}",
                query=query,
                drive_id=drive_id,
                error_raw=str(e),
            )
            raise

    async def get_file_permissions(self, file_id: str) -> list[dict[str, Any]]:
        """Get permissions for a specific file.

        Args:
            file_id: Google Drive file ID

        Returns:
            List of permission dictionaries
        """
        drive_service = await self._get_drive_service()

        try:
            request = drive_service.permissions().list(
                fileId=file_id,
                supportsAllDrives=True,
                fields="permissions(id, type, domain, role, emailAddress, displayName)",
            )
            results = request.execute()
            return results.get("permissions", [])
        except HttpError as e:
            logger.error(
                f"Failed to get permissions: {sanitize_google_api_error(e)}",
                file_id=file_id,
                error_raw=str(e),
            )
            return []

    async def get_file_permissions_batch(
        self, file_ids: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Get permissions for multiple files concurrently.

        Args:
            file_ids: List of Google Drive file IDs

        Returns:
            Dict mapping file IDs to their permissions
        """
        tasks = [self.get_file_permissions(file_id) for file_id in file_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        permissions_map: dict[str, list[dict[str, Any]]] = {}
        for file_id, result in zip(file_ids, results, strict=True):
            if isinstance(result, Exception):
                logger.error(f"Failed to get permissions for {file_id}: {result}")
                permissions_map[file_id] = []
            else:
                permissions_map[file_id] = result  # type: ignore[assignment]

        return permissions_map

    def is_domain_accessible(self, permissions: list[dict[str, Any]]) -> bool:
        """Check if file has domain-wide read access.

        Args:
            permissions: List of permission dictionaries

        Returns:
            True if file is accessible to the domain
        """
        if not self._domain:
            return False

        for permission in permissions:
            if (
                permission.get("type") == "domain"
                and permission.get("domain") == self._domain
                and permission.get("role") in ["reader", "commenter", "writer", "owner"]
            ):
                return True
        return False

    async def get_file_metadata(self, file_id: str) -> dict[str, Any]:
        """Get metadata for a specific file.

        Args:
            file_id: Google Drive file ID

        Returns:
            File metadata dict
        """
        drive_service = await self._get_drive_service()

        try:
            request = drive_service.files().get(
                fileId=file_id,
                fields="id, name, mimeType, modifiedTime, createdTime, size, parents, "
                "owners, lastModifyingUser, description, starred, webViewLink, "
                "driveId, permissions, hasAugmentedPermissions",
                supportsAllDrives=True,
            )
            return request.execute()
        except HttpError as e:
            logger.error(
                f"Failed to get file metadata: {sanitize_google_api_error(e)}",
                file_id=file_id,
                error_raw=str(e),
            )
            raise

    async def get_file_content(
        self, file_id: str, mime_type: str, _file_metadata: dict[str, Any] | None = None
    ) -> str:
        """Get the text content of a file or metadata header for unsupported types.

        Args:
            file_id: Google Drive file ID
            mime_type: MIME type of the file
            file_metadata: Optional file metadata to include in header for unsupported types

        Returns:
            File content as text or metadata header
        """
        drive_service = await self._get_drive_service()

        try:
            if mime_type in GOOGLE_EXPORT_MIME_TYPES:
                return await self._export_google_workspace_file(drive_service, file_id, mime_type)
            elif mime_type and mime_type.startswith("text/"):
                return await self._extract_text_file(drive_service, file_id)
            elif mime_type == "application/pdf":
                return await self._extract_pdf_text(drive_service, file_id)
            else:
                return ""

        except HttpError as e:
            logger.error(
                f"Failed to get file content: {sanitize_google_api_error(e)}",
                file_id=file_id,
                mime_type=mime_type,
                error_raw=str(e),
            )
            return ""

    async def _export_google_workspace_file(
        self, drive_service: Any, file_id: str, mime_type: str
    ) -> str:
        """Export a Google Workspace file as text.

        Args:
            drive_service: Google Drive service instance
            file_id: Google Drive file ID
            mime_type: MIME type of the Google Workspace file

        Returns:
            Exported text content
        """
        export_mime_type = GOOGLE_EXPORT_MIME_TYPES[mime_type]
        request = drive_service.files().export(fileId=file_id, mimeType=export_mime_type)
        return request.execute()

    async def _extract_text_file(self, drive_service: Any, file_id: str) -> str:
        """Extract content from a text file.

        Args:
            drive_service: Google Drive service instance
            file_id: Google Drive file ID

        Returns:
            Text content of the file
        """
        request = drive_service.files().get_media(fileId=file_id)
        content = request.execute()
        if isinstance(content, bytes):
            return content.decode("utf-8", errors="ignore")
        return content

    async def _extract_pdf_text(self, drive_service: Any, file_id: str) -> str:
        """Extract text content from a PDF file.

        Args:
            drive_service: Google Drive service instance
            file_id: ID of the PDF file

        Returns:
            Extracted text content or empty string if extraction fails
        """
        try:
            # Download the PDF bytes
            request = drive_service.files().get_media(fileId=file_id)
            pdf_bytes = request.execute()

            # Use the centralized PDF extractor
            return extract_pdf_text(pdf_bytes, source_identifier=f"Google Drive file {file_id}")

        except HttpError as e:
            logger.error(
                f"Failed to download PDF: {sanitize_google_api_error(e)}",
                file_id=file_id,
                error_raw=str(e),
            )
            return ""
        except Exception as e:
            logger.error(f"Failed to extract PDF text: {e}", file_id=file_id, error_raw=str(e))
            return ""

    async def list_files_in_folder(
        self, folder_id: str, recursive: bool = False
    ) -> list[dict[str, Any]]:
        """List all files in a folder.

        Args:
            folder_id: Google Drive folder ID
            recursive: Whether to recursively list files in subfolders

        Returns:
            List of file metadata dicts
        """
        all_files = []
        folders_to_process = [folder_id]
        processed_folders = set()

        logger.info(f"Starting list_files_in_folder for folder {folder_id}, recursive={recursive}")

        while folders_to_process:
            current_folder = folders_to_process.pop(0)
            if current_folder in processed_folders:
                continue
            processed_folders.add(current_folder)

            query = f"'{current_folder}' in parents and trashed = false"
            page_token = None

            while True:
                result = await self.list_files(query=query, page_token=page_token)
                files = result.get("files", [])

                for file in files:
                    all_files.append(file)
                    if recursive and file.get("mimeType") == "application/vnd.google-apps.folder":
                        folders_to_process.append(file["id"])

                page_token = result.get("nextPageToken")
                if not page_token:
                    break

        logger.info(f"Finished processing folder {folder_id}, found {len(all_files)} total items")
        return all_files

    async def impersonate_user(self, user_email: str) -> "GoogleDriveClient":
        """Create a new client instance that impersonates a specific user.

        Args:
            user_email: Email of the user to impersonate

        Returns:
            New GoogleDriveClient instance with user impersonation
        """
        return GoogleDriveClient(
            tenant_id=self.tenant_id, admin_email=user_email, ssm_client=self.ssm_client
        )

    async def create_watch_channel(
        self,
        resource_uri: str,
        webhook_url: str,
        token: str | None = None,
        expiration: int | None = None,
    ) -> dict[str, Any]:
        """Create a push notification channel to watch for changes.

        Args:
            resource_uri: The resource to watch (e.g., 'files' or specific file ID)
            webhook_url: HTTPS URL to receive notifications (format: https://{tenant_id}.your-gatekeeper.com/webhooks/google-drive)
            token: Optional token for webhook verification
            expiration: Optional expiration time in milliseconds since epoch

        Returns:
            Channel information including ID and expiration

        Raises:
            HttpError: If channel creation fails
        """
        drive_service = await self._get_drive_service()

        # Generate unique channel ID
        channel_id = str(uuid.uuid4())

        # Prepare channel configuration
        channel_config = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
        }

        if token:
            channel_config["token"] = token

        if expiration:
            channel_config["expiration"] = str(expiration)

        try:
            # Create the watch channel
            if resource_uri == "files":
                # Watch for changes to files across the drive
                request = drive_service.files().watch(body=channel_config)
            else:
                # Watch for changes to a specific file
                request = drive_service.files().watch(fileId=resource_uri, body=channel_config)

            result = request.execute()
            logger.info(f"Created Google Drive watch channel {channel_id} for {resource_uri}")
            return result

        except HttpError as e:
            logger.error(
                f"Failed to create watch channel: {sanitize_google_api_error(e)}",
                resource_uri=resource_uri,
                webhook_url=webhook_url,
                error_raw=str(e),
            )
            raise

    async def stop_watch_channel(self, channel_id: str, resource_id: str) -> bool:
        """Stop a push notification channel.

        Args:
            channel_id: ID of the channel to stop
            resource_id: Resource ID returned when the channel was created

        Returns:
            True if channel was stopped successfully, False otherwise
        """
        drive_service = await self._get_drive_service()

        try:
            # Stop the channel
            request = drive_service.channels().stop(
                body={"id": channel_id, "resourceId": resource_id}
            )
            request.execute()
            logger.info(f"Stopped Google Drive watch channel {channel_id}")
            return True

        except HttpError as e:
            logger.error(
                f"Failed to stop watch channel: {sanitize_google_api_error(e)}",
                channel_id=channel_id,
                resource_id=resource_id,
                error_raw=str(e),
            )
            return False

    async def list_watch_channels(self) -> list[dict[str, Any]]:
        """List active push notification channels.

        Note: Google Drive API doesn't provide a direct method to list channels.
        This would typically require storing channel information externally.

        Returns:
            Empty list (placeholder for external channel tracking)
        """
        logger.warning("Google Drive API doesn't support listing channels directly")
        return []

    async def refresh_watch_channel(
        self,
        old_channel_id: str,
        old_resource_id: str,
        resource_uri: str,
        webhook_url: str,
        token: str | None = None,
        expiration: int | None = None,
    ) -> dict[str, Any] | None:
        """Refresh an expiring watch channel by creating a new one and stopping the old one.

        Args:
            old_channel_id: ID of the expiring channel
            old_resource_id: Resource ID of the expiring channel
            resource_uri: The resource to watch
            webhook_url: HTTPS URL to receive notifications (format: https://{tenant_id}.your-gatekeeper.com/webhooks/google-drive)
            token: Optional token for webhook verification
            expiration: Optional expiration time in milliseconds since epoch

        Returns:
            New channel information or None if refresh failed
        """
        try:
            # Create new channel first
            new_channel = await self.create_watch_channel(
                resource_uri=resource_uri,
                webhook_url=webhook_url,
                token=token,
                expiration=expiration,
            )

            # Stop the old channel
            await self.stop_watch_channel(old_channel_id, old_resource_id)

            logger.info(
                f"Refreshed Google Drive watch channel from {old_channel_id} to {new_channel['id']}"
            )
            return new_channel

        except HttpError as e:
            logger.error(
                f"Failed to refresh watch channel: {sanitize_google_api_error(e)}",
                old_channel_id=old_channel_id,
                resource_uri=resource_uri,
                error_raw=str(e),
            )
            return None
        except Exception as e:
            logger.error(
                f"Failed to refresh watch channel: {e}",
                old_channel_id=old_channel_id,
                resource_uri=resource_uri,
                error_raw=str(e),
            )
            return None

    async def get_start_page_token(self, drive_id: str | None = None) -> str:
        """Get start page token for changes API.

        Args:
            drive_id: Optional drive ID for shared drive, None for user drive

        Returns:
            Start page token for changes tracking

        Raises:
            HttpError: If API call fails
        """
        drive_service = await self._get_drive_service()

        try:
            if drive_id:
                request = drive_service.changes().getStartPageToken(
                    driveId=drive_id, supportsAllDrives=True
                )
            else:
                request = drive_service.changes().getStartPageToken()

            result = request.execute()
            return result["startPageToken"]

        except HttpError as e:
            logger.error(
                f"Failed to get start page token: {sanitize_google_api_error(e)}",
                drive_id=drive_id,
                error_raw=str(e),
            )
            raise

    async def watch_changes(
        self,
        page_token: str,
        webhook_url: str,
        drive_id: str | None = None,
        restrict_to_my_drive: bool = False,
        token: str | None = None,
        expiration: int | None = None,
    ) -> dict[str, Any]:
        """Watch for changes using changes API.

        Args:
            page_token: Page token to start watching from
            webhook_url: HTTPS URL to receive notifications
            drive_id: Optional drive ID for shared drive
            restrict_to_my_drive: If True, restricts to user's My Drive only
            token: Optional token for webhook verification
            expiration: Optional expiration time in milliseconds since epoch

        Returns:
            Channel information including ID and expiration

        Raises:
            HttpError: If channel creation fails
        """
        drive_service = await self._get_drive_service()

        # Generate unique channel ID
        channel_id = str(uuid.uuid4())

        # Prepare channel configuration
        channel_config = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
        }

        if token:
            channel_config["token"] = token

        if expiration:
            channel_config["expiration"] = str(expiration)

        try:
            # Create the watch channel with appropriate parameters
            if drive_id:
                request = drive_service.changes().watch(
                    pageToken=page_token,
                    body=channel_config,
                    driveId=drive_id,
                    supportsAllDrives=True,
                )
            elif restrict_to_my_drive:
                request = drive_service.changes().watch(
                    pageToken=page_token,
                    body=channel_config,
                    restrictToMyDrive=True,
                )
            else:
                request = drive_service.changes().watch(
                    pageToken=page_token,
                    body=channel_config,
                )

            result = request.execute()

            logger.info(
                f"Created Google Drive changes watch channel {channel_id} for {'shared drive ' + drive_id if drive_id else 'user drive'}"
            )
            return result

        except HttpError as e:
            logger.error(
                f"Failed to create changes watch channel: {sanitize_google_api_error(e)}",
                page_token=page_token,
                drive_id=drive_id,
                webhook_url=webhook_url,
                error_raw=str(e),
            )
            raise

    async def list_changes(
        self,
        page_token: str,
        drive_id: str | None = None,
        restrict_to_my_drive: bool = False,
        page_size: int = 1000,
    ) -> dict[str, Any]:
        """List changes from the changes API.

        Args:
            page_token: Page token to start listing from
            drive_id: Optional drive ID for shared drive
            restrict_to_my_drive: If True, restricts to user's My Drive only
            page_size: Number of changes per page

        Returns:
            Changes response with changes list and tokens

        Raises:
            HttpError: If API call fails
        """
        drive_service = await self._get_drive_service()

        try:
            # Prepare fields parameter
            fields = "nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,modifiedTime,driveId),time)"

            # Create request with appropriate parameters
            if drive_id:
                request = drive_service.changes().list(
                    pageToken=page_token,
                    pageSize=page_size,
                    fields=fields,
                    driveId=drive_id,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
            elif restrict_to_my_drive:
                request = drive_service.changes().list(
                    pageToken=page_token,
                    pageSize=page_size,
                    fields=fields,
                    restrictToMyDrive=True,
                )
            else:
                request = drive_service.changes().list(
                    pageToken=page_token,
                    pageSize=page_size,
                    fields=fields,
                )

            return request.execute()

        except HttpError as e:
            logger.error(
                f"Failed to list changes: {sanitize_google_api_error(e)}",
                page_token=page_token,
                drive_id=drive_id,
                error_raw=str(e),
            )
            raise
