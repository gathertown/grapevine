from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base.base_chunk import BaseChunk
from connectors.base.base_document import BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.clickup.client.clickup_api_models import ClickupUser
from connectors.clickup.extractors.artifacts.clickup_comment_artifact import ClickupCommentArtifact
from connectors.clickup.extractors.artifacts.clickup_list_artifact import ClickupListArtifact
from connectors.clickup.extractors.artifacts.clickup_task_artifact import ClickupTaskArtifact
from connectors.clickup.extractors.artifacts.clickup_workspace_artifact import (
    ClickupWorkspaceArtifact,
)
from src.permissions.models import PermissionPolicy
from src.permissions.utils import make_email_permission_token


class ClickupChunkMetadata(TypedDict):
    chunk_index: int
    total_chunks: int
    task_id: str


class ClickupChunkRawData(TypedDict):
    content: str
    chunk_index: int
    total_chunks: int
    task_id: str


class ClickupTaskChunk(BaseChunk[ClickupChunkMetadata]):
    raw_data: ClickupChunkRawData

    def get_content(self) -> str:
        content = self.raw_data["content"]
        chunk_index = self.raw_data["chunk_index"]
        total_chunks = self.raw_data["total_chunks"]

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> ClickupChunkMetadata:
        return ClickupChunkMetadata(
            task_id=self.raw_data["task_id"],
            chunk_index=self.raw_data["chunk_index"],
            total_chunks=self.raw_data["total_chunks"],
        )


class ClickupTaskDocumentMetadata(TypedDict):
    task_id: str
    task_name: str
    task_url: str

    workspace_id: str
    workspace_name: str
    space_id: str
    folder_id: str
    folder_name: str
    list_id: str
    list_name: str

    # epoch milliseconds
    date_created: str
    # epoch milliseconds
    date_updated: str
    # epoch milliseconds
    date_closed: str | None
    # epoch milliseconds
    date_done: str | None


