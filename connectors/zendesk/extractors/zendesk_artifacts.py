from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from connectors.base.base_ingest_artifact import ArtifactEntity, BaseIngestArtifact
from connectors.zendesk.client.zendesk_help_center_models import (
    ZendeskArticle,
    ZendeskCategory,
    ZendeskComment,
    ZendeskSection,
)
from connectors.zendesk.client.zendesk_ticketing_models import (
    ZendeskBrand,
    ZendeskCustomTicketStatus,
    ZendeskGroup,
    ZendeskOrganization,
    ZendeskTicket,
    ZendeskTicketAudit,
    ZendeskTicketField,
    ZendeskTicketMetrics,
    ZendeskUser,
)


class ZendeskUserArtifactMetadata(BaseModel):
    user_id: int
    user_name: str | None

    @classmethod
    def from_api_user(cls, user: ZendeskUser) -> "ZendeskUserArtifactMetadata":
        return ZendeskUserArtifactMetadata(
            user_id=user.id,
            user_name=user.name,
        )


class ZendeskGroupArtifactMetadata(BaseModel):
    group_id: int
    group_name: str

    @classmethod
    def from_api_group(cls, group: ZendeskGroup) -> "ZendeskGroupArtifactMetadata":
        return ZendeskGroupArtifactMetadata(
            group_id=group.id,
            group_name=group.name,
        )


class ZendeskTicketFieldArtifactMetadata(BaseModel):
    ticket_field_id: int
    ticket_field_title: str

    @classmethod
    def from_api_ticket_field(
        cls, ticket_field: ZendeskTicketField
    ) -> "ZendeskTicketFieldArtifactMetadata":
        return ZendeskTicketFieldArtifactMetadata(
            ticket_field_id=ticket_field.id,
            ticket_field_title=ticket_field.title,
        )


class ZendeskBrandArtifactMetadata(BaseModel):
    brand_id: int
    brand_name: str

    @classmethod
    def from_api_brand(cls, brand: ZendeskBrand) -> "ZendeskBrandArtifactMetadata":
        return ZendeskBrandArtifactMetadata(
            brand_id=brand.id,
            brand_name=brand.name,
        )


class ZendeskOrganizationArtifactMetadata(BaseModel):
    organization_id: int
    organization_name: str

    @classmethod
    def from_api_organization(
        cls, organization: ZendeskOrganization
    ) -> "ZendeskOrganizationArtifactMetadata":
        return ZendeskOrganizationArtifactMetadata(
            organization_id=organization.id,
            organization_name=organization.name,
        )


class ZendeskCustomTicketStatusArtifactMetadata(BaseModel):
    custom_status_id: int
    agent_label: str

    @classmethod
    def from_api_custom_ticket_status(
        cls, custom_status: ZendeskCustomTicketStatus
    ) -> "ZendeskCustomTicketStatusArtifactMetadata":
        return ZendeskCustomTicketStatusArtifactMetadata(
            custom_status_id=custom_status.id,
            agent_label=custom_status.agent_label,
        )


class ZendeskTicketMetricsArtifactMetadata(BaseModel):
    ticket_metrics_id: int
    ticket_id: int

    @classmethod
    def from_api_ticket_metrics(
        cls, ticket_metrics: ZendeskTicketMetrics
    ) -> "ZendeskTicketMetricsArtifactMetadata":
        return ZendeskTicketMetricsArtifactMetadata(
            ticket_metrics_id=ticket_metrics.id,
            ticket_id=ticket_metrics.ticket_id,
        )


class ZendeskTicketAuditArtifactMetadata(BaseModel):
    ticket_audit_id: int
    ticket_id: int
    updater_id: int | None

    @classmethod
    def from_api_ticket_audit(
        cls, ticket_audit: ZendeskTicketAudit
    ) -> "ZendeskTicketAuditArtifactMetadata":
        return ZendeskTicketAuditArtifactMetadata(
            ticket_audit_id=ticket_audit.id,
            ticket_id=ticket_audit.ticket_id,
            updater_id=ticket_audit.updater_id,
        )


