from typing import Literal

from pydantic import BaseModel


def dedupe_asana_resources[T: AsanaIdentifiedResource](resources: list[T]) -> list[T]:
    """Dedupe asana resources by gid, order preserved"""
    seen_gids = set[str]()
    deduplicated = list[T]()

    for resource in resources:
        if resource.gid not in seen_gids:
            seen_gids.add(resource.gid)
            deduplicated.append(resource)

    return deduplicated


def asana_resource_set_difference[T: AsanaIdentifiedResource](a: list[T], b: list[T]) -> list[T]:
    """A - B set difference for asana resources based on gid"""
    b_gids = {task.gid for task in b}
    return [task for task in a if task.gid not in b_gids]


class AsanaIdentifiedResource(BaseModel, frozen=True):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        # gid is always automatically included
        return ["resource_type"]

    gid: str
    resource_type: str


def get_prefixed_opt_fields(cls: type[AsanaIdentifiedResource], prefix: str) -> list[str]:
    return [f"{prefix}.{field}" for field in cls.get_opt_fields()]


class AsanaNamedResouce(AsanaIdentifiedResource, frozen=True):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        return super().get_opt_fields() + ["name"]

    name: str


class AsanaUser(AsanaNamedResouce, frozen=True):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        return super().get_opt_fields() + ["email"]

    resource_type: Literal["user"]
    email: str


class AsanaWorkspace(AsanaNamedResouce, frozen=True):
    resource_type: Literal["workspace"] | Literal["organization"]


class AsanaTaskParent(AsanaNamedResouce, frozen=True):
    resource_type: Literal["task"]


class AsanaProject(AsanaNamedResouce, frozen=True):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        return super().get_opt_fields() + [
            "privacy_setting",
            "created_at",
            "modified_at",
        ]

    resource_type: Literal["project"]
    privacy_setting: str  # private | private_to_team | public_to_workspace
    created_at: str
    modified_at: str

    def is_public(self) -> bool:
        return self.privacy_setting == "public_to_workspace"


class AsanaSection(AsanaNamedResouce, frozen=True):
    resource_type: Literal["section"]


class AsanaTeam(AsanaNamedResouce, frozen=True):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        return super().get_opt_fields() + ["visibility"]

    resource_type: Literal["team"]
    visibility: str  # public | request_to_join | secret

    def is_public(self) -> bool:
        return self.visibility == "public"


class AsanaTag(AsanaNamedResouce, frozen=True):
    resource_type: Literal["tag"]


class AsanaCustomField(AsanaNamedResouce, frozen=True):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        return super().get_opt_fields() + [
            "display_value",
            *get_prefixed_opt_fields(AsanaUser, "people_value"),
            *get_prefixed_opt_fields(AsanaNamedResouce, "reference_value"),
        ]

    resource_type: Literal["custom_field"]
    display_value: str | None
    people_value: list[AsanaUser] | None = None
    reference_value: list[AsanaNamedResouce] | None = None


class AsanaTaskMembership(BaseModel, frozen=True):
    project: AsanaProject
    section: AsanaSection


class AsanaTask(AsanaNamedResouce, frozen=True):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        return super().get_opt_fields() + [
            "resource_subtype",
            "notes",
            "approval_status",
            "num_likes",
            "num_subtasks",
            "actual_time_minutes",
            "permalink_url",
            "created_at",
            "modified_at",
            "completed_at",
            "start_on",
            "start_at",
            "due_on",
            "due_at",
            *get_prefixed_opt_fields(AsanaUser, "created_by"),
            *get_prefixed_opt_fields(AsanaUser, "completed_by"),
            *get_prefixed_opt_fields(AsanaUser, "assignee"),
            *get_prefixed_opt_fields(AsanaUser, "followers"),
            *get_prefixed_opt_fields(AsanaTaskParent, "parent"),
            *get_prefixed_opt_fields(AsanaProject, "memberships.project"),
            *get_prefixed_opt_fields(AsanaSection, "memberships.section"),
            *get_prefixed_opt_fields(AsanaTag, "tags"),
            *get_prefixed_opt_fields(AsanaCustomField, "custom_fields"),
        ]

    resource_type: Literal["task"]
    resource_subtype: str  # "default_task" | "milestone" | "approval"
    notes: str
    # "approved" | "changes_requested" | "pending" | "rejected" | None, only present for approval tasks
    approval_status: str | None = None
    num_likes: int
    num_subtasks: int
    actual_time_minutes: int | None
    permalink_url: str
    created_by: AsanaUser | None
    completed_by: AsanaUser | None
    assignee: AsanaUser | None
    followers: list[AsanaUser]
    created_at: str
    modified_at: str
    completed_at: str | None
    start_on: str | None  # iso local date only, ex: "2025-01-01"
    start_at: str | None  # populated when start date also has a time component
    due_on: str | None  # iso local date only, ex: "2025-01-01"
    due_at: str | None  # populated when due date also has a time component
    parent: AsanaTaskParent | None
    memberships: list[AsanaTaskMembership]
    tags: list[AsanaTag]
    custom_fields: list[AsanaCustomField]


