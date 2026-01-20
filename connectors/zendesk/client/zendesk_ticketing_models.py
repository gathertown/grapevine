from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Discriminator, Field, Tag

from connectors.zendesk.client.zendesk_models import ZendeskPageMetadata


class ZendeskUser(BaseModel):
    id: int
    role: str | None  # "admin", "agent", "end-user"
    name: str | None
    email: str | None

    created_at: str
    updated_at: str


class ZendeskBrand(BaseModel):
    id: int
    name: str
    brand_url: str
    subdomain: str

    created_at: str
    updated_at: str


class ZendeskGroup(BaseModel):
    id: int
    name: str
    description: str
    is_public: bool
    default: bool

    created_at: str
    updated_at: str


class ZendeskOrganization(BaseModel):
    id: int
    name: str
    details: str | None
    notes: str | None
    domain_names: list[str]
    group_id: int | None

    created_at: str
    updated_at: str


class ZendeskTicketField(BaseModel):
    id: int
    type: str
    title: str
    description: str | None

    created_at: str
    updated_at: str


class ZendeskCustomTicketStatus(BaseModel):
    id: int
    agent_label: str
    end_user_label: str
    description: str | None
    status_category: str  # "new", "open", "pending", "hold", "solved"

    created_at: str
    updated_at: str


class ZendeskMetricMinutes(BaseModel):
    calendar: int | None
    business: int | None


class ZendeskTicketMetrics(BaseModel):
    id: int
    ticket_id: int

    group_stations: int | None
    assignee_stations: int | None
    reopens: int | None
    replies: int | None

    assignee_updated_at: str | None
    requester_updated_at: str | None
    status_updated_at: str | None
    initially_assigned_at: str | None
    assigned_at: str | None
    solved_at: str | None
    latest_comment_added_at: str | None

    # This field was legit missing in some json in the wild so make optional
    custom_status_updated_at: str | None = None

    reply_time_in_minutes: ZendeskMetricMinutes | None
    first_resolution_time_in_minutes: ZendeskMetricMinutes | None
    full_resolution_time_in_minutes: ZendeskMetricMinutes | None
    agent_wait_time_in_minutes: ZendeskMetricMinutes | None
    requester_wait_time_in_minutes: ZendeskMetricMinutes | None
    on_hold_time_in_minutes: ZendeskMetricMinutes | None

    created_at: str
    updated_at: str


fallback_event_type = "default"
handled_ticket_audit_event_types = {
    "Create",
    "Change",
    "Comment",
}


# fallback for events we don't explicitly handle / care about
class ZendeskTicketAuditDefaultEvent(BaseModel):
    id: int
    event_type: str


class ZendeskTicketAuditCreateEvent(BaseModel):
    id: int
    event_type: Literal["Create"]


class ZendeskTicketAuditChangeEvent(BaseModel):
    id: int
    event_type: Literal["Change"]


class ZendeskTicketAuditCommentEvent(BaseModel):
    id: int
    event_type: Literal["Comment"]
    # markdown version of body, also see plain_body, html_body
    body: str | None
    public: bool
    author_id: int | None


# Handle dicts and model instances
def zendesk_ticket_audit_event_discriminator(
    v: Union[dict[str, Any], "ZendeskTicketAuditEvent"],
) -> str:
    audit_event_type = v.get("event_type") if isinstance(v, dict) else v.event_type

    if audit_event_type in handled_ticket_audit_event_types:
        return audit_event_type

    return fallback_event_type


ZendeskTicketAuditEvent = Annotated[
    Annotated[ZendeskTicketAuditCreateEvent, Tag("Create")]
    | Annotated[ZendeskTicketAuditChangeEvent, Tag("Change")]
    | Annotated[ZendeskTicketAuditCommentEvent, Tag("Comment")]
    | Annotated[ZendeskTicketAuditDefaultEvent, Tag("default")],
    Discriminator(zendesk_ticket_audit_event_discriminator),
]


class ZendeskTicketAudit(BaseModel):
    id: int
    ticket_id: int
    updater_id: int | None
    child_events: list[ZendeskTicketAuditEvent]

    created_at: str
    timestamp: int


class ZendeskTicketCustomField(BaseModel):
    id: int
    value: object | None


class ZendeskSatisfactionRating(BaseModel):
    id: int | None = None
    score: str  # "offered", "unoffered", "good", "bad"
    comment: str | None = None


class ZendeskTicket(BaseModel):
    id: int
    subdomain: str

    type: str | None  # incident | question | task
    status: str  # new | open | pending | hold | solved | closed | deleted
    priority: str | None  # urgent | high | normal | low
    has_incidents: bool
    is_public: bool
    tags: list[str]

    description: str | None
    subject: str | None
    custom_fields: list[ZendeskTicketCustomField]
    satisfaction_rating: ZendeskSatisfactionRating

    due_at: str | None
    created_at: str
    updated_at: str
    generated_timestamp: int

    custom_status_id: int | None
    brand_id: int | None
    requester_id: int | None
    submitter_id: int | None
    assignee_id: int | None
    organization_id: int | None
    group_id: int | None
    collaborator_ids: list[int]
    follower_ids: list[int]

    def get_user_ids(self) -> set[int]:
        user_ids: set[int] = set()

        if self.requester_id is not None:
            user_ids.add(self.requester_id)

        if self.submitter_id is not None:
            user_ids.add(self.submitter_id)

        if self.assignee_id is not None:
            user_ids.add(self.assignee_id)

        user_ids.update(self.collaborator_ids)
        user_ids.update(self.follower_ids)

        return user_ids


class ZendeskIncrementalTicketResponse(BaseModel):
    tickets: list[ZendeskTicket]
    metric_sets: list[ZendeskTicketMetrics] = Field(default_factory=list[ZendeskTicketMetrics])
    end_of_stream: bool
    after_cursor: str | None


class ZendeskIncrementalTicketEventResponse(BaseModel):
    ticket_events: list[ZendeskTicketAudit]
    end_of_stream: bool
    end_time: int | None


class ZendeskTicketFieldResponse(BaseModel):
    ticket_fields: list[ZendeskTicketField]
    meta: ZendeskPageMetadata


class ZendeskBrandResponse(BaseModel):
    brands: list[ZendeskBrand]
    meta: ZendeskPageMetadata


class ZendeskGroupResponse(BaseModel):
    groups: list[ZendeskGroup]
    meta: ZendeskPageMetadata


class ZendeskSearchTicketResponse(BaseModel):
    results: list[ZendeskTicket]
    meta: ZendeskPageMetadata
