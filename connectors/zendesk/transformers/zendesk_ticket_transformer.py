from datetime import datetime

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.zendesk.client.zendesk_ticketing_models import (
    ZendeskMetricMinutes,
    ZendeskSatisfactionRating,
    ZendeskTicketAuditChangeEvent,
    ZendeskTicketAuditCommentEvent,
    ZendeskTicketAuditCreateEvent,
    ZendeskTicketAuditDefaultEvent,
    ZendeskTicketAuditEvent,
    ZendeskTicketCustomField,
)
from connectors.zendesk.extractors.zendesk_artifacts import (
    ZendeskBrandArtifact,
    ZendeskCustomTicketStatusArtifact,
    ZendeskGroupArtifact,
    ZendeskOrganizationArtifact,
    ZendeskTicketArtifact,
    ZendeskTicketAuditArtifact,
    ZendeskTicketFieldArtifact,
    ZendeskTicketMetricsArtifact,
    ZendeskUserArtifact,
    zendesk_brand_entity_id,
    zendesk_custom_status_entity_id,
    zendesk_group_entity_id,
    zendesk_organization_entity_id,
    zendesk_ticket_field_entity_id,
    zendesk_user_entity_id,
)
from connectors.zendesk.transformers.zendesk_ticket_document import (
    RawDataAudit,
    RawDataAuditChangeEvent,
    RawDataAuditCommentEvent,
    RawDataAuditCreateEvent,
    RawDataAuditEvent,
    RawDataNamed,
    RawDataSatisfactionRating,
    RawDataTicketCustomField,
    RawDataTicketCustomStatus,
    RawDataTicketMetrics,
    RawDataUser,
    ZendeskTicketDocument,
    ZendeskTicketDocumentRawData,
    zendesk_ticket_document_id,
)
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TicketHydrator:
    _user_by_id: dict[int, ZendeskUserArtifact]
    _group_by_id: dict[int, ZendeskGroupArtifact]
    _organization_by_id: dict[int, ZendeskOrganizationArtifact]
    _brand_by_id: dict[int, ZendeskBrandArtifact]
    _custom_status_by_id: dict[int, ZendeskCustomTicketStatusArtifact]
    _ticket_field_by_id: dict[int, ZendeskTicketFieldArtifact]
    _ticket_metrics_by_ticket_id: dict[int, ZendeskTicketMetricsArtifact]
    _ticket_audits_by_ticket_id: dict[int, list[ZendeskTicketAuditArtifact]]

    def __init__(
        self,
        user_by_id: dict[int, ZendeskUserArtifact],
        group_by_id: dict[int, ZendeskGroupArtifact],
        organization_by_id: dict[int, ZendeskOrganizationArtifact],
        brand_by_id: dict[int, ZendeskBrandArtifact],
        custom_status_by_id: dict[int, ZendeskCustomTicketStatusArtifact],
        ticket_field_by_id: dict[int, ZendeskTicketFieldArtifact],
        ticket_metrics_by_ticket_id: dict[int, ZendeskTicketMetricsArtifact],
        ticket_audits_by_ticket_id: dict[int, list[ZendeskTicketAuditArtifact]],
    ):
        self._user_by_id = user_by_id
        self._group_by_id = group_by_id
        self._organization_by_id = organization_by_id
        self._brand_by_id = brand_by_id
        self._custom_status_by_id = custom_status_by_id
        self._ticket_field_by_id = ticket_field_by_id
        self._ticket_metrics_by_ticket_id = ticket_metrics_by_ticket_id
        self._ticket_audits_by_ticket_id = ticket_audits_by_ticket_id

    def hydrate_ticket(self, ticket: ZendeskTicketArtifact) -> ZendeskTicketDocumentRawData:
        return ZendeskTicketDocumentRawData(
            id=ticket.content.id,
            subdomain=ticket.content.subdomain,
            description=ticket.content.description,
            subject=ticket.content.subject,
            type=ticket.content.type,
            status=ticket.content.status,
            priority=ticket.content.priority,
            tags=ticket.content.tags,
            due_at=ticket.content.due_at,
            created_at=ticket.content.created_at,
            updated_at=ticket.content.updated_at,
            satisfaction_rating=self._get_raw_data_satisfaction_rating(
                ticket.content.satisfaction_rating
            ),
            custom_fields=self._get_raw_data_custom_fields(ticket.content.custom_fields),
            custom_status=self._get_raw_data_custom_status(ticket.content.custom_status_id),
            brand=self._get_raw_data_brand(ticket.content.brand_id),
            organization=self._get_raw_data_organization(ticket.content.organization_id),
            group=self._get_raw_data_group(ticket.content.group_id),
            requester=self._get_raw_data_user(ticket.content.requester_id),
            submitter=self._get_raw_data_user(ticket.content.submitter_id),
            assignee=self._get_raw_data_user(ticket.content.assignee_id),
            collaborators=self._get_raw_data_users(ticket.content.collaborator_ids),
            followers=self._get_raw_data_users(ticket.content.follower_ids),
            metrics=self._get_raw_data_metrics(ticket.content.id),
            audits=self._get_raw_data_audits(ticket.content.id),
        )

    def _get_raw_data_user(self, user_id: int | None) -> RawDataUser | None:
        if user_id is None:
            return None

        user_artifact = self._user_by_id.get(user_id)

        return (
            RawDataUser(
                id=user_artifact.content.id,
                name=user_artifact.content.name,
                email=user_artifact.content.email,
            )
            if user_artifact
            else None
        )

    def _get_raw_data_users(self, user_ids: list[int]) -> list[RawDataUser]:
        return [
            u for u in [self._get_raw_data_user(user_id) for user_id in user_ids] if u is not None
        ]

    def _get_raw_data_brand(self, brand_id: int | None) -> RawDataNamed | None:
        if brand_id is None:
            return None

        brand_artifact = self._brand_by_id.get(brand_id)

        return (
            RawDataNamed(
                id=brand_artifact.content.id,
                name=brand_artifact.content.name,
            )
            if brand_artifact
            else None
        )

    def _get_raw_data_organization(self, organization_id: int | None) -> RawDataNamed | None:
        if organization_id is None:
            return None

        organization_artifact = self._organization_by_id.get(organization_id)

        return (
            RawDataNamed(
                id=organization_artifact.content.id,
                name=organization_artifact.content.name,
            )
            if organization_artifact
            else None
        )

    def _get_raw_data_group(self, group_id: int | None) -> RawDataNamed | None:
        if group_id is None:
            return None

        group_artifact = self._group_by_id.get(group_id)

        return (
            RawDataNamed(
                id=group_artifact.content.id,
                name=group_artifact.content.name,
            )
            if group_artifact
            else None
        )

    def _get_raw_data_custom_status(
        self, custom_status_id: int | None
    ) -> RawDataTicketCustomStatus | None:
        if custom_status_id is None:
            return None

        return RawDataTicketCustomStatus(
            id=custom_status_id,
            agent_label=self._custom_status_by_id[custom_status_id].content.agent_label
            if custom_status_id in self._custom_status_by_id
            else None,
        )

    def _get_raw_data_custom_fields(
        self, fields: list[ZendeskTicketCustomField]
    ) -> list[RawDataTicketCustomField]:
        return [
            RawDataTicketCustomField(
                id=field.id,
                title=self._ticket_field_by_id[field.id].content.title
                if field.id in self._ticket_field_by_id
                else None,
                value=field.value,
            )
            for field in fields
        ]

    def _get_raw_data_satisfaction_rating(
        self, rating: ZendeskSatisfactionRating
    ) -> RawDataSatisfactionRating:
        return RawDataSatisfactionRating(
            id=rating.id,
            score=rating.score,
            comment=rating.comment,
        )

    def _get_raw_data_metrics(self, ticket_id: int) -> RawDataTicketMetrics | None:
        metrics = self._ticket_metrics_by_ticket_id.get(ticket_id)
        if metrics is None:
            return None

        reply_time = metrics.content.reply_time_in_minutes
        first_resolution_time = metrics.content.first_resolution_time_in_minutes
        full_resolution_time = metrics.content.full_resolution_time_in_minutes
        agent_wait_time = metrics.content.agent_wait_time_in_minutes
        requester_wait_time = metrics.content.requester_wait_time_in_minutes
        on_hold_time = metrics.content.on_hold_time_in_minutes

        return RawDataTicketMetrics(
            group_stations=metrics.content.group_stations,
            assignee_stations=metrics.content.assignee_stations,
            reopens=metrics.content.reopens,
            replies=metrics.content.replies,
            assignee_updated_at=metrics.content.assignee_updated_at,
            requester_updated_at=metrics.content.requester_updated_at,
            status_updated_at=metrics.content.status_updated_at,
            initially_assigned_at=metrics.content.initially_assigned_at,
            assigned_at=metrics.content.assigned_at,
            solved_at=metrics.content.solved_at,
            latest_comment_added_at=metrics.content.latest_comment_added_at,
            custom_status_updated_at=metrics.content.custom_status_updated_at,
            reply_time_in_minutes=self._extract_business_minutes(reply_time),
            first_resolution_time_in_minutes=self._extract_business_minutes(first_resolution_time),
            full_resolution_time_in_minutes=self._extract_business_minutes(full_resolution_time),
            agent_wait_time_in_minutes=self._extract_business_minutes(agent_wait_time),
            requester_wait_time_in_minutes=self._extract_business_minutes(requester_wait_time),
            on_hold_time_in_minutes=self._extract_business_minutes(on_hold_time),
        )

    def _extract_business_minutes(self, metric_minutes: ZendeskMetricMinutes | None) -> int | None:
        if metric_minutes is None:
            return None
        return metric_minutes.business

    def _get_raw_data_audits(self, ticket_id: int) -> list[RawDataAudit]:
        audits = self._ticket_audits_by_ticket_id.get(ticket_id, [])

        raw_audits: list[RawDataAudit] = []
        for audit in audits:
            events = [self._get_raw_data_audit_event(event) for event in audit.content.child_events]
            handled_events = [event for event in events if event is not None]

            raw_audits.append(
                RawDataAudit(
                    id=audit.content.id,
                    created_at=audit.content.created_at,
                    updater=self._get_raw_data_user(audit.content.updater_id),
                    child_events=handled_events,
                )
            )
        return raw_audits

    def _get_raw_data_audit_event(self, event: ZendeskTicketAuditEvent) -> RawDataAuditEvent | None:
        match event:
            case ZendeskTicketAuditCreateEvent():
                return RawDataAuditCreateEvent(
                    id=event.id,
                    event_type=event.event_type,
                )
            case ZendeskTicketAuditChangeEvent():
                return RawDataAuditChangeEvent(
                    id=event.id,
                    event_type=event.event_type,
                )
            case ZendeskTicketAuditCommentEvent():
                return RawDataAuditCommentEvent(
                    id=event.id,
                    event_type=event.event_type,
                    body=event.body,
                    public=event.public,
                    author=self._get_raw_data_user(event.author_id),
                )
            case ZendeskTicketAuditDefaultEvent():
                return None


