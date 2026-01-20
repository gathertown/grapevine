import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.base.utils import split_even_chunks
from connectors.zendesk.client.zendesk_client import ZendeskClient
from connectors.zendesk.client.zendesk_models import DateWindow
from connectors.zendesk.client.zendesk_ticketing_models import ZendeskUser
from connectors.zendesk.extractors.zendesk_artifacts import (
    ZendeskArticleArtifact,
    ZendeskBrandArtifact,
    ZendeskCategoryArtifact,
    ZendeskCommentArtifact,
    ZendeskCustomTicketStatusArtifact,
    ZendeskGroupArtifact,
    ZendeskOrganizationArtifact,
    ZendeskSectionArtifact,
    ZendeskTicketArtifact,
    ZendeskTicketAuditArtifact,
    ZendeskTicketFieldArtifact,
    ZendeskTicketMetricsArtifact,
    ZendeskUserArtifact,
    zendesk_organization_entity_id,
    zendesk_ticket_entity_id,
    zendesk_user_entity_id,
)
from connectors.zendesk.zendesk_service import ZendeskSyncService
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ZendeskBackfillerConfig:
    tenant_id: str
    backfill_id: str
    suppress_notification: bool
    job_id: UUID


_SHOW_MANY_BATCH_SIZE = 100


@dataclass
class BackfillTicketsResult:
    ticket_ids: set[int]


@dataclass
class BackfillTicketEventsResult:
    ticket_audit_ids: set[int]


@dataclass
class BackfillArticlesResult:
    article_ids: set[int]


@dataclass
class BackfillWindowResult:
    tickets_result: BackfillTicketsResult
    ticket_events_result: BackfillTicketEventsResult
    articles_result: BackfillArticlesResult