class ZendeskArticleArtifactMetadata(BaseModel):
    article_id: int
    author_id: int

    created_at: str
    updated_at: str

    @classmethod
    def from_api_article(cls, article: ZendeskArticle) -> "ZendeskArticleArtifactMetadata":
        return ZendeskArticleArtifactMetadata(
            article_id=article.id,
            author_id=article.author_id,
            created_at=article.created_at,
            updated_at=article.updated_at,
        )


class ZendeskCommentArtifactMetadata(BaseModel):
    comment_id: int
    source_id: int
    author_id: int

    created_at: str
    updated_at: str

    @classmethod
    def from_api_comment(cls, comment: ZendeskComment) -> "ZendeskCommentArtifactMetadata":
        return ZendeskCommentArtifactMetadata(
            comment_id=comment.id,
            source_id=comment.source_id,
            author_id=comment.author_id,
            created_at=comment.created_at,
            updated_at=comment.updated_at,
        )


class ZendeskCategoryArtifactMetadata(BaseModel):
    category_id: int

    created_at: str
    updated_at: str

    @classmethod
    def from_api_category(cls, category: ZendeskCategory) -> "ZendeskCategoryArtifactMetadata":
        return ZendeskCategoryArtifactMetadata(
            category_id=category.id,
            created_at=category.created_at,
            updated_at=category.updated_at,
        )


class ZendeskSectionArtifactMetadata(BaseModel):
    section_id: int
    category_id: int

    created_at: str
    updated_at: str

    @classmethod
    def from_api_section(cls, section: ZendeskSection) -> "ZendeskSectionArtifactMetadata":
        return ZendeskSectionArtifactMetadata(
            section_id=section.id,
            category_id=section.category_id,
            created_at=section.created_at,
            updated_at=section.updated_at,
        )


class ZendeskTicketArtifactMetadata(BaseModel):
    ticket_id: int
    brand_id: int | None
    requester_id: int | None
    submitter_id: int | None
    assignee_id: int | None
    organization_id: int | None
    group_id: int | None

    created_at: str
    updated_at: str

    @classmethod
    def from_api_ticket(cls, ticket: ZendeskTicket) -> "ZendeskTicketArtifactMetadata":
        return ZendeskTicketArtifactMetadata(
            ticket_id=ticket.id,
            brand_id=ticket.brand_id,
            requester_id=ticket.requester_id,
            submitter_id=ticket.submitter_id,
            assignee_id=ticket.assignee_id,
            organization_id=ticket.organization_id,
            group_id=ticket.group_id,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )


def zendesk_ticket_entity_id(ticket_id: int) -> str:
    return f"zendesk_ticket_{ticket_id}"


