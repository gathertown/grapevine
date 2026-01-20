"""Typed Pydantic models for Gong artifacts."""

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact


def _default_job_id() -> UUID:
    return uuid4()


class GongUserContent(BaseModel):
    id: str
    email_address: str | None = Field(default=None, alias="emailAddress")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    manager_id: str | None = Field(default=None, alias="managerId")
    first_name: str | None = Field(default=None, alias="firstName")
    last_name: str | None = Field(default=None, alias="lastName")
    active: bool | None = None

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class GongUserMetadata(BaseModel):
    workspace_id: str | None = None
    email: str | None = None


class GongUserArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.GONG_USER
    entity_id: str = Field(default="gong_user")
    ingest_job_id: UUID = Field(default_factory=_default_job_id)
    content: GongUserContent
    metadata: GongUserMetadata

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Override to handle BaseModel fields with JSON serialization."""
        # Use mode='json' to ensure datetime objects are serialized to ISO strings
        data = super().model_dump(mode="json", **kwargs)
        # Convert any BaseModel instances to dicts with JSON serialization
        if isinstance(self.content, BaseModel):
            data["content"] = self.content.model_dump(mode="json")
        if isinstance(self.metadata, BaseModel):
            data["metadata"] = self.metadata.model_dump(mode="json")
        return data


class GongPermissionProfileContent(BaseModel):
    id: str
    name: str | None = None

    model_config = ConfigDict(extra="allow")


class GongPermissionProfileMetadata(BaseModel):
    workspace_id: str | None = None


class GongPermissionProfileArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.GONG_PERMISSION_PROFILE
    entity_id: str = Field(default="gong_permission_profile")
    ingest_job_id: UUID = Field(default_factory=_default_job_id)
    content: GongPermissionProfileContent
    metadata: GongPermissionProfileMetadata

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Override to handle BaseModel fields with JSON serialization."""
        # Use mode='json' to ensure datetime objects are serialized to ISO strings
        data = super().model_dump(mode="json", **kwargs)
        # Convert any BaseModel instances to dicts with JSON serialization
        if isinstance(self.content, BaseModel):
            data["content"] = self.content.model_dump(mode="json")
        if isinstance(self.metadata, BaseModel):
            data["metadata"] = self.metadata.model_dump(mode="json")
        return data


class GongPermissionProfileUsersContent(BaseModel):
    profile_id: str
    users: list[dict[str, Any]]

    model_config = ConfigDict(extra="allow")


class GongPermissionProfileUsersMetadata(BaseModel):
    workspace_id: str | None = None


class GongPermissionProfileUsersArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.GONG_PERMISSION_PROFILE_USER
    entity_id: str = Field(default="gong_permission_profile_user")
    ingest_job_id: UUID = Field(default_factory=_default_job_id)
    content: GongPermissionProfileUsersContent
    metadata: GongPermissionProfileUsersMetadata

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Override to handle BaseModel fields with JSON serialization."""
        # Use mode='json' to ensure datetime objects are serialized to ISO strings
        data = super().model_dump(mode="json", **kwargs)
        # Convert any BaseModel instances to dicts with JSON serialization
        if isinstance(self.content, BaseModel):
            data["content"] = self.content.model_dump(mode="json")
        if isinstance(self.metadata, BaseModel):
            data["metadata"] = self.metadata.model_dump(mode="json")
        return data


class GongLibraryFolderContent(BaseModel):
    id: str
    name: str | None = None
    parent_folder_id: str | None = Field(default=None, alias="parentFolderId")

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class GongLibraryFolderMetadata(BaseModel):
    workspace_id: str | None = None
    call_ids: list[str] = Field(default_factory=list)


class GongLibraryFolderArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.GONG_LIBRARY_FOLDER
    entity_id: str = Field(default="gong_library_folder")
    ingest_job_id: UUID = Field(default_factory=_default_job_id)
    content: GongLibraryFolderContent
    metadata: GongLibraryFolderMetadata

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Override to handle BaseModel fields with JSON serialization."""
        # Use mode='json' to ensure datetime objects are serialized to ISO strings
        data = super().model_dump(mode="json", **kwargs)
        # Convert any BaseModel instances to dicts with JSON serialization
        if isinstance(self.content, BaseModel):
            data["content"] = self.content.model_dump(mode="json")
        if isinstance(self.metadata, BaseModel):
            data["metadata"] = self.metadata.model_dump(mode="json")
        return data


class GongCallMetadata(BaseModel):
    call_id: str
    workspace_id: str | None = None
    owner_user_id: str | None = None
    is_private: bool = False
    library_folder_ids: list[str] = Field(default_factory=list)
    explicit_access_user_ids: list[str] = Field(default_factory=list)
    source_created_at: str | None = None


class GongCallContent(BaseModel):
    meta_data: dict[str, Any]
    parties: list[dict[str, Any]]

    model_config = ConfigDict(extra="allow")


class GongCallArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.GONG_CALL
    entity_id: str = Field(default="gong_call")
    ingest_job_id: UUID = Field(default_factory=_default_job_id)
    content: GongCallContent
    metadata: GongCallMetadata

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Override to handle BaseModel fields with JSON serialization."""
        # Use mode='json' to ensure datetime objects are serialized to ISO strings
        data = super().model_dump(mode="json", **kwargs)
        # Convert any BaseModel instances to dicts with JSON serialization
        if isinstance(self.content, BaseModel):
            data["content"] = self.content.model_dump(mode="json")
        if isinstance(self.metadata, BaseModel):
            data["metadata"] = self.metadata.model_dump(mode="json")
        return data


class GongCallTranscriptContent(BaseModel):
    call_id: str
    transcript: list[dict[str, Any]]

    model_config = ConfigDict(extra="allow")


class GongCallTranscriptArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.GONG_CALL_TRANSCRIPT
    entity_id: str = Field(default="gong_call_transcript")
    ingest_job_id: UUID = Field(default_factory=_default_job_id)
    content: GongCallTranscriptContent
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Override to handle BaseModel fields with JSON serialization."""
        # Use mode='json' to ensure datetime objects are serialized to ISO strings
        data = super().model_dump(mode="json", **kwargs)
        # Convert any BaseModel instances to dicts with JSON serialization
        if isinstance(self.content, BaseModel):
            data["content"] = self.content.model_dump(mode="json")
        # metadata is dict, no need to check isinstance for BaseModel
        return data


class GongCallUsersAccessContent(BaseModel):
    call_id: str
    users: list[dict[str, Any]]

    model_config = ConfigDict(extra="allow")


class GongCallUsersAccessArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.GONG_CALL_USERS_ACCESS
    entity_id: str = Field(default="gong_call_users_access")
    ingest_job_id: UUID = Field(default_factory=_default_job_id)
    content: GongCallUsersAccessContent
    metadata: dict[str, Any] = Field(default_factory=dict)

    def model_dump(self, **kwargs) -> dict[str, Any]:
        """Override to handle BaseModel fields with JSON serialization."""
        # Use mode='json' to ensure datetime objects are serialized to ISO strings
        data = super().model_dump(mode="json", **kwargs)
        # Convert any BaseModel instances to dicts with JSON serialization
        if isinstance(self.content, BaseModel):
            data["content"] = self.content.model_dump(mode="json")
        # metadata is dict, no need to check isinstance for BaseModel
        return data
