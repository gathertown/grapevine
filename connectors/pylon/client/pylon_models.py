"""Pydantic models for Pylon API responses.

Based on: https://docs.usepylon.com/pylon-docs/developer/api/api-reference
"""

from typing import Any

from pydantic import BaseModel


class PylonUser(BaseModel):
    """Pylon user (internal team member)."""

    id: str
    name: str | None = None
    email: str | None = None
    emails: list[str] | None = None
    avatar_url: str | None = None
    role_id: str | None = None
    status: str | None = None  # active, away, out_of_office


class PylonContactRef(BaseModel):
    """Contact reference in author/requester context."""

    id: str
    email: str | None = None


class PylonContact(BaseModel):
    """Pylon contact (external customer contact)."""

    id: str
    name: str | None = None
    email: str | None = None
    emails: list[str] | None = None
    avatar_url: str | None = None
    portal_role: str | None = None  # no_access, member, admin
    portal_role_id: str | None = None
    account: dict[str, str] | None = None  # Contains id
    custom_fields: dict[str, Any] | None = None


class PylonChannel(BaseModel):
    """Account channel information."""

    channel_id: str | None = None
    is_primary: bool | None = None
    source: str | None = None
    mirror_to: str | None = None


class PylonExternalId(BaseModel):
    """External ID reference."""

    external_id: str
    label: str | None = None


class PylonOwner(BaseModel):
    """Account owner information."""

    id: str
    email: str | None = None


class PylonAccount(BaseModel):
    """Pylon account (customer organization)."""

    id: str
    name: str | None = None
    domain: str | None = None  # deprecated
    domains: list[str] | None = None
    primary_domain: str | None = None
    tags: list[str] | None = None
    logo_url: str | None = None
    owner_id: str | None = None
    owner: PylonOwner | None = None
    subaccount_ids: list[str] | None = None
    channels: list[PylonChannel] | None = None
    external_ids: list[PylonExternalId] | None = None
    custom_fields: dict[str, Any] | None = None
    created_at: str | None = None
    type: str | None = None
    crm_settings: dict[str, Any] | None = None
    latest_customer_activity_time: str | None = None


class PylonMessageAuthor(BaseModel):
    """Author information for a message."""

    name: str | None = None
    avatar_url: str | None = None
    contact: PylonContactRef | None = None
    user: PylonUser | None = None


class PylonEmailInfo(BaseModel):
    """Email metadata for a message."""

    from_email: str | None = None
    to_emails: list[str] | None = None
    cc_emails: list[str] | None = None
    bcc_emails: list[str] | None = None


class PylonMessage(BaseModel):
    """Pylon message within an issue."""

    id: str
    message_html: str | None = None
    source: str | None = None  # e.g., "slack", "email", "web"
    is_private: bool | None = None
    timestamp: str | None = None
    thread_id: str | None = None
    file_urls: list[str] | None = None
    author: PylonMessageAuthor | None = None
    email_info: PylonEmailInfo | None = None


class PylonAssignee(BaseModel):
    """Assignee information."""

    id: str
    email: str | None = None


class PylonTeamUser(BaseModel):
    """User info within team response."""

    id: str
    email: str | None = None


class PylonTeam(BaseModel):
    """Team information."""

    id: str
    name: str | None = None
    users: list[PylonTeamUser] | None = None


class PylonRequester(BaseModel):
    """Requester information (contact or user)."""

    id: str | None = None
    email: str | None = None


class PylonCsatResponse(BaseModel):
    """CSAT (Customer Satisfaction) response."""

    score: int | None = None
    comment: str | None = None


class PylonExternalIssue(BaseModel):
    """External issue reference (Linear, Asana, Jira, GitHub)."""

    source: str | None = None  # "linear", "asana", "jira", "github"
    external_id: str | None = None
    link: str | None = None


class PylonSlackInfo(BaseModel):
    """Slack-specific issue information."""

    workspace_id: str | None = None
    channel_id: str | None = None
    message_ts: str | None = None


class PylonChatWidgetInfo(BaseModel):
    """Chat widget information."""

    page_url: str | None = None


class PylonAccountRef(BaseModel):
    """Account reference in issue context."""

    id: str


class PylonIssue(BaseModel):
    """Pylon issue (support ticket).

    Based on: https://docs.usepylon.com/pylon-docs/developer/api/api-reference/issues
    """

    id: str
    number: int | None = None
    title: str | None = None
    body_html: str | None = None
    state: str | None = None  # open, snoozed, closed
    source: str | None = None  # slack, email, etc.
    type: str | None = None  # Conversation, Ticket
    priority: str | None = None  # low, medium, high, urgent
    link: str | None = None

    # Timestamps (RFC3339 format)
    created_at: str | None = None
    updated_at: str | None = None
    latest_message_time: str | None = None
    first_response_time: str | None = None  # RFC3339 datetime
    resolution_time: str | None = None  # RFC3339 datetime
    snoozed_until_time: str | None = None

    # Metrics in seconds
    first_response_seconds: int | None = None
    business_hours_first_response_seconds: int | None = None
    resolution_seconds: int | None = None
    business_hours_resolution_seconds: int | None = None
    number_of_touches: int | None = None

    # Content
    tags: list[str] | None = None
    attachment_urls: list[str] | None = None
    customer_portal_visible: bool | None = None

    # Relationships
    assignee: PylonAssignee | None = None
    requester: PylonRequester | None = None
    account: PylonAccountRef | None = None
    team: PylonTeam | None = None
    external_issues: list[PylonExternalIssue] | None = None
    csat_responses: list[PylonCsatResponse] | None = None

    # Platform-specific info
    slack: PylonSlackInfo | None = None
    chat_widget_info: PylonChatWidgetInfo | None = None

    # Custom fields - can have nested structures with slug, value, values
    custom_fields: dict[str, Any] | None = None


class PylonTag(BaseModel):
    """Pylon tag object."""

    id: str
    value: str | None = None
    hex_color: str | None = None
    object_type: str | None = None  # account, issue, contact


class PylonMeResponse(BaseModel):
    """Response from /me endpoint."""

    id: str
    name: str


class PylonPagination(BaseModel):
    """Pagination information."""

    cursor: str | None = None
    has_next_page: bool | None = None


class PylonIssuesResponse(BaseModel):
    """Response from GET /issues endpoint."""

    data: list[PylonIssue]
    cursor: str | None = None
    request_id: str | None = None
    pagination: PylonPagination | None = None


class PylonAccountsResponse(BaseModel):
    """Response from GET /accounts endpoint."""

    data: list[PylonAccount]
    cursor: str | None = None
    request_id: str | None = None
    pagination: PylonPagination | None = None


class PylonContactsResponse(BaseModel):
    """Response from GET /contacts endpoint."""

    data: list[PylonContact]
    cursor: str | None = None
    request_id: str | None = None
    pagination: PylonPagination | None = None


class PylonMessagesResponse(BaseModel):
    """Response from issue messages endpoint."""

    data: list[PylonMessage]
    request_id: str | None = None


class PylonTagsResponse(BaseModel):
    """Response from GET /tags endpoint."""

    data: list[PylonTag]
    request_id: str | None = None
    pagination: PylonPagination | None = None


class PylonUsersResponse(BaseModel):
    """Response from GET /users endpoint."""

    data: list[PylonUser]
    cursor: str | None = None
    request_id: str | None = None
    pagination: PylonPagination | None = None


class PylonTeamsResponse(BaseModel):
    """Response from GET /teams endpoint."""

    data: list[PylonTeam]
    cursor: str | None = None
    request_id: str | None = None
    pagination: PylonPagination | None = None