class ZendeskTicketArtifact(BaseIngestArtifact):
    """Typed Zendesk ticket artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ZENDESK_TICKET
    content: ZendeskTicket
    metadata: ZendeskTicketArtifactMetadata

    @classmethod
    def from_api_ticket(cls, ticket: ZendeskTicket, ingest_job_id: UUID) -> "ZendeskTicketArtifact":
        return ZendeskTicketArtifact(
            entity_id=zendesk_ticket_entity_id(ticket.id),
            content=ticket,
            metadata=ZendeskTicketArtifactMetadata.from_api_ticket(ticket),
            source_updated_at=datetime.fromisoformat(ticket.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_brand_entity_id(brand_id: int) -> str:
    return f"zendesk_brand_{brand_id}"


class ZendeskBrandArtifact(BaseIngestArtifact):
    """Typed Zendesk brand artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ZENDESK_BRAND
    content: ZendeskBrand
    metadata: ZendeskBrandArtifactMetadata

    @classmethod
    def from_api_brand(cls, brand: ZendeskBrand, ingest_job_id: UUID) -> "ZendeskBrandArtifact":
        return ZendeskBrandArtifact(
            entity_id=zendesk_brand_entity_id(brand.id),
            content=brand,
            metadata=ZendeskBrandArtifactMetadata.from_api_brand(brand),
            source_updated_at=datetime.fromisoformat(brand.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_organization_entity_id(organization_id: int) -> str:
    return f"zendesk_organization_{organization_id}"


class ZendeskOrganizationArtifact(BaseIngestArtifact):
    """Typed Zendesk organization artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ZENDESK_ORGANIZATION
    content: ZendeskOrganization
    metadata: ZendeskOrganizationArtifactMetadata

    @classmethod
    def from_api_organization(
        cls, organization: ZendeskOrganization, ingest_job_id: UUID
    ) -> "ZendeskOrganizationArtifact":
        return ZendeskOrganizationArtifact(
            entity_id=zendesk_organization_entity_id(organization.id),
            content=organization,
            metadata=ZendeskOrganizationArtifactMetadata.from_api_organization(organization),
            source_updated_at=datetime.fromisoformat(organization.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_group_entity_id(group_id: int) -> str:
    return f"zendesk_group_{group_id}"


class ZendeskGroupArtifact(BaseIngestArtifact):
    """Typed Zendesk group artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ZENDESK_GROUP
    content: ZendeskGroup
    metadata: ZendeskGroupArtifactMetadata

    @classmethod
    def from_api_group(cls, group: ZendeskGroup, ingest_job_id: UUID) -> "ZendeskGroupArtifact":
        return ZendeskGroupArtifact(
            entity_id=zendesk_group_entity_id(group.id),
            content=group,
            metadata=ZendeskGroupArtifactMetadata.from_api_group(group),
            source_updated_at=datetime.fromisoformat(group.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_user_entity_id(user_id: int) -> str:
    return f"zendesk_user_{user_id}"


class ZendeskUserArtifact(BaseIngestArtifact):
    """Typed Zendesk user artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ZENDESK_USER
    content: ZendeskUser
    metadata: ZendeskUserArtifactMetadata

    @classmethod
    def from_api_user(cls, user: ZendeskUser, ingest_job_id: UUID) -> "ZendeskUserArtifact":
        return ZendeskUserArtifact(
            entity_id=zendesk_user_entity_id(user.id),
            content=user,
            metadata=ZendeskUserArtifactMetadata.from_api_user(user),
            source_updated_at=datetime.fromisoformat(user.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_ticket_field_entity_id(ticket_field_id: int) -> str:
    return f"zendesk_ticket_field_{ticket_field_id}"


class ZendeskTicketFieldArtifact(BaseIngestArtifact):
    """Typed Zendesk ticket field artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ZENDESK_TICKET_FIELD
    content: ZendeskTicketField
    metadata: ZendeskTicketFieldArtifactMetadata

    @classmethod
    def from_api_ticket_field(
        cls, ticket_field: ZendeskTicketField, ingest_job_id: UUID
    ) -> "ZendeskTicketFieldArtifact":
        return ZendeskTicketFieldArtifact(
            entity_id=zendesk_ticket_field_entity_id(ticket_field.id),
            content=ticket_field,
            metadata=ZendeskTicketFieldArtifactMetadata.from_api_ticket_field(ticket_field),
            source_updated_at=datetime.fromisoformat(ticket_field.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_custom_status_entity_id(custom_status_id: int) -> str:
    return f"zendesk_custom_status_{custom_status_id}"


class ZendeskCustomTicketStatusArtifact(BaseIngestArtifact):
    """Typed Zendesk custom status artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ZENDESK_CUSTOM_STATUS
    content: ZendeskCustomTicketStatus
    metadata: ZendeskCustomTicketStatusArtifactMetadata

    @classmethod
    def from_api_custom_ticket_status(
        cls, custom_status: ZendeskCustomTicketStatus, ingest_job_id: UUID
    ) -> "ZendeskCustomTicketStatusArtifact":
        # Implement conversion from API model to artifact
        return ZendeskCustomTicketStatusArtifact(
            entity_id=zendesk_custom_status_entity_id(custom_status.id),
            content=custom_status,
            metadata=ZendeskCustomTicketStatusArtifactMetadata.from_api_custom_ticket_status(
                custom_status
            ),
            source_updated_at=datetime.fromisoformat(custom_status.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_ticket_metrics_entity_id(ticket_metrics_id: int) -> str:
    return f"zendesk_ticket_metrics_{ticket_metrics_id}"


class ZendeskTicketMetricsArtifact(BaseIngestArtifact):
    """Typed Zendesk ticket metric artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ZENDESK_TICKET_METRICS
    content: ZendeskTicketMetrics
    metadata: ZendeskTicketMetricsArtifactMetadata

    @classmethod
    def from_api_ticket_metrics(
        cls, ticket_metrics: ZendeskTicketMetrics, ingest_job_id: UUID
    ) -> "ZendeskTicketMetricsArtifact":
        return ZendeskTicketMetricsArtifact(
            entity_id=zendesk_ticket_metrics_entity_id(ticket_metrics.id),
            content=ticket_metrics,
            metadata=ZendeskTicketMetricsArtifactMetadata.from_api_ticket_metrics(ticket_metrics),
            source_updated_at=datetime.fromisoformat(ticket_metrics.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_ticket_audit_entity_id(ticket_audit_id: int) -> str:
    return f"zendesk_ticket_audit_{ticket_audit_id}"


class ZendeskTicketAuditArtifact(BaseIngestArtifact):
    """Typed Zendesk ticket audit artifact with validated content and metadata."""

    entity: ArtifactEntity = ArtifactEntity.ZENDESK_TICKET_AUDIT
    content: ZendeskTicketAudit
    metadata: ZendeskTicketAuditArtifactMetadata

    @classmethod
    def from_api_ticket_audit(
        cls, ticket_audit: ZendeskTicketAudit, ingest_job_id: UUID
    ) -> "ZendeskTicketAuditArtifact":
        return ZendeskTicketAuditArtifact(
            entity_id=zendesk_ticket_audit_entity_id(ticket_audit.id),
            content=ticket_audit,
            metadata=ZendeskTicketAuditArtifactMetadata.from_api_ticket_audit(ticket_audit),
            source_updated_at=datetime.fromisoformat(ticket_audit.created_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_article_entity_id(article_id: int) -> str:
    return f"zendesk_article_{article_id}"


class ZendeskArticleArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.ZENDESK_ARTICLE
    content: ZendeskArticle
    metadata: ZendeskArticleArtifactMetadata

    @classmethod
    def from_api_article(
        cls, article: ZendeskArticle, ingest_job_id: UUID
    ) -> "ZendeskArticleArtifact":
        return ZendeskArticleArtifact(
            entity_id=zendesk_article_entity_id(article.id),
            content=article,
            metadata=ZendeskArticleArtifactMetadata.from_api_article(article),
            source_updated_at=datetime.fromisoformat(article.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_comment_entity_id(comment_id: int) -> str:
    return f"zendesk_comment_{comment_id}"


class ZendeskCommentArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.ZENDESK_COMMENT
    content: ZendeskComment
    metadata: ZendeskCommentArtifactMetadata

    @classmethod
    def from_api_comment(
        cls, comment: ZendeskComment, ingest_job_id: UUID
    ) -> "ZendeskCommentArtifact":
        return ZendeskCommentArtifact(
            entity_id=zendesk_comment_entity_id(comment.id),
            content=comment,
            metadata=ZendeskCommentArtifactMetadata.from_api_comment(comment),
            source_updated_at=datetime.fromisoformat(comment.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_category_entity_id(category_id: int) -> str:
    return f"zendesk_category_{category_id}"


class ZendeskCategoryArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.ZENDESK_CATEGORY
    content: ZendeskCategory
    metadata: ZendeskCategoryArtifactMetadata

    @classmethod
    def from_api_category(
        cls, category: ZendeskCategory, ingest_job_id: UUID
    ) -> "ZendeskCategoryArtifact":
        return ZendeskCategoryArtifact(
            entity_id=zendesk_category_entity_id(category.id),
            content=category,
            metadata=ZendeskCategoryArtifactMetadata.from_api_category(category),
            source_updated_at=datetime.fromisoformat(category.updated_at),
            ingest_job_id=ingest_job_id,
        )


def zendesk_section_entity_id(section_id: int) -> str:
    return f"zendesk_section_{section_id}"


class ZendeskSectionArtifact(BaseIngestArtifact):
    entity: ArtifactEntity = ArtifactEntity.ZENDESK_SECTION
    content: ZendeskSection
    metadata: ZendeskSectionArtifactMetadata

    @classmethod
    def from_api_section(
        cls, section: ZendeskSection, ingest_job_id: UUID
    ) -> "ZendeskSectionArtifact":
        return ZendeskSectionArtifact(
            entity_id=zendesk_section_entity_id(section.id),
            content=section,
            metadata=ZendeskSectionArtifactMetadata.from_api_section(section),
            source_updated_at=datetime.fromisoformat(section.updated_at),
            ingest_job_id=ingest_job_id,
        )
