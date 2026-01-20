"""Typed models for Intercom API data structures.

These models represent the data structures returned by the Intercom API.
They use Pydantic for validation and provide type safety throughout the codebase.
"""

from pydantic import BaseModel, ConfigDict, Field


class IntercomAuthor(BaseModel):
    """Author information for conversation parts."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    name: str | None = None
    email: str | None = None
    from_ai_agent: bool | None = None


class IntercomAttachment(BaseModel):
    """Attachment in conversation or article."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    name: str | None = None
    url: str | None = None
    content_type: str | None = None
    filesize: int | None = None


class IntercomConversationPart(BaseModel):
    """A single part/message in a conversation."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    part_type: str | None = None
    body: str | None = None
    created_at: int | str | None = None
    updated_at: int | str | None = None
    author: IntercomAuthor | None = None
    attachments: list[IntercomAttachment] = Field(default_factory=list)
    from_ai_agent: bool | None = None
    is_ai_answer: bool | None = None


class IntercomConversationParts(BaseModel):
    """Container for conversation parts."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    conversation_parts: list[IntercomConversationPart] = Field(default_factory=list)
    total_count: int | None = None


class IntercomSource(BaseModel):
    """Source information for a conversation."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    delivered_as: str | None = None
    subject: str | None = None
    body: str | None = None
    author: IntercomAuthor | None = None
    attachments: list[IntercomAttachment] = Field(default_factory=list)
    url: str | None = None


class IntercomTag(BaseModel):
    """Tag applied to a resource."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    name: str | None = None


class IntercomTagList(BaseModel):
    """List container for tags."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    tags: list[IntercomTag] = Field(default_factory=list)


class IntercomContactReference(BaseModel):
    """Reference to a contact in a conversation."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    external_id: str | None = None
    name: str | None = None
    email: str | None = None


class IntercomContactList(BaseModel):
    """List container for contacts."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    contacts: list[IntercomContactReference] = Field(default_factory=list)


class IntercomTeammateReference(BaseModel):
    """Reference to a teammate."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None


class IntercomTeammateList(BaseModel):
    """List container for teammates."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    teammates: list[IntercomTeammateReference] = Field(default_factory=list)


class IntercomTopic(BaseModel):
    """Topic/category for a conversation."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    name: str | None = None


class IntercomTopicList(BaseModel):
    """List container for topics."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    topics: list[IntercomTopic] = Field(default_factory=list)


class IntercomLinkedObject(BaseModel):
    """Linked object reference."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None


class IntercomLinkedObjectList(BaseModel):
    """List container for linked objects."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    total_count: int | None = None
    has_more: bool | None = None
    data: list[IntercomLinkedObject] = Field(default_factory=list)


class IntercomFirstContactReply(BaseModel):
    """First contact reply metadata."""

    model_config = ConfigDict(extra="allow")

    created_at: int | str | None = None
    type: str | None = None
    url: str | None = None


class IntercomConversationData(BaseModel):
    """Full conversation data from Intercom API.

    This represents the complete conversation object returned by the API.
    """

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | int
    workspace_id: str | None = None
    title: str | None = None
    created_at: int | str | None = None
    updated_at: int | str | None = None
    waiting_since: int | str | None = None
    snoozed_until: int | str | None = None
    open: bool | None = None
    read: bool | None = None
    state: str | None = None
    priority: str | None = None
    admin_assignee_id: str | int | None = None
    team_assignee_id: str | int | None = None
    company_id: str | int | None = None

    source: IntercomSource | None = None
    contacts: IntercomContactList | None = None
    teammates: IntercomTeammateList | None = None
    tags: IntercomTagList | None = None
    topics: IntercomTopicList | None = None
    linked_objects: IntercomLinkedObjectList | None = None
    conversation_parts: IntercomConversationParts | None = None
    first_contact_reply: IntercomFirstContactReply | None = None
    custom_attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


# Help Center Article Types


class IntercomArticleAuthor(BaseModel):
    """Author of a Help Center article."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    name: str | None = None
    email: str | None = None


class IntercomArticleStatistics(BaseModel):
    """Statistics for a Help Center article."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    views: int | None = None
    conversions: int | None = None
    reactions: int | None = None
    happy_reaction_percentage: float | None = None
    neutral_reaction_percentage: float | None = None
    sad_reaction_percentage: float | None = None


class IntercomArticleData(BaseModel):
    """Full Help Center article data from Intercom API."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | int
    workspace_id: str | None = None
    title: str | None = None
    description: str | None = None
    body: str | None = None
    author_id: str | int | None = None
    state: str | None = None
    created_at: int | str | None = None
    updated_at: int | str | None = None
    url: str | None = None
    parent_id: str | int | None = None
    parent_type: str | None = None
    default_locale: str | None = None
    parent_ids: list[str | int] = Field(default_factory=list)

    # Additional fields that may be present
    author: IntercomArticleAuthor | None = None
    statistics: IntercomArticleStatistics | None = None


