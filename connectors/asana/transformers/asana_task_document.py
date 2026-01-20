from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.asana.client.asana_api_models import AsanaNamedResouce, AsanaUser
from connectors.asana.extractors.artifacts.asana_project_artifact import (
    AsanaProjectPermissionsArtifact,
)
from connectors.asana.extractors.artifacts.asana_story_artifact import AsanaStoryArtifact
from connectors.asana.extractors.artifacts.asana_task_artifact import AsanaTaskArtifact
from connectors.base.base_chunk import BaseChunk
from connectors.base.base_document import BaseDocument
from connectors.base.document_source import DocumentSource
from src.permissions.models import PermissionPolicy
from src.permissions.utils import make_email_permission_token


class AsanaChunkMetadata(TypedDict):
    chunk_index: int
    total_chunks: int
    task_gid: str


class AsanaChunkRawData(TypedDict):
    content: str
    chunk_index: int
    total_chunks: int
    task_gid: str


class AsanaTaskChunk(BaseChunk[AsanaChunkMetadata]):
    raw_data: AsanaChunkRawData

    def get_content(self) -> str:
        content = self.raw_data["content"]
        chunk_index = self.raw_data["chunk_index"]
        total_chunks = self.raw_data["total_chunks"]

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> AsanaChunkMetadata:
        return AsanaChunkMetadata(
            task_gid=self.raw_data["task_gid"],
            chunk_index=self.raw_data["chunk_index"],
            total_chunks=self.raw_data["total_chunks"],
        )


class AsanaTaskDocumentMetadata(TypedDict):
    task_gid: str
    task_name: str
    permalink_url: str
    project_gids: list[str]
    section_gids: list[str]
    workspace_gid: str
    workspace_name: str

    created_at: str
    modified_at: str
    due_on: str | None
    start_on: str | None

    assignee_gid: str | None
    assignee_name: str | None


