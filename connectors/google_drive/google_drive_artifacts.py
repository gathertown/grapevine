"""Models for Google Drive processing in the ingest pipeline."""

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


class GoogleDriveFileOwner(BaseModel):
    """Owner information for a Google Drive file."""

    display_name: str
    email_address: str | None = None
    permission_id: str | None = None
    photo_link: str | None = None


class GoogleDriveFileMetadata(BaseModel):
    """Metadata for Google Drive file artifacts."""

    mime_type: str
    file_extension: str | None = None
    parent_folder_ids: list[str] = []
    web_view_link: str | None = None
    size_bytes: int | None = None
    starred: bool = False
    permissions: list[dict] = []


class GoogleDriveFileContent(BaseModel):
    """Content model for Google Drive file artifacts."""

    file_id: str
    name: str
    content: str
    description: str | None = None
    source_created_at: str | None = None
    source_modified_at: str | None = None
    owners: list[GoogleDriveFileOwner] = []
    last_modifying_user: GoogleDriveFileOwner | None = None
    drive_id: str | None = None  # For shared drives
    drive_name: str | None = None


class GoogleDriveFileArtifact(BaseIngestArtifact):
    """Artifact model for Google Drive file data."""

    entity: ArtifactEntity = ArtifactEntity.GOOGLE_DRIVE_FILE
    content: GoogleDriveFileContent
    metadata: GoogleDriveFileMetadata


class GoogleDriveUserContent(BaseModel):
    """Content model for Google Drive user artifacts."""

    user_id: str
    email: str
    full_name: str
    given_name: str | None = None
    family_name: str | None = None
    is_admin: bool = False
    is_suspended: bool = False
    org_unit_path: str | None = None
    creation_time: str | None = None
    last_login_time: str | None = None


class GoogleDriveUserMetadata(BaseModel):
    """Metadata for Google Drive user artifacts."""

    primary_email: str
    aliases: list[str] = []
    photo_url: str | None = None


class GoogleDriveUserArtifact(BaseIngestArtifact):
    """Artifact model for Google Workspace user data."""

    entity: ArtifactEntity = ArtifactEntity.GOOGLE_DRIVE_USER
    content: GoogleDriveUserContent
    metadata: GoogleDriveUserMetadata


class GoogleDriveSharedDriveContent(BaseModel):
    """Content model for Google Drive shared drive artifacts."""

    drive_id: str
    name: str
    created_time: str | None = None


class GoogleDriveSharedDriveMetadata(BaseModel):
    """Metadata for Google Drive shared drive artifacts."""

    color_rgb: str | None = None
    background_image_link: str | None = None
    capabilities: dict | None = None


class GoogleDriveSharedDriveArtifact(BaseIngestArtifact):
    """Artifact model for Google Drive shared drive data."""

    entity: ArtifactEntity = ArtifactEntity.GOOGLE_DRIVE_SHARED_DRIVE
    content: GoogleDriveSharedDriveContent
    metadata: GoogleDriveSharedDriveMetadata