# Contact Types


class IntercomLocation(BaseModel):
    """Location information for a contact."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    country: str | None = None
    region: str | None = None
    city: str | None = None
    country_code: str | None = None
    continent_code: str | None = None


class IntercomSocialProfile(BaseModel):
    """Social profile for a contact."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    name: str | None = None
    url: str | None = None


class IntercomSocialProfileList(BaseModel):
    """List container for social profiles."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    data: list[IntercomSocialProfile] = Field(default_factory=list)


class IntercomCompanyReference(BaseModel):
    """Reference to a company from a contact."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    name: str | None = None
    company_id: str | None = None


class IntercomCompanyList(BaseModel):
    """List container for companies."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    data: list[IntercomCompanyReference] = Field(default_factory=list)
    url: str | None = None
    total_count: int | None = None
    has_more: bool | None = None


class IntercomContactTagList(BaseModel):
    """List container for contact tags."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    data: list[IntercomTag] = Field(default_factory=list)
    url: str | None = None
    total_count: int | None = None
    has_more: bool | None = None


class IntercomContactData(BaseModel):
    """Full contact data from Intercom API."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str
    workspace_id: str | None = None
    external_id: str | None = None
    role: str | None = None
    email: str | None = None
    phone: str | None = None
    name: str | None = None
    avatar: str | None = None
    owner_id: str | None = None
    signed_up_at: int | str | None = None
    last_seen_at: int | str | None = None
    last_replied_at: int | str | None = None
    last_contacted_at: int | str | None = None
    last_email_opened_at: int | str | None = None
    last_email_clicked_at: int | str | None = None
    language_override: str | None = None
    browser: str | None = None
    browser_version: str | None = None
    browser_language: str | None = None
    os: str | None = None
    android_app_name: str | None = None
    android_app_version: str | None = None
    android_device: str | None = None
    android_os_version: str | None = None
    android_sdk_version: str | None = None
    android_last_seen_at: int | str | None = None
    ios_app_name: str | None = None
    ios_app_version: str | None = None
    ios_device: str | None = None
    ios_os_version: str | None = None
    ios_sdk_version: str | None = None
    ios_last_seen_at: int | str | None = None
    unsubscribed_from_emails: bool | None = None
    created_at: int | str | None = None
    updated_at: int | str | None = None
    marked_email_as_spam: bool | None = None
    has_hard_bounced: bool | None = None

    location: IntercomLocation | None = None
    social_profiles: IntercomSocialProfileList | None = None
    companies: IntercomCompanyList | None = None
    tags: IntercomContactTagList | None = None
    custom_attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


# Company Types


class IntercomPlan(BaseModel):
    """Plan information for a company."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    name: str | None = None


class IntercomCompanyTagList(BaseModel):
    """List container for company tags."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    data: list[IntercomTag] = Field(default_factory=list)


class IntercomSegment(BaseModel):
    """Segment reference for a company."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str | None = None
    name: str | None = None


class IntercomSegmentList(BaseModel):
    """List container for segments."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    segments: list[IntercomSegment] = Field(default_factory=list)


class IntercomCompanyData(BaseModel):
    """Full company data from Intercom API."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    id: str
    workspace_id: str | None = None
    company_id: str | None = None
    name: str | None = None
    website: str | None = None
    industry: str | None = None
    size: int | None = None
    user_count: int | None = None
    session_count: int | None = None
    monthly_spend: float | None = None
    remote_created_at: int | str | None = None
    created_at: int | str | None = None
    updated_at: int | str | None = None
    last_request_at: int | str | None = None

    plan: IntercomPlan | None = None
    tags: IntercomCompanyTagList | None = None
    segments: IntercomSegmentList | None = None
    custom_attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


# API Response Types


class IntercomPaginationPages(BaseModel):
    """Pagination information in API responses."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    next: dict[str, str | None] | None = None
    page: int | None = None
    per_page: int | None = None
    total_pages: int | None = None


class IntercomConversationsResponse(BaseModel):
    """Response from conversations list/search API."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    conversations: list[IntercomConversationData] = Field(default_factory=list)
    pages: IntercomPaginationPages | None = None
    total_count: int | None = None


class IntercomArticlesResponse(BaseModel):
    """Response from articles list/search API."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    data: list[IntercomArticleData] = Field(default_factory=list)
    pages: IntercomPaginationPages | None = None
    total_count: int | None = None


class IntercomContactsResponse(BaseModel):
    """Response from contacts list/search API."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    data: list[IntercomContactData] = Field(default_factory=list)
    pages: IntercomPaginationPages | None = None
    total_count: int | None = None


class IntercomCompaniesResponse(BaseModel):
    """Response from companies list API."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    data: list[IntercomCompanyData] = Field(default_factory=list)
    pages: IntercomPaginationPages | None = None
    total_count: int | None = None