@dataclass
class ClickupTaskDocument(BaseDocument[ClickupTaskChunk, ClickupTaskDocumentMetadata]):
    task_artifact: ClickupTaskArtifact
    comment_artifacts: list[ClickupCommentArtifact]

    def to_embedding_chunks(self) -> list[ClickupTaskChunk]:
        full_content = self.get_content()

        if not full_content.strip():
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        text_chunks = text_splitter.split_text(full_content)

        return [
            ClickupTaskChunk(
                document=self,
                raw_data=ClickupChunkRawData(
                    content=chunk_text,
                    chunk_index=i,
                    total_chunks=len(text_chunks),
                    task_id=self.task_artifact.metadata.task_id,
                ),
            )
            for i, chunk_text in enumerate(text_chunks)
        ]

    def get_content(self) -> str:
        header_content = self._get_header_content()
        description_content = self.task_artifact.content.markdown_description
        comments_content = self._get_comments_content()
        return header_content + "\n\n" + description_content + "\n\n" + comments_content

    def _get_header_content(self) -> str:
        header_lines = [
            f"Task: {self._format_named(self.task_artifact.metadata.task_id, self.task_artifact.metadata.task_name)}",
            f"Task URL: {self.task_artifact.content.url}",
            f"Task Status: {self.task_artifact.content.status.status}",
            f"Task Priority: {self.task_artifact.content.priority.priority if self.task_artifact.content.priority else ''}",
            f"Is Public: {'Yes' if self.task_artifact.content.sharing.public else 'No'}",
            "",
            f"Workspace: {self._format_named(self.task_artifact.metadata.workspace_id, self.task_artifact.metadata.workspace_name)}",
            f"Space ID: {self.task_artifact.content.space.id}",
            f"Folder: {self._format_named(self.task_artifact.metadata.folder_id, self.task_artifact.metadata.folder_name)}",
            f"List: {self._format_named(self.task_artifact.metadata.list_id, self.task_artifact.metadata.list_name)}",
            f"Parent Task ID: {self.task_artifact.content.parent or ''}",
            "",
            f"Creator: {self._format_user(self.task_artifact.content.creator)}",
            f"Assignees: {', '.join([self._format_user(assignee) for assignee in self.task_artifact.content.assignees])}",
            f"Watchers: {', '.join([self._format_user(watcher) for watcher in self.task_artifact.content.watchers])}",
            f"Tags: {', '.join([tag.name for tag in self.task_artifact.content.tags])}",
            "",
            f"Created At: {self.task_artifact.metadata.date_created}",
            f"Updated At: {self.task_artifact.metadata.date_updated}",
            f"Closed At: {self.task_artifact.metadata.date_closed or ''}",
            f"Done At: {self.task_artifact.metadata.date_done or ''}",
        ]

        return "\n".join(header_lines)

    def _get_comments_content(self) -> str:
        if not self.comment_artifacts:
            return ""

        comment_lines = ["Comments:"]

        for comment_artifact in self.comment_artifacts:
            if comment_artifact.metadata.parent_comment_id:
                continue

            author = self._format_user(comment_artifact.content.user)
            date_created_ms = int(comment_artifact.content.date)
            date_created_s = date_created_ms / 1000.0
            date_created = datetime.fromtimestamp(date_created_s, UTC).isoformat()
            reaction_count = len(comment_artifact.content.reactions)
            comment_lines.append(
                f"- Comment by {author} at {date_created} ({reaction_count} reactions):"
            )
            comment_lines.append(comment_artifact.content.comment_text)
            comment_lines.append("")

            replies = [
                ca
                for ca in self.comment_artifacts
                if ca.metadata.parent_comment_id == comment_artifact.metadata.comment_id
            ]
            for reply in replies:
                reply_author = self._format_user(reply.content.user)
                reply_date_created_ms = int(reply.content.date)
                reply_date_created_s = reply_date_created_ms / 1000.0
                reply_date_created = datetime.fromtimestamp(reply_date_created_s, UTC).isoformat()
                reply_reaction_count = len(reply.content.reactions)
                comment_lines.append(
                    f"  - Reply by {reply_author} at {reply_date_created} ({reply_reaction_count} reactions):"
                )
                comment_lines.append(f"  {reply.content.comment_text}")
                comment_lines.append("")

        return "\n".join(comment_lines)

    def _format_user(self, user: ClickupUser | None) -> str:
        if not user:
            return ""

        name_likely_email = user.username and "@" in user.username

        name: str | None = None
        if user.username:
            name_likely_email = "@" in user.username
            name = user.username if name_likely_email else "@" + user.username

        email = user.email
        id = f"@{str(user.id)}"

        parts: list[str | None] = [name, email, id]
        defined_parts = [part for part in parts if part]

        return f"<{'|'.join(defined_parts)}>"

    def _format_named(self, id: str, name: str) -> str:
        return f"<{name}|@{id}>"

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.CLICKUP_TASK

    def get_reference_id(self) -> str:
        return clickup_task_reference_id(self.task_artifact.metadata.task_id)

    def get_metadata(self) -> ClickupTaskDocumentMetadata:
        return {
            "task_id": self.task_artifact.metadata.task_id,
            "task_name": self.task_artifact.metadata.task_name,
            "task_url": self.task_artifact.content.url,
            "workspace_id": self.task_artifact.metadata.workspace_id,
            "workspace_name": self.task_artifact.metadata.workspace_name,
            "space_id": self.task_artifact.metadata.space_id,
            "folder_id": self.task_artifact.metadata.folder_id,
            "folder_name": self.task_artifact.metadata.folder_name,
            "list_id": self.task_artifact.metadata.list_id,
            "list_name": self.task_artifact.metadata.list_name,
            "date_created": self.task_artifact.metadata.date_created,
            "date_updated": self.task_artifact.metadata.date_updated,
            "date_closed": self.task_artifact.metadata.date_closed,
            "date_done": self.task_artifact.metadata.date_done,
        }

    def get_source_created_at(self) -> datetime:
        date_created_ms = int(self.task_artifact.metadata.date_created)
        date_created_s = date_created_ms / 1000.0
        return datetime.fromtimestamp(date_created_s, UTC)

    @classmethod
    def from_artifacts(
        cls,
        task_artifact: ClickupTaskArtifact,
        comment_artifacts: list[ClickupCommentArtifact],
        workspace_artifact: ClickupWorkspaceArtifact,
        list_artifact: ClickupListArtifact,
    ) -> "ClickupTaskDocument":
        list_user_ids = {user.id for user in list_artifact.content.members}
        workspace_user_ids = {member.user.id for member in workspace_artifact.content.members}

        is_public = task_artifact.content.sharing.public == True or list_user_ids.issuperset(
            workspace_user_ids
        )

        permission_policy: PermissionPolicy = "tenant" if is_public else "private"
        permission_allowed_tokens: list[str] | None = None
        if not is_public:
            allowed_emails = {user.email for user in list_artifact.content.members}
            permission_allowed_tokens = [
                make_email_permission_token(email) for email in allowed_emails
            ]

        return ClickupTaskDocument(
            id=clickup_task_document_id(task_artifact.metadata.task_id),
            task_artifact=task_artifact,
            comment_artifacts=comment_artifacts,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
            source_updated_at=task_artifact.source_updated_at,
        )


def clickup_task_reference_id(task_id: str) -> str:
    return f"r_clickup_task_{task_id}"


def clickup_task_document_id(task_id: str) -> str:
    return f"clickup_task_{task_id}"