class StoryDates(BaseModel):
    """the api is missing start_at.. this'll do"""

    due_on: str | None = None
    due_at: str | None = None
    start_on: str | None = None


class AsanaStory(AsanaIdentifiedResource, frozen=True):
    """
    Reference to all story resource_subtype's: https://forum.asana.com/t/no-more-parsing-story-text-new-fields-on-stories/42924
    Lets add special handling for things we can reference, otherwise just use their text:
    - assigned
    - collaborator_added
    - added_to_task
    - removed_from_task
    - added_to_project
    - removed_from_project
    - added_to_tag
    - removed_from_tag
    - due_date_changed (their text doesn't include the year and sometimes has stuff like "Today" in it)
    """

    @classmethod
    def get_opt_fields(cls) -> list[str]:
        return super().get_opt_fields() + [
            "resource_subtype",
            "type",
            "created_at",
            "text",
            "num_likes",
            "old_dates",
            "new_dates",
            *get_prefixed_opt_fields(AsanaUser, "created_by"),
            *get_prefixed_opt_fields(AsanaUser, "assignee"),
            *get_prefixed_opt_fields(AsanaUser, "collaborator"),
            *get_prefixed_opt_fields(AsanaTaskParent, "task"),
            *get_prefixed_opt_fields(AsanaTag, "tag"),
            *get_prefixed_opt_fields(AsanaProject, "project"),
            *get_prefixed_opt_fields(AsanaSection, "new_section"),
        ]

    resource_type: Literal["story"]
    # https://forum.asana.com/t/no-more-parsing-story-text-new-fields-on-stories/42924
    resource_subtype: str
    type: str  # "comment" | "system"

    text: str | None = None
    num_likes: int | None = None
    created_at: str
    old_dates: StoryDates | None = None
    new_dates: StoryDates | None = None

    created_by: AsanaUser | None = None
    assignee: AsanaUser | None = None
    collaborator: AsanaUser | None = None

    task: AsanaTaskParent | None = None
    tag: AsanaTag | None = None
    project: AsanaProject | None = None
    new_section: AsanaSection | None = None


# For whatever reason resource_type and gid can be missing for some event parents
class AsanaEventParent(BaseModel):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        # gid is always automatically included
        return ["resource_type"]

    gid: str | None = None
    resource_type: str | None = None


class AsanaEvent(BaseModel):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        return [
            "type",
            "action",
            "resource.resource_type",
            "parent.resource_type",
        ]

    type: str
    action: str  # changed | added | removed | deleted | undeleted
    parent: AsanaEventParent | None
    resource: AsanaIdentifiedResource


class AsanaNextPage(BaseModel):
    offset: str


class AsanaListRes[T](BaseModel):
    data: list[T]
    next_page: AsanaNextPage | None


class AsanaWorkspaceListRes(AsanaListRes[AsanaWorkspace]):
    pass


class AsanaProjectListRes(AsanaListRes[AsanaProject]):
    pass


class AsanaTaskSearchRes(BaseModel):
    data: list[AsanaTask]


class AsanaStoryListRes(AsanaListRes[AsanaStory]):
    pass


class AsanaEventListRes(BaseModel):
    data: list[AsanaEvent]
    sync: str
    has_more: bool


class AsanaEventListErrorRes(BaseModel):
    sync: str