@dataclass
class AsanaTaskDocument(BaseDocument[AsanaTaskChunk, AsanaTaskDocumentMetadata]):
    task_artifact: AsanaTaskArtifact
    story_artifacts: list[AsanaStoryArtifact]

    def to_embedding_chunks(self) -> list[AsanaTaskChunk]:
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
            AsanaTaskChunk(
                document=self,
                raw_data=AsanaChunkRawData(
                    content=chunk_text,
                    chunk_index=i,
                    total_chunks=len(text_chunks),
                    task_gid=self.task_artifact.metadata.task_gid,
                ),
            )
            for i, chunk_text in enumerate(text_chunks)
        ]

    def get_content(self) -> str:
        header_content = self._get_header_content()
        description_content = self.task_artifact.content.task.notes or "No description provided."
        stories_content = self._get_stories_content()
        comments_content = self._get_comments_content()

        return f"{header_content}\n\n## Task Description\n{description_content}\n\n## Stories:\n{stories_content}\n\n## Comments:\n{comments_content}"

    def _get_named_content(self, named: AsanaNamedResouce | None) -> str:
        if not named:
            return ""
        parts: list[str] = [named.name, named.gid]
        defined_parts = [f"@{part}" for part in parts]
        return f"<{'|'.join(defined_parts)}>"

    def _get_user_content(self, user: AsanaUser | None) -> str:
        if not user:
            return ""

        name_likely_email = "@" in user.name
        name = user.name if name_likely_email else f"@{user.name}"
        email = user.email
        id = f"@{str(user.gid)}"

        return f"<{'|'.join([name, email, id])}>"

    def _get_header_content(self) -> str:
        task = self.task_artifact.content.task

        people_custom_fields_lines: list[str] = [
            f"- {field.name}: "
            + ", ".join([self._get_user_content(person) for person in field.people_value])
            for field in task.custom_fields
            if field.people_value is not None
        ]

        referenced_customed_field_lines = [
            f"- {field.name}: "
            + ", ".join([self._get_named_content(ref) for ref in field.reference_value])
            for field in task.custom_fields
            if field.reference_value is not None
        ]

        other_custom_field_lines = [
            f"- {field.name}: {field.display_value or ''}"
            for field in task.custom_fields
            if field.people_value is None and field.reference_value is None
        ]

        header_lines = [
            "# Asana Task",
            f"- Task: {self._get_named_content(task)}",
            f"- Parent Task: {self._get_named_content(task.parent)}",
            f"- Sections: {', '.join([self._get_named_content(membership.section) for membership in task.memberships])}",
            f"- Projects: {', '.join([self._get_named_content(membership.project) for membership in task.memberships])}",
            f"- Workspace: {self._get_named_content(self.task_artifact.content.workspace)}",
            f"- Tags: {', '.join([self._get_named_content(tag) for tag in task.tags])}",
            f"- Subtype: {task.resource_subtype}",
            f"- Approval Status: {task.approval_status}",
            f"- Due On: {task.due_on}",
            f"- Start On: {task.start_on}",
            f"- Completed At: {task.completed_at}",
            f"- Likes: {task.num_likes}",
            f"- Subtasks: {task.num_subtasks}",
            f"- Logged Time Minutes: {task.actual_time_minutes}",
            f"- Permalink: {task.permalink_url}",
            f"- Created At: {task.created_at}",
            f"- Modified At: {task.modified_at}",
            "## People involved",
            f"- Assignee: {self._get_user_content(task.assignee)}",
            f"- Collaborators: {', '.join([self._get_user_content(follower) for follower in task.followers])}",
            f"- Created By: {self._get_user_content(task.created_by)}",
            f"- Completed By: {self._get_user_content(task.completed_by)}",
            *people_custom_fields_lines,
            "## Additional Details",
            *referenced_customed_field_lines,
            *other_custom_field_lines,
        ]
        return "\n".join(header_lines)

    def _get_comments_content(self) -> str:
        # Most recent first
        comment_stories = [sa for sa in self.story_artifacts if sa.content.type == "comment"]
        sorted_comments = sorted(
            comment_stories, key=lambda sa: sa.content.created_at, reverse=True
        )

        comment_texts: list[str] = [
            "\n".join(
                [
                    "### Comment",
                    sa.content.text or "",
                    f"- Author: {self._get_user_content(sa.content.created_by)}",
                    f"- Timestamp: {sa.content.created_at}",
                    f"- Likes: {sa.content.num_likes or 0}",
                ]
            )
            for sa in sorted_comments
        ]

        return "\n\n".join(comment_texts)

    def _get_stories_content(self) -> str:
        # Most recent first
        non_comment_stories = [sa for sa in self.story_artifacts if sa.content.type != "comment"]
        sorted_stories = sorted(
            non_comment_stories, key=lambda sa: sa.content.created_at, reverse=True
        )

        story_texts: list[str] = [
            "\n".join(
                [
                    "### Update",
                    self._get_story_content(sa),
                    f"- Performed By: {self._get_user_content(sa.content.created_by)}",
                    f"- Performed At: {sa.content.created_at}",
                ]
            )
            for sa in sorted_stories
        ]

        return "\n\n".join(story_texts)

    def _get_story_content(self, story: AsanaStoryArtifact) -> str:
        match story.content.resource_subtype:
            case "assigned":
                return f"{self._get_user_content(story.content.created_by)} assigned this task to {self._get_user_content(story.content.assignee)}."
            case "collaborator_added":
                return f"{self._get_user_content(story.content.created_by)} added {self._get_user_content(story.content.collaborator)} as a collaborator."
            case "added_to_task":
                return f"{self._get_user_content(story.content.created_by)} added this task to {self._get_named_content(story.content.task)} as a subtask."
            case "removed_from_task":
                return f"{self._get_user_content(story.content.created_by)} removed this task from task {self._get_named_content(story.content.task)}."
            case "added_to_project":
                return f"{self._get_user_content(story.content.created_by)} added this task to project {self._get_named_content(story.content.project)}."
            case "removed_from_project":
                return f"{self._get_user_content(story.content.created_by)} removed this task from project {self._get_named_content(story.content.project)}."
            case "added_to_tag":
                return f"{self._get_user_content(story.content.created_by)} added this task to tag {self._get_named_content(story.content.tag)}."
            case "removed_from_tag":
                return f"{self._get_user_content(story.content.created_by)} removed this task from tag {self._get_named_content(story.content.tag)}."
            case "due_date_changed":
                return self._get_story_due_date_changed_content(story)
            case "section_changed":
                return f"{self._get_user_content(story.content.created_by)} moved this task to section {self._get_named_content(story.content.new_section)}."
            case _:
                return story.content.text or self._get_fallback_story_content(story)

    def _get_story_due_date_changed_content(self, story: AsanaStoryArtifact) -> str:
        old_dates = story.content.old_dates
        new_dates = story.content.new_dates

        if not old_dates or not new_dates:
            return f"{self._get_user_content(story.content.created_by)} changed the date range."

        old_start_on = old_dates.start_on
        new_start_on = new_dates.start_on
        start_on_action: str | None = None
        # set, remove, change, nothing
        if new_start_on and not old_start_on:
            start_on_action = f"set start date to {new_start_on}"
        elif old_start_on and not new_start_on:
            start_on_action = "removed start date"
        elif old_start_on != new_start_on:
            start_on_action = f"changed start date to {new_start_on}"

        old_due_on = old_dates.due_on
        new_due_on = new_dates.due_on
        due_on_action: str | None = None
        # set, remove, change, nothing
        if new_due_on and not old_due_on:
            due_on_action = f"set due date to {new_due_on}"
        elif old_due_on and not new_due_on:
            due_on_action = "removed due date"
        elif old_due_on != new_due_on:
            due_on_action = f"changed due date to {new_due_on}"

        if not start_on_action and not due_on_action:
            return f"{self._get_user_content(story.content.created_by)} changed the date range."

        return (
            f"{self._get_user_content(story.content.created_by)}"
            + (f" {start_on_action}" if start_on_action else "")
            + (" and" if start_on_action and due_on_action else "")
            + (f" {due_on_action}" if due_on_action else "")
        )

    def _get_fallback_story_content(self, story: AsanaStoryArtifact) -> str:
        return f"{self._get_user_content(story.content.created_by)} {story.content.resource_subtype} on this task."

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.ASANA_TASK

    def get_reference_id(self) -> str:
        return asana_task_reference_id(self.task_artifact.metadata.task_gid)

    def get_metadata(self) -> AsanaTaskDocumentMetadata:
        return {
            "task_gid": self.task_artifact.metadata.task_gid,
            "task_name": self.task_artifact.content.task.name,
            "permalink_url": self.task_artifact.content.task.permalink_url,
            "project_gids": self.task_artifact.metadata.project_gids,
            "section_gids": self.task_artifact.metadata.section_gids,
            "workspace_gid": self.task_artifact.metadata.workspace_gid,
            "workspace_name": self.task_artifact.content.workspace.name,
            "created_at": self.task_artifact.content.task.created_at,
            "modified_at": self.task_artifact.content.task.modified_at,
            "due_on": self.task_artifact.content.task.due_on,
            "start_on": self.task_artifact.content.task.start_on,
            "assignee_gid": (
                self.task_artifact.content.task.assignee.gid
                if self.task_artifact.content.task.assignee
                else None
            ),
            "assignee_name": (
                self.task_artifact.content.task.assignee.name
                if self.task_artifact.content.task.assignee
                else None
            ),
        }

    def get_source_created_at(self) -> datetime:
        return datetime.fromisoformat(self.task_artifact.metadata.created_at)

    @classmethod
    def from_artifacts(
        cls,
        task_artifact: AsanaTaskArtifact,
        story_artifacts: list[AsanaStoryArtifact],
        project_artifacts: list[AsanaProjectPermissionsArtifact],
    ) -> "AsanaTaskDocument":
        is_part_of_public_project = any(
            project_artifact.content.project.is_public() for project_artifact in project_artifacts
        )
        has_public_team = any(
            team.team.is_public()
            for project_artifact in project_artifacts
            for team in project_artifact.content.teams
        )
        is_public = is_part_of_public_project or has_public_team

        permission_policy: PermissionPolicy = "tenant" if is_public else "private"
        permission_allowed_tokens: list[str] | None = None

        if not is_public:
            collaborators = task_artifact.content.task.followers
            assignees = (
                [task_artifact.content.task.assignee] if task_artifact.content.task.assignee else []
            )
            project_users = [
                user
                for project_artifact in project_artifacts
                for user in project_artifact.content.get_all_users()
            ]
            allowed_users = collaborators + assignees + project_users
            permission_allowed_tokens = list(
                {make_email_permission_token(user.email) for user in allowed_users if user.email}
            )

        return AsanaTaskDocument(
            id=asana_task_document_id(task_artifact.metadata.task_gid),
            task_artifact=task_artifact,
            story_artifacts=story_artifacts,
            permission_policy=permission_policy,
            permission_allowed_tokens=permission_allowed_tokens,
            source_updated_at=task_artifact.source_updated_at,
        )


def asana_task_reference_id(task_gid: str) -> str:
    return f"r_asana_task_{task_gid}"


def asana_task_document_id(task_gid: str) -> str:
    return f"asana_task_{task_gid}"