class ZendeskTicketTransformer(BaseTransformer[ZendeskTicketDocument]):
    def __init__(self):
        super().__init__(DocumentSource.ZENDESK_TICKET)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[ZendeskTicketDocument]:
        repo = ArtifactRepository(readonly_db_pool)

        ticket_artifacts = await repo.get_artifacts_by_entity_ids(ZendeskTicketArtifact, entity_ids)

        logger.info(
            f"Loaded {len(ticket_artifacts)} Zendesk ticket artifacts for {len(entity_ids)} entity IDs"
        )

        user_by_id = await self._get_user_artifacts_by_id(repo, ticket_artifacts)
        group_by_id = await self._get_group_artifacts_by_id(repo, ticket_artifacts)
        brand_by_id = await self._get_brand_artifacts_by_id(repo, ticket_artifacts)
        custom_status_by_id = await self._get_custom_status_artifacts_by_id(repo, ticket_artifacts)
        ticket_field_by_id = await self._get_ticket_field_artifacts_by_id(repo, ticket_artifacts)

        organization_by_id = await self._get_organization_artifacts_by_id(repo, ticket_artifacts)
        ticket_metrics_by_ticket_id = await self._get_ticket_metrics_artifacts_by_ticket_id(
            repo, ticket_artifacts
        )
        ticket_audits_by_ticket_id = await self._get_ticket_audit_artifacts_by_ticket_id(
            repo, ticket_artifacts
        )

        ticket_hydrator = TicketHydrator(
            user_by_id=user_by_id,
            group_by_id=group_by_id,
            organization_by_id=organization_by_id,
            brand_by_id=brand_by_id,
            custom_status_by_id=custom_status_by_id,
            ticket_field_by_id=ticket_field_by_id,
            ticket_metrics_by_ticket_id=ticket_metrics_by_ticket_id,
            ticket_audits_by_ticket_id=ticket_audits_by_ticket_id,
        )

        documents: list[ZendeskTicketDocument] = []
        counter: ErrorCounter = {}
        skipped_count = 0

        for artifact in ticket_artifacts:
            with record_exception_and_ignore(
                logger, f"Failed to transform artifact {artifact.id}", counter
            ):
                hydrated = ticket_hydrator.hydrate_ticket(artifact)
                document = self._create_document(artifact, hydrated)
                if document:
                    documents.append(document)
                    if len(documents) % 50 == 0:
                        logger.info(f"Processed {len(documents)}/{len(ticket_artifacts)} tickets")
                else:
                    skipped_count += 1
                    logger.warning(f"Skipped artifact {artifact.entity_id} - no document created")

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"Zendesk Ticket transformation complete: {successful} successful, {failed} failed, {skipped_count} skipped. "
            f"Created {len(documents)} documents from {len(ticket_artifacts)} artifacts"
        )

        return documents

    def _create_document(
        self, ticket: ZendeskTicketArtifact, raw_data: ZendeskTicketDocumentRawData
    ) -> ZendeskTicketDocument | None:
        return ZendeskTicketDocument(
            id=zendesk_ticket_document_id(ticket.content.id),
            raw_data=raw_data,
            source_updated_at=datetime.fromisoformat(ticket.content.updated_at),
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )

    async def _get_user_artifacts_by_id(
        self, repo: ArtifactRepository, ticket_artifacts: list[ZendeskTicketArtifact]
    ) -> dict[int, ZendeskUserArtifact]:
        user_ids = {
            ticket.content.requester_id
            for ticket in ticket_artifacts
            if ticket.content.requester_id is not None
        }
        user_entity_ids = [zendesk_user_entity_id(user_id) for user_id in user_ids]

        user_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskUserArtifact, user_entity_ids
        )

        return {user.content.id: user for user in user_artifacts}

    async def _get_group_artifacts_by_id(
        self, repo: ArtifactRepository, ticket_artifacts: list[ZendeskTicketArtifact]
    ) -> dict[int, ZendeskGroupArtifact]:
        group_ids = {
            ticket.content.group_id
            for ticket in ticket_artifacts
            if ticket.content.group_id is not None
        }
        group_entity_ids = [zendesk_group_entity_id(group_id) for group_id in group_ids]

        group_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskGroupArtifact, group_entity_ids
        )

        return {group.content.id: group for group in group_artifacts}

    async def _get_organization_artifacts_by_id(
        self, repo: ArtifactRepository, ticket_artifacts: list[ZendeskTicketArtifact]
    ) -> dict[int, ZendeskOrganizationArtifact]:
        organization_ids = {
            ticket.content.organization_id
            for ticket in ticket_artifacts
            if ticket.content.organization_id is not None
        }
        organization_entity_ids = [
            zendesk_organization_entity_id(org_id) for org_id in organization_ids
        ]

        organization_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskOrganizationArtifact, organization_entity_ids
        )

        return {org.content.id: org for org in organization_artifacts}

    async def _get_brand_artifacts_by_id(
        self, repo: ArtifactRepository, ticket_artifacts: list[ZendeskTicketArtifact]
    ) -> dict[int, ZendeskBrandArtifact]:
        brand_ids = {
            ticket.content.brand_id
            for ticket in ticket_artifacts
            if ticket.content.brand_id is not None
        }
        brand_entity_ids = [zendesk_brand_entity_id(brand_id) for brand_id in brand_ids]

        brand_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskBrandArtifact, brand_entity_ids
        )

        return {brand.content.id: brand for brand in brand_artifacts}

    async def _get_custom_status_artifacts_by_id(
        self, repo: ArtifactRepository, ticket_artifacts: list[ZendeskTicketArtifact]
    ) -> dict[int, ZendeskCustomTicketStatusArtifact]:
        custom_status_ids = {
            ticket.content.custom_status_id
            for ticket in ticket_artifacts
            if ticket.content.custom_status_id is not None
        }
        custom_status_entity_ids = [
            zendesk_custom_status_entity_id(status_id) for status_id in custom_status_ids
        ]

        custom_status_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskCustomTicketStatusArtifact, custom_status_entity_ids
        )

        return {status.content.id: status for status in custom_status_artifacts}

    async def _get_ticket_field_artifacts_by_id(
        self, repo: ArtifactRepository, ticket_artifacts: list[ZendeskTicketArtifact]
    ) -> dict[int, ZendeskTicketFieldArtifact]:
        ticket_field_ids = {
            field.id for ticket in ticket_artifacts for field in ticket.content.custom_fields
        }
        ticket_field_entity_ids = [
            zendesk_ticket_field_entity_id(field_id) for field_id in ticket_field_ids
        ]

        ticket_field_artifacts = await repo.get_artifacts_by_entity_ids(
            ZendeskTicketFieldArtifact, ticket_field_entity_ids
        )

        return {field.content.id: field for field in ticket_field_artifacts}

    async def _get_ticket_metrics_artifacts_by_ticket_id(
        self, repo: ArtifactRepository, ticket_artifacts: list[ZendeskTicketArtifact]
    ) -> dict[int, ZendeskTicketMetricsArtifact]:
        ticket_ids = {str(ticket.content.id) for ticket in ticket_artifacts}

        ticket_metrics_artifacts = await repo.get_artifacts_by_metadata_filter(
            ZendeskTicketMetricsArtifact,
            batches={"ticket_id": list(ticket_ids)},
        )

        return {metrics.content.ticket_id: metrics for metrics in ticket_metrics_artifacts}

    async def _get_ticket_audit_artifacts_by_ticket_id(
        self, repo: ArtifactRepository, ticket_artifacts: list[ZendeskTicketArtifact]
    ) -> dict[int, list[ZendeskTicketAuditArtifact]]:
        ticket_ids = {str(ticket.content.id) for ticket in ticket_artifacts}

        ticket_audit_artifacts = await repo.get_artifacts_by_metadata_filter(
            ZendeskTicketAuditArtifact,
            batches={"ticket_id": list(ticket_ids)},
        )

        audits_by_ticket_id: dict[int, list[ZendeskTicketAuditArtifact]] = {}
        for audit in ticket_audit_artifacts:
            audits_by_ticket_id.setdefault(audit.content.ticket_id, []).append(audit)

        # Ensure each list of audits is in chronological order
        for audits in audits_by_ticket_id.values():
            audits.sort(key=lambda audit: audit.content.created_at)

        return audits_by_ticket_id