class ZendeskBackfiller:
    api: ZendeskClient
    db: ArtifactRepository
    service: ZendeskSyncService
    trigger_indexing: TriggerIndexingCallback

    config: ZendeskBackfillerConfig

    def __init__(
        self,
        api: ZendeskClient,
        db: ArtifactRepository,
        service: ZendeskSyncService,
        trigger_indexing: TriggerIndexingCallback,
        config: ZendeskBackfillerConfig,
    ) -> None:
        self.api = api
        self.db = db
        self.service = service
        self.trigger_indexing = trigger_indexing
        self.config = config

    async def backfill_window(self, window: DateWindow) -> BackfillWindowResult:
        """
        Assumes everything in the future of this window has already been backfilled.
        """

        (
            initial_ticket_end_time,
            initial_ticket_events_start_time,
            initial_articles_start_time,
        ) = await asyncio.gather(
            self.service.get_window_tickets_end_time(window),
            self.service.get_window_ticket_events_start_time(window),
            self.service.get_window_articles_start_time(window),
        )

        async with asyncio.TaskGroup() as tg:
            backfill_tickets_task = tg.create_task(
                self._backfill_tickets_window(
                    window=window,
                    initial_end_time=initial_ticket_end_time,
                    on_earlier_end_time=lambda x: self.service.set_window_tickets_end_time(
                        window, x
                    ),
                    force_refetch_identities=False,
                )
            )
            backfill_ticket_events_task = tg.create_task(
                self._backfill_ticket_events_incr(
                    window=window,
                    initial_start_time=initial_ticket_events_start_time,
                    on_later_start_time=lambda x: self.service.set_window_ticket_events_start_time(
                        window, x
                    ),
                    force_refetch_identities=False,
                )
            )
            backfill_articles_task = tg.create_task(
                self._backfill_and_index_articles_incr(
                    window=window,
                    initial_start_time=initial_articles_start_time,
                    on_later_start_time=lambda x: self.service.set_window_articles_start_time(
                        window, x
                    ),
                    force_refetch_identities=False,
                )
            )

        await self._trigger_indexing_for_tickets_created_in(window)

        await asyncio.gather(
            self.service.set_window_tickets_end_time(window, None),
            self.service.set_window_ticket_events_start_time(window, None),
            self.service.set_window_articles_start_time(window, None),
        )

        return BackfillWindowResult(
            tickets_result=backfill_tickets_task.result(),
            ticket_events_result=backfill_ticket_events_task.result(),
            articles_result=backfill_articles_task.result(),
        )

    async def backfill_incremental(self) -> None:
        tickets_cursor, ticket_events_start_time, articles_start_time = await asyncio.gather(
            self.service.get_incremental_tickets_cursor(),
            self.service.get_incremental_ticket_events_start_time(),
            self.service.get_incremental_articles_start_time(),
        )

        hour_ago = datetime.now(UTC) - timedelta(hours=1)

        async with asyncio.TaskGroup() as tg:
            ticket_ids_task = tg.create_task(
                self._backfill_tickets_window_incr(
                    initial_start=int(hour_ago.timestamp()),
                    initial_cursor=tickets_cursor,
                    on_cursor=self.service.set_incremental_tickets_cursor,
                    force_refetch_identities=True,
                )
            )
            tg.create_task(
                self._backfill_ticket_events_incr(
                    window=DateWindow(start=hour_ago),
                    initial_start_time=ticket_events_start_time,
                    on_later_start_time=self.service.set_incremental_ticket_events_start_time,
                    force_refetch_identities=True,
                )
            )
            tg.create_task(
                self._backfill_and_index_articles_incr(
                    window=DateWindow(start=hour_ago),
                    initial_start_time=articles_start_time,
                    on_later_start_time=self.service.set_incremental_articles_start_time,
                    force_refetch_identities=True,
                )
            )

        entity_ids = [zendesk_ticket_entity_id(id) for id in ticket_ids_task.result().ticket_ids]
        if entity_ids:
            await self.trigger_indexing(
                entity_ids=entity_ids,
                source=DocumentSource.ZENDESK_TICKET,
                tenant_id=self.config.tenant_id,
                backfill_id=self.config.backfill_id,
                suppress_notification=self.config.suppress_notification,
            )

    async def backfill_context(self) -> None:
        start_perf_time = time.perf_counter()
        logger.info("Zendesk starting brands/groups/custom statuses/custom ticket fields backfill")

        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._backfill_ticket_fields())
            tg.create_task(self._backfill_brands())
            tg.create_task(self._backfill_custom_statuses())
            tg.create_task(self._backfill_groups())

        total_duration = time.perf_counter() - start_perf_time
        logger.info(
            "Zendesk completed brands/groups/custom statuses/custom ticket fields backfill",
            total_duration=total_duration,
        )

    async def _backfill_ticket_fields(self) -> None:
        async for page in self.api.list_ticket_fields():
            artifacts = [
                ZendeskTicketFieldArtifact.from_api_ticket_field(
                    ticket_field=field, ingest_job_id=self.config.job_id
                )
                for field in page.ticket_fields
            ]
            await self.db.upsert_artifacts_batch(artifacts)

    async def _backfill_brands(self) -> None:
        async for page in self.api.list_brands():
            artifacts = [
                ZendeskBrandArtifact.from_api_brand(brand=x, ingest_job_id=self.config.job_id)
                for x in page.brands
            ]
            await self.db.upsert_artifacts_batch(artifacts)

    async def _backfill_custom_statuses(self) -> None:
        response = await self.api.list_custom_statuses()

        artifacts = [
            ZendeskCustomTicketStatusArtifact.from_api_custom_ticket_status(
                custom_status=x, ingest_job_id=self.config.job_id
            )
            for x in response
        ]

        await self.db.upsert_artifacts_batch(artifacts)

    async def _backfill_groups(self) -> None:
        async for page in self.api.list_groups():
            artifacts = [
                ZendeskGroupArtifact.from_api_group(group=x, ingest_job_id=self.config.job_id)
                for x in page.groups
            ]
            await self.db.upsert_artifacts_batch(artifacts)

    async def _backfill_tickets_window(
        self,
        window: DateWindow,
        initial_end_time: datetime | None,
        on_earlier_end_time: Callable[[datetime], Awaitable[None]],
        force_refetch_identities: bool,
    ) -> BackfillTicketsResult:
        end_time = window.end

        # an 'initial_end_time' can be provided to resume partway through a window
        if initial_end_time and window.contains(initial_end_time):
            end_time = initial_end_time

        sliced_window = DateWindow(start=window.start, end=end_time)

        cursor = None
        has_more = True

        all_ticket_ids = set[int]()

        while has_more:
            page_start_perf_time = time.perf_counter()

            response = await self.api.search_tickets_window(sliced_window, cursor)
            windowed_tickets = [
                ticket
                for ticket in response.results
                if not sliced_window.end
                or datetime.fromisoformat(ticket.created_at) < sliced_window.end
            ]

            artifacts = [
                ZendeskTicketArtifact.from_api_ticket(ticket, self.config.job_id)
                for ticket in windowed_tickets
            ]

            user_ids = {user_id for ticket in windowed_tickets for user_id in ticket.get_user_ids()}
            organization_ids = {
                ticket.organization_id
                for ticket in windowed_tickets
                if ticket.organization_id is not None
            }
            ticket_ids = {ticket.id for ticket in windowed_tickets}
            all_ticket_ids.update(ticket_ids)

            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.db.upsert_artifacts_batch(artifacts))
                metrics_task = tg.create_task(self._backfill_metrics(ticket_ids))
                users_task = tg.create_task(
                    self._backfill_users(user_ids, force_refetch=force_refetch_identities)
                )
                org_task = tg.create_task(
                    self._backfill_organizations(
                        organization_ids, force_refetch=force_refetch_identities
                    )
                )

            if windowed_tickets:
                earliest_created_at = datetime.fromisoformat(windowed_tickets[-1].created_at)
                await on_earlier_end_time(earliest_created_at)

            page_duration = time.perf_counter() - page_start_perf_time
            logger.info(
                "Zendesk backfilled ticket page",
                page_duration=page_duration,
                ticket_artifact_count=len(artifacts),
                organization_artifact_count=org_task.result(),
                metrics_artifact_count=metrics_task.result(),
                user_artifact_count=users_task.result(),
            )

            hit_window_end = len(response.results) != len(windowed_tickets)
            if hit_window_end:
                break

            has_more = response.meta.has_more
            cursor = response.meta.after_cursor

        return BackfillTicketsResult(ticket_ids=all_ticket_ids)

    async def _backfill_tickets_window_incr(
        self,
        initial_start: int,
        initial_cursor: str | None,
        on_cursor: Callable[[str], Awaitable[None]],
        force_refetch_identities: bool,
    ) -> BackfillTicketsResult:
        cursor = initial_cursor
        has_more = True

        all_ticket_ids = set[int]()

        while has_more:
            page_start_perf_time = time.perf_counter()

            if cursor:
                response = await self.api.incremental_tickets(cursor=cursor)
            else:
                response = await self.api.incremental_tickets(start_time=initial_start)

            artifacts = [
                ZendeskTicketArtifact.from_api_ticket(ticket, self.config.job_id)
                for ticket in response.tickets
            ]

            user_ids = {user_id for ticket in response.tickets for user_id in ticket.get_user_ids()}
            organization_ids = {
                ticket.organization_id
                for ticket in response.tickets
                if ticket.organization_id is not None
            }
            ticket_ids = {ticket.id for ticket in response.tickets}
            all_ticket_ids.update(ticket_ids)

            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.db.upsert_artifacts_batch(artifacts))
                org_task = tg.create_task(
                    self._backfill_organizations(
                        organization_ids, force_refetch=force_refetch_identities
                    )
                )
                metrics_task = tg.create_task(self._backfill_metrics(ticket_ids))
                user_task = tg.create_task(
                    self._backfill_users(user_ids, force_refetch=force_refetch_identities)
                )

            if response.after_cursor:
                await on_cursor(response.after_cursor)

            has_more = not response.end_of_stream
            cursor = response.after_cursor

            page_duration = time.perf_counter() - page_start_perf_time
            logger.info(
                "Zendesk backfilled ticket page (incr)",
                page_duration=page_duration,
                ticket_artifact_count=len(artifacts),
                organization_artifact_count=org_task.result(),
                metrics_artifact_count=metrics_task.result(),
                user_artifact_count=user_task.result(),
            )

        return BackfillTicketsResult(ticket_ids=all_ticket_ids)

    async def _backfill_ticket_events_incr(
        self,
        window: DateWindow,
        initial_start_time: int | None,
        on_later_start_time: Callable[[int], Awaitable[None]],
        force_refetch_identities: bool,
    ) -> BackfillTicketEventsResult:
        if not window.start:
            raise ValueError("A window with a start must be provided")

        start_time = int(window.start.timestamp())

        # an 'initial_start_time' can be provided to resume partway through a window
        if initial_start_time:
            if window.contains(datetime.fromtimestamp(initial_start_time).astimezone(UTC)):
                start_time = initial_start_time
            else:
                logger.warning(
                    "initial_start_time is outside the provided window, defaulting to window.start",
                    initial_start_time=initial_start_time,
                    window=str(window),
                )

        all_ticket_audit_ids = set[int]()
        has_more = True

        while has_more:
            page_start_perf_time = time.perf_counter()

            response = await self.api.incremental_ticket_events(start_time=start_time)
            windowed_ticket_events = [
                event
                for event in response.ticket_events
                if not window.end or (event.timestamp < int(window.end.timestamp()))
            ]

            artifacts = [
                ZendeskTicketAuditArtifact.from_api_ticket_audit(audit, self.config.job_id)
                for audit in windowed_ticket_events
            ]

            ticket_audit_ids = {te.id for te in windowed_ticket_events}
            user_ids = {
                event.updater_id for event in windowed_ticket_events if event.updater_id is not None
            }
            all_ticket_audit_ids.update(ticket_audit_ids)

            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.db.upsert_artifacts_batch(artifacts))
                users_task = tg.create_task(
                    self._backfill_users(user_ids, force_refetch=force_refetch_identities)
                )

            if response.end_time:
                await on_later_start_time(response.end_time)

            page_duration = time.perf_counter() - page_start_perf_time
            logger.info(
                "Zendesk backfilled ticket events page",
                page_duration=page_duration,
                ticket_audit_artifact_count=len(artifacts),
                user_artifact_count=users_task.result(),
            )

            hit_window_end = len(response.ticket_events) != len(windowed_ticket_events)
            if hit_window_end:
                break

            # if the page boundary perfectly lines up the final page is empty and end_time is null
            if response.end_time:
                start_time = response.end_time

            has_more = not response.end_of_stream

        return BackfillTicketEventsResult(ticket_audit_ids=all_ticket_audit_ids)

    async def _backfill_and_index_articles_incr(
        self,
        window: DateWindow,
        initial_start_time: int | None,
        on_later_start_time: Callable[[int], Awaitable[None]],
        force_refetch_identities: bool,
    ) -> BackfillArticlesResult:
        if not window.start:
            raise ValueError("A window with a start must be provided")

        start_time = window.start

        # an 'initial_start_time' can be provided to resume partway through a window
        if initial_start_time:
            initial_start_time_dt = datetime.fromtimestamp(initial_start_time).astimezone(UTC)
            if window.contains(initial_start_time_dt):
                start_time = initial_start_time_dt
            else:
                logger.warning(
                    "initial_start_time is outside the provided window, defaulting to window.start",
                    initial_start_time=initial_start_time,
                    window=str(window),
                )

        all_article_ids = set[int]()

        page_start_perf_time = time.perf_counter()
        async for article_page in self.api.incremental_articles(
            start_time=start_time, end_time=window.end
        ):
            article_artifacts = [
                ZendeskArticleArtifact.from_api_article(article, self.config.job_id)
                for article in article_page.articles
            ]
            category_artifacts = [
                ZendeskCategoryArtifact.from_api_category(category, self.config.job_id)
                for category in article_page.categories
            ]
            section_artifacts = [
                ZendeskSectionArtifact.from_api_section(section, self.config.job_id)
                for section in article_page.sections
            ]
            all_artifacts = article_artifacts + category_artifacts + section_artifacts

            article_ids = {article.id for article in article_page.articles}
            user_ids = {article.author_id for article in article_page.articles}
            all_article_ids.update(article_ids)

            async with asyncio.TaskGroup() as tg:
                tg.create_task(self.db.upsert_artifacts_batch(all_artifacts))
                users_task = tg.create_task(
                    self._backfill_users(user_ids, force_refetch=force_refetch_identities)
                )
                comments_task = tg.create_task(
                    self._backfill_comments_for_articles(
                        article_ids,
                        force_refetch_identities=force_refetch_identities,
                    )
                )

            article_entity_ids = [aa.entity_id for aa in article_artifacts]
            await self.trigger_indexing(
                entity_ids=article_entity_ids,
                source=DocumentSource.ZENDESK_ARTICLE,
                tenant_id=self.config.tenant_id,
                backfill_id=self.config.backfill_id,
                suppress_notification=self.config.suppress_notification,
            )

            if article_page.end_time:
                await on_later_start_time(article_page.end_time)

            page_duration = time.perf_counter() - page_start_perf_time
            page_start_perf_time = time.perf_counter()

            logger.info(
                "Zendesk backfilled articles page",
                article_artifact_count=len(article_artifacts),
                category_artifact_count=len(category_artifacts),
                section_artifact_count=len(section_artifacts),
                user_artifact_count=users_task.result(),
                comment_artifact_count=comments_task.result(),
                duration=page_duration,
            )

        return BackfillArticlesResult(article_ids=all_article_ids)

    async def _backfill_comments_for_articles(
        self, article_ids: set[int], force_refetch_identities: bool
    ) -> int:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(
                    self._backfill_comments_for_article(
                        article_id,
                        force_refetch_identities=force_refetch_identities,
                    )
                )
                for article_id in article_ids
            ]

        return sum(task.result() for task in tasks)

    async def _backfill_comments_for_article(
        self, article_id: int, force_refetch_identities: bool
    ) -> int:
        artifact_count = 0

        async for comment_page in self.api.list_article_comments(article_id):
            await self._backfill_users(
                {comment.author_id for comment in comment_page.comments},
                force_refetch=force_refetch_identities,
            )

            artifacts = [
                ZendeskCommentArtifact.from_api_comment(
                    comment=comment, ingest_job_id=self.config.job_id
                )
                for comment in comment_page.comments
            ]

            await self.db.upsert_artifacts_batch(artifacts)

            artifact_count += len(artifacts)

        return artifact_count

    async def _backfill_users(self, all_user_ids: set[int], force_refetch: bool) -> int:
        """backfill all missing users, optionally force refetch all for incremental backfills"""
        valid_user_ids = {user_id for user_id in all_user_ids if user_id != -1}

        if force_refetch:
            user_ids_to_fetch = list(valid_user_ids)
        else:
            user_artifacts = await self.db.get_artifacts_by_entity_ids(
                artifact_class=ZendeskUserArtifact,
                entity_ids=[zendesk_user_entity_id(user_id) for user_id in valid_user_ids],
            )

            existing_ids = [artifact.metadata.user_id for artifact in user_artifacts]
            new_ids = valid_user_ids.difference(existing_ids)
            user_ids_to_fetch = list(new_ids)

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._backfill_user_batch(batch))
                for batch in split_even_chunks(user_ids_to_fetch, _SHOW_MANY_BATCH_SIZE)
            ]

        return sum(task.result() for task in tasks)

    async def _backfill_user_batch(self, user_ids: list[int]) -> int:
        response = await self.api.show_users(user_ids)

        found_artifacts = [
            ZendeskUserArtifact.from_api_user(user=user, ingest_job_id=self.config.job_id)
            for user in response
        ]
        found_user_ids = {user.id for user in response}

        # Deleted users aren't returned from show_many, you can see them via /users/:id. Mark them
        # in the db to prevent repeatedly refetching.
        deleted_user_artifacts = [
            ZendeskUserArtifact.from_api_user(
                user=ZendeskUser(
                    id=user_id,
                    name="Permanently deleted user",
                    email=None,
                    role=None,
                    created_at=datetime.fromtimestamp(0).isoformat(),
                    updated_at=datetime.fromtimestamp(0).isoformat(),
                ),
                ingest_job_id=self.config.job_id,
            )
            for user_id in user_ids
            if user_id not in found_user_ids
        ]

        artifacts = found_artifacts + deleted_user_artifacts

        await self.db.upsert_artifacts_batch(artifacts)

        return len(artifacts)

    async def _backfill_organizations(
        self, all_organization_ids: set[int], force_refetch: bool
    ) -> int:
        """backfill all missing organizations, optionally force refetch all for incremental backfills"""
        valid_org_ids = {org_id for org_id in all_organization_ids if org_id != -1}

        if force_refetch:
            organization_ids = list(valid_org_ids)
        else:
            organization_artifacts = await self.db.get_artifacts_by_entity_ids(
                artifact_class=ZendeskOrganizationArtifact,
                entity_ids=[zendesk_organization_entity_id(org_id) for org_id in valid_org_ids],
            )

            existing_ids = [
                artifact.metadata.organization_id for artifact in organization_artifacts
            ]
            new_ids = valid_org_ids.difference(existing_ids)
            organization_ids = list(new_ids)

        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._backfill_organization_batch(batch))
                for batch in split_even_chunks(organization_ids, _SHOW_MANY_BATCH_SIZE)
            ]

        return sum(task.result() for task in tasks)

    async def _backfill_organization_batch(self, organization_ids: list[int]) -> int:
        response = await self.api.show_organizations(organization_ids)

        artifacts = [
            ZendeskOrganizationArtifact.from_api_organization(
                organization=org, ingest_job_id=self.config.job_id
            )
            for org in response
        ]

        await self.db.upsert_artifacts_batch(artifacts)

        return len(artifacts)

    async def _backfill_metrics(self, ticket_ids: set[int]) -> int:
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(self._backfill_metrics_batch(batch))
                for batch in split_even_chunks(list(ticket_ids), _SHOW_MANY_BATCH_SIZE)
            ]

        return sum(task.result() for task in tasks)

    async def _backfill_metrics_batch(self, ticket_ids: list[int]) -> int:
        response = await self.api.show_metrics_for_tickets(ticket_ids)

        artifacts = [
            ZendeskTicketMetricsArtifact.from_api_ticket_metrics(
                ticket_metrics=metric_set, ingest_job_id=self.config.job_id
            )
            for metric_set in response
        ]

        await self.db.upsert_artifacts_batch(artifacts)

        return len(artifacts)

    async def _trigger_indexing_for_tickets_created_in(self, window: DateWindow) -> None:
        start = window.start or datetime.fromtimestamp(0).astimezone(UTC)
        end = window.end or datetime.now(UTC)

        artifacts = await self.db.get_artifacts_by_metadata_filter(
            artifact_class=ZendeskTicketArtifact, ranges={"created_at": (start, end)}
        )

        logger.info(
            f"Triggering indexing for {len(artifacts)} tickets created ({start}, {end}) inclusive",
        )

        entity_ids = [artifact.entity_id for artifact in artifacts]

        for batch in split_even_chunks(entity_ids, 1000):
            await self.trigger_indexing(
                entity_ids=batch,
                source=DocumentSource.ZENDESK_TICKET,
                tenant_id=self.config.tenant_id,
                backfill_id=self.config.backfill_id,
                suppress_notification=self.config.suppress_notification,
            )
