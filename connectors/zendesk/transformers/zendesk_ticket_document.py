"""
Zendesk document classes for structured ticket and comment representation.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter

from connectors.base import BaseChunk, BaseDocument
from connectors.base.document_source import DocumentSource


class ZendeskTicketChunkMetadata(TypedDict):
    chunk_index: int
    total_chunks: int
    ticket_id: int


class ZendeskTicketChunkRawData(ZendeskTicketChunkMetadata):
    content: str


class ZendeskTicketDocumentMetadata(TypedDict):
    ticket_id: int
    ticket_subdomain: str
    ticket_subject: str | None
    ticket_type: str | None
    ticket_status: str
    ticket_priority: str | None

    created_at: str
    updated_at: str

    brand_id: int | None
    brand_name: str | None

    requester_id: int | None
    requester_name: str | None

    submitter_id: int | None
    submitter_name: str | None

    assignee_id: int | None
    assignee_name: str | None

    organization_id: int | None
    organization_name: str | None

    group_id: int | None
    group_name: str | None


@dataclass
class ZendeskTicketChunk(BaseChunk[ZendeskTicketChunkMetadata]):
    def get_content(self) -> str:
        content = self.raw_data.get("content", "")
        chunk_index = self.raw_data.get("chunk_index", 0)
        total_chunks = self.raw_data.get("total_chunks", 1)

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> ZendeskTicketChunkMetadata:
        return ZendeskTicketChunkMetadata(
            ticket_id=self.raw_data["ticket_id"],
            chunk_index=self.raw_data.get("chunk_index", -1),
            total_chunks=self.raw_data.get("total_chunks", -1),
        )


class RawDataNamed(TypedDict):
    id: int
    name: str | None


class RawDataUser(TypedDict):
    id: int
    name: str | None
    email: str | None


class RawDataSatisfactionRating(TypedDict):
    id: int | None
    score: str  # "offered", "unoffered", "good", "bad"
    comment: str | None


class RawDataTicketCustomField(TypedDict):
    id: int
    title: str | None
    value: object | None


class RawDataTicketCustomStatus(TypedDict):
    id: int
    agent_label: str | None


class RawDataTicketMetrics(TypedDict):
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
    custom_status_updated_at: str | None

    # lets just use business minutes for these
    reply_time_in_minutes: int | None
    first_resolution_time_in_minutes: int | None
    full_resolution_time_in_minutes: int | None
    agent_wait_time_in_minutes: int | None
    requester_wait_time_in_minutes: int | None
    on_hold_time_in_minutes: int | None


class RawDataAuditCreateEvent(TypedDict):
    id: int
    event_type: Literal["Create"]


class RawDataAuditChangeEvent(TypedDict):
    id: int
    event_type: Literal["Change"]


class RawDataAuditCommentEvent(TypedDict):
    id: int
    event_type: Literal["Comment"]
    # markdown version of body, also see plain_body, html_body
    body: str | None
    public: bool
    author: RawDataUser | None


RawDataAuditEvent = RawDataAuditCreateEvent | RawDataAuditChangeEvent | RawDataAuditCommentEvent


class RawDataAudit(TypedDict):
    id: int
    created_at: str
    updater: RawDataUser | None
    child_events: list[RawDataAuditEvent]


class ZendeskTicketDocumentRawData(TypedDict):
    id: int
    subdomain: str
    description: str | None
    subject: str | None
    type: str | None
    status: str
    priority: str | None
    tags: list[str]

    satisfaction_rating: RawDataSatisfactionRating
    custom_fields: list[RawDataTicketCustomField]
    custom_status: RawDataTicketCustomStatus | None
    metrics: RawDataTicketMetrics | None
    audits: list[RawDataAudit]

    brand: RawDataNamed | None
    organization: RawDataNamed | None
    group: RawDataNamed | None

    requester: RawDataUser | None
    submitter: RawDataUser | None
    assignee: RawDataUser | None

    collaborators: list[RawDataUser]
    followers: list[RawDataUser]

    due_at: str | None
    created_at: str
    updated_at: str


@dataclass
class ZendeskTicketDocument(BaseDocument[ZendeskTicketChunk, ZendeskTicketDocumentMetadata]):
    raw_data: ZendeskTicketDocumentRawData

    def get_header_content(self) -> str:
        lines: list[str] = []

        custom_status = self.raw_data["custom_status"]
        status_category = self.raw_data["status"]
        status_primary = custom_status["agent_label"] if custom_status else status_category
        status_secondary = f" ({status_category})" if custom_status else ""

        lines.append("# Zendesk Ticket")
        lines.append(f"- Subject: {self.raw_data['subject'] or ''}")
        lines.append(f"- Description: {self.raw_data['description'] or ''}")
        lines.append(f"- Ticket ID: {self.raw_data['id']}")
        lines.append(f"- Subdomain: {self.raw_data['subdomain']}")
        lines.append(f"- Status: {status_primary}{status_secondary}")
        lines.append(f"- Priority: {self.raw_data['priority'] or ''}")
        lines.append(f"- Type: {self.raw_data['type'] or ''}")
        lines.append(f"- Tags: {', '.join(self.raw_data['tags']) if self.raw_data['tags'] else ''}")
        lines.append(f"- Due At: {self.raw_data['due_at'] or ''}")
        lines.append(f"- Created At: {self.raw_data['created_at']}")
        lines.append(f"- Updated At: {self.raw_data['updated_at']}")

        lines.append("## People involved")
        lines.append(f"- Assignee: {self._get_user_content(self.raw_data['assignee'])}")
        lines.append(f"- Requester: {self._get_user_content(self.raw_data['requester'])}")
        lines.append(f"- Submitter: {self._get_user_content(self.raw_data['submitter'])}")

        lines.append(
            f"- Collaborators: {', '.join([self._get_user_content(user) for user in self.raw_data['collaborators']])}"
        )
        lines.append(
            f"- Followers: {', '.join([self._get_user_content(user) for user in self.raw_data['followers']])}"
        )

        lines.append("## Additional Details")
        for field in self.raw_data["custom_fields"]:
            lines.append(f"- {field['title']}: {field['value'] or ''}")

        lines.append("## Satisfaction Rating")
        lines.append(f"- Score: {self.raw_data['satisfaction_rating']['score']}")
        lines.append(f"- Comment: {self.raw_data['satisfaction_rating']['comment'] or ''}")

        lines.append("## Metrics ")
        lines.append(f"- Group Stations: {self._get_metric_data('group_stations')}")
        lines.append(f"- Assignee Stations: {self._get_metric_data('assignee_stations')}")
        lines.append(f"- Reopens: {self._get_metric_data('reopens')}")
        lines.append(f"- Replies: {self._get_metric_data('replies')}")

        lines.append(f"- Assignee Updated At: {self._get_metric_data('assignee_updated_at')}")
        lines.append(f"- Requester Updated At: {self._get_metric_data('requester_updated_at')}")
        lines.append(f"- Status Updated At: {self._get_metric_data('status_updated_at')}")
        lines.append(f"- Initially Assigned At: {self._get_metric_data('initially_assigned_at')}")
        lines.append(f"- Assigned At: {self._get_metric_data('assigned_at')}")
        lines.append(f"- Solved At: {self._get_metric_data('solved_at')}")
        lines.append(
            f"- Latest Comment Added At: {self._get_metric_data('latest_comment_added_at')}"
        )
        lines.append(
            f"- Custom Status Updated At: {self._get_metric_data('custom_status_updated_at')}"
        )

        lines.append(f"- Reply Time (minutes): {self._get_metric_data('reply_time_in_minutes')}")
        lines.append(
            f"- Full Resolution Time (minutes): {self._get_metric_data('full_resolution_time_in_minutes')}"
        )
        lines.append(
            f"- Agent Wait Time (minutes): {self._get_metric_data('agent_wait_time_in_minutes')}"
        )
        lines.append(
            f"- Requester Wait Time (minutes): {self._get_metric_data('requester_wait_time_in_minutes')}"
        )
        lines.append(
            f"- First Resolution Time (minutes): {self._get_metric_data('first_resolution_time_in_minutes')}"
        )
        lines.append(
            f"- On Hold Time (minutes): {self._get_metric_data('on_hold_time_in_minutes')}"
        )

        lines.append("## Belongs to")
        lines.append(f"- Brand: {self._get_named_content(self.raw_data['brand'])}")
        lines.append(f"- Organization: {self._get_named_content(self.raw_data['organization'])}")
        lines.append(f"- Group: {self._get_named_content(self.raw_data['group'])}")

        return "\n".join(lines)

    def _get_metric_data(self, metric_name: str) -> str:
        if not self.raw_data["metrics"]:
            return ""
        metric_value = self.raw_data["metrics"].get(metric_name)
        return str(metric_value) if metric_value is not None else ""

    def _get_named_content(self, named: RawDataNamed | None) -> str:
        if not named:
            return ""
        parts: list[str | None] = [named["name"], str(named["id"])]
        defined_parts = [f"@{part}" for part in parts if part]
        return f"<{'|'.join(defined_parts)}>"

    def _get_user_content(self, user: RawDataUser | None) -> str:
        if not user:
            return ""

        if user["name"]:
            name_likely_email = "@" in user["name"]
            name = user["name"] if name_likely_email else f"@{user['name']}"
        else:
            name = None

        email = user["email"] if user["email"] else None
        id = f"@{str(user['id'])}"

        defined_parts: list[str] = [part for part in (name, email, id) if part]
        return f"<{'|'.join(defined_parts)}>"

    def get_content(self) -> str:
        non_empty_audits = [audit for audit in self.raw_data["audits"] if audit["child_events"]]
        audit_content = [self._get_content_from_audit(audit) for audit in non_empty_audits]

        return "\n\n".join([self.get_header_content()] + audit_content)

    def to_embedding_chunks(self) -> list[ZendeskTicketChunk]:
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

        embedding_chunks: list[ZendeskTicketChunk] = []

        for i, chunk_text in enumerate(text_chunks):
            chunk_data = ZendeskTicketChunkRawData(
                ticket_id=self.raw_data["id"],
                content=chunk_text,
                chunk_index=i,
                total_chunks=len(text_chunks),
            )

            chunk = ZendeskTicketChunk(document=self, raw_data=chunk_data)
            embedding_chunks.append(chunk)

        return embedding_chunks

    def _get_content_from_audit(self, audit: RawDataAudit) -> str:
        if not audit["child_events"]:
            return ""

        lines: list[str] = []

        has_create_event = any(
            event for event in audit["child_events"] if event["event_type"] == "Create"
        )
        has_change_event = any(
            event for event in audit["child_events"] if event["event_type"] == "Change"
        )

        if has_create_event:
            lines.append(
                f"- Created by {self._get_user_content(audit['updater'])} at {audit['created_at']}"
            )

        if has_change_event:
            lines.append(
                f"- Updated by {self._get_user_content(audit['updater'])} at {audit['created_at']}"
            )

        comment_events: list[RawDataAuditCommentEvent] = [
            event for event in audit["child_events"] if event["event_type"] == "Comment"
        ]
        for comment_event in comment_events:
            lines.append("# Comment")
            lines.append(
                f"- Commented by {self._get_user_content(comment_event['author'])} at {audit['created_at']}"
            )
            lines.append("## Comment Body")
            lines.append(comment_event["body"] or "")

        return "\n".join(lines)

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.ZENDESK_TICKET

    def get_reference_id(self) -> str:
        ticket_id = self.raw_data.get("id")
        return f"r_zendesk_ticket_{ticket_id}"

    def get_metadata(self) -> ZendeskTicketDocumentMetadata:
        return ZendeskTicketDocumentMetadata(
            ticket_id=self.raw_data["id"],
            ticket_subdomain=self.raw_data["subdomain"],
            ticket_subject=self.raw_data["subject"],
            ticket_type=self.raw_data["type"],
            ticket_status=self.raw_data["status"],
            ticket_priority=self.raw_data["priority"],
            created_at=self.raw_data["created_at"],
            updated_at=self.raw_data["updated_at"],
            brand_id=self.raw_data["brand"]["id"] if self.raw_data["brand"] else None,
            brand_name=self.raw_data["brand"]["name"] if self.raw_data["brand"] else None,
            requester_id=self.raw_data["requester"]["id"] if self.raw_data["requester"] else None,
            requester_name=self.raw_data["requester"]["name"]
            if self.raw_data["requester"]
            else None,
            submitter_id=self.raw_data["submitter"]["id"] if self.raw_data["submitter"] else None,
            submitter_name=self.raw_data["submitter"]["name"]
            if self.raw_data["submitter"]
            else None,
            assignee_id=self.raw_data["assignee"]["id"] if self.raw_data["assignee"] else None,
            assignee_name=self.raw_data["assignee"]["name"] if self.raw_data["assignee"] else None,
            organization_id=self.raw_data["organization"]["id"]
            if self.raw_data["organization"]
            else None,
            organization_name=self.raw_data["organization"]["name"]
            if self.raw_data["organization"]
            else None,
            group_id=self.raw_data["group"]["id"] if self.raw_data["group"] else None,
            group_name=self.raw_data["group"]["name"] if self.raw_data["group"] else None,
        )

    def get_source_created_at(self) -> datetime:
        return datetime.fromisoformat(self.get_metadata()["created_at"])


def zendesk_ticket_document_id(ticket_id: int) -> str:
    return f"zendesk_ticket_{ticket_id}"
