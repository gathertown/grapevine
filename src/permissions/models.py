from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

PermissionPolicy = Literal["tenant", "private"]
PermissionAudience = Literal["tenant", "private"]


class DocumentPermissions(BaseModel):
    id: UUID | None = None
    document_id: str
    permission_policy: PermissionPolicy = Field(default="private")
    permission_allowed_tokens: list[str] | None = Field(default=None)

    class Config:
        from_attributes = True
