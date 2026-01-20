from pydantic import BaseModel


class ClickupUser(BaseModel):
    id: int
    username: str | None
    email: str


class ClickupGroup(BaseModel):
    """A Clickup user group (called team in the platform)"""

    id: str
    name: str


class ClickupWorkspaceMember(BaseModel):
    user: ClickupUser


class ClickupWorkspace(BaseModel):
    id: str
    name: str
    members: list[ClickupWorkspaceMember]


class ClickupWorkspaceRes(BaseModel):
    teams: list[ClickupWorkspace]


class ClickupSpace(BaseModel):
    id: str
    name: str
    private: bool


class ClickupSpacesRes(BaseModel):
    spaces: list[ClickupSpace]


class ClickupFolder(BaseModel):
    id: str
    name: str
    hidden: bool


class ClickupListWithFolder(BaseModel):
    id: str
    name: str
    folder: ClickupFolder

    @classmethod
    def from_list_folder(cls, lst: "ClickupList", folder: ClickupFolder) -> "ClickupListWithFolder":
        return cls(id=lst.id, name=lst.name, folder=folder)

    def to_list(self) -> "ClickupList":
        return ClickupList(id=self.id, name=self.name)


class ClickupList(BaseModel):
    id: str
    name: str


class ClickupFolderWithLists(BaseModel):
    id: str
    name: str
    hidden: bool

    lists: list[ClickupList]

    def to_folder(self) -> ClickupFolder:
        return ClickupFolder(id=self.id, name=self.name, hidden=self.hidden)


class ClickupFoldersRes(BaseModel):
    folders: list[ClickupFolderWithLists]


class ClickupListsRes(BaseModel):
    lists: list[ClickupListWithFolder]


class ClickupListMembersRes(BaseModel):
    members: list[ClickupUser]


class ClickupTaskStatus(BaseModel):
    id: str
    status: str
    type: str


class ClickupPriority(BaseModel):
    priority: str


class ClickupTag(BaseModel):
    name: str


class ClickupTaskSharing(BaseModel):
    public: bool


class ClickupTaskSpace(BaseModel):
    id: str


class ClickupTask(BaseModel):
    id: str
    name: str
    markdown_description: str
    url: str
    status: ClickupTaskStatus
    priority: ClickupPriority | None

    # epoch milliseconds
    date_created: str
    # epoch milliseconds
    date_updated: str
    # epoch milliseconds
    date_closed: str | None
    # epoch milliseconds
    date_done: str | None

    # workspace id, clickup calls them teams in the API ._.
    team_id: str
    # parent task id for a subtask
    parent: str | None
    top_level_parent: str | None

    creator: ClickupUser | None
    assignees: list[ClickupUser]
    group_assignees: list[ClickupGroup]
    watchers: list[ClickupUser]
    tags: list[ClickupTag]
    sharing: ClickupTaskSharing
    space: ClickupTaskSpace
    folder: ClickupFolder
    list: ClickupList


class ClickupTasksRes(BaseModel):
    tasks: list[ClickupTask]
    last_page: bool


class ClickupCommentReaction(BaseModel):
    reaction: str
    # epoch milliseconds
    date: str
    user: ClickupUser | None


class ClickupComment(BaseModel):
    id: str
    # we could use the 'comment' array for mentions and fancy blocks.. but for now just take the 'comment_text'
    comment_text: str
    user: ClickupUser | None
    reactions: list[ClickupCommentReaction]
    # epoch milliseconds
    date: str
    reply_count: int

    assignee: ClickupUser | None
    group_assignee: ClickupGroup | None
    # Only present if the comment has been assigned as a task
    assigned_by: ClickupUser | None = None
    # Only present if the comment has been assigned as a task
    resolved: bool | None = None


class ClickupCommentsRes(BaseModel):
    comments: list[ClickupComment]
