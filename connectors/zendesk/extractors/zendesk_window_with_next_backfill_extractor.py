import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.models import BackfillIngestConfig
from connectors.zendesk.client.zendesk_factory import get_zendesk_client_for_tenant
from connectors.zendesk.client.zendesk_models import DateWindow
from connectors.zendesk.extractors.zendesk_backfiller import (
    BackfillWindowResult,
    ZendeskBackfiller,
    ZendeskBackfillerConfig,
)
from connectors.zendesk.zendesk_service import ZendeskSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


# TODO: make this less arbitrary.. probably configured per tenant at some point?
_SYNC_AFTER = datetime(2015, 1, 1, tzinfo=UTC)


class ZendeskWindowWithNextBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["zendesk_window_with_next_backfill"] = "zendesk_window_with_next_backfill"

    start: str
    end: str | None


class ZendeskWindowWithNextBackfillExtractor(BaseExtractor[ZendeskWindowWithNextBackfillConfig]):
    """
    Backfill a window in time and enqueue the previous window for backfilling. Intentionally don't
    backfill context, assume the parent job has done that. If you want to backfill a single window
    with context use ZendeskBackfillWindowExtractor.
    """

    source_name = "zendesk_window_with_next_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: ZendeskWindowWithNextBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)

        logger.info(
            f"Started Zendesk window ({config.start}, {config.end}) backfill job",
            backfill_id=backfill_id,
        )

        config_start = datetime.fromisoformat(config.start).astimezone(UTC)
        config_end = datetime.fromisoformat(config.end).astimezone(UTC) if config.end else None

        if not _window_after_sync_after(config_start, config_end):
            logger.info(
                f"Skipped Zendesk window ({config.start}, {config.end}) backfill job, window is before sync_after",
                backfill_id=backfill_id,
                sync_after=_SYNC_AFTER,
            )
            return

        start, end = _clamp_window_to_sync_after(config_start, config_end)
        window = DateWindow(start=start, end=end)

        repository = ArtifactRepository(db_pool)
        zendesk_client = await get_zendesk_client_for_tenant(config.tenant_id, self.ssm_client)
        zendesk_service = ZendeskSyncService(db_pool)
        zendesk_backfiller = ZendeskBackfiller(
            api=zendesk_client,
            db=repository,
            service=zendesk_service,
            trigger_indexing=trigger_indexing,
            config=ZendeskBackfillerConfig(
                job_id=UUID(job_id),
                tenant_id=config.tenant_id,
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            ),
        )

        with LogContext(backfill_id=backfill_id):
            window_results = await zendesk_backfiller.backfill_window(window)
            await zendesk_service.set_synced_after(start)

        next_start, next_end = _get_next_start_end(
            previous_start=start,
            previous_end=end,
            previous_result=window_results,
        )

        await self.sqs_client.send_backfill_ingest_message(
            backfill_config=ZendeskWindowWithNextBackfillConfig(
                tenant_id=config.tenant_id,
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
                start=next_start.isoformat(),
                end=next_end.isoformat(),
            ),
        )

        total_duration = time.perf_counter() - start_time
        logger.info(
            f"Completed Zendesk window ({config.start}, {config.end}) backfill job, enqueued next window",
            backfill_id=backfill_id,
            total_duration=total_duration,
            next_start=next_start,
            next_end=next_end,
        )


_min_window_size = timedelta(days=1)
_max_window_size = timedelta(weeks=52)
_window_size_scale_factor = 3


def _clamp_window_to_sync_after(
    start: datetime, end: datetime | None
) -> tuple[datetime, datetime | None]:
    clamped_start = max(start, _SYNC_AFTER)
    clamped_end = max(end, _SYNC_AFTER) if end else None
    return clamped_start, clamped_end


def _window_after_sync_after(start: datetime, end: datetime | None) -> bool:
    return not end or end >= _SYNC_AFTER


def _clamp(value: timedelta, min_value: timedelta, max_value: timedelta) -> timedelta:
    return max(min_value, min(value, max_value))


def _get_next_start_end(
    previous_start: datetime, previous_end: datetime | None, previous_result: BackfillWindowResult
) -> tuple[datetime, datetime]:
    """
    Dynamically calculate a "next window" sized based on the previous results. This is mostly here
    to catch the case where there is almost no data (as we sync back in time the data will get
    sparser and sparser). OR to also handle large orgs where syncing a single week of data would
    take more than 10 mins.
    """

    previous_end = previous_end or datetime.now(tz=UTC)

    tickets_synced = len(previous_result.tickets_result.ticket_ids)
    ticket_events_synced = len(previous_result.ticket_events_result.ticket_audit_ids)
    articles_synced = len(previous_result.articles_result.article_ids)

    should_increase = (
        tickets_synced < 1000 and ticket_events_synced < 1000 and articles_synced < 1000
    )
    should_decrease = ticket_events_synced >= 5000

    previous_window_size = previous_end - previous_start
    next_window_size = previous_window_size
    if should_increase:
        next_window_size = previous_window_size * _window_size_scale_factor
    elif should_decrease:
        next_window_size = previous_window_size / _window_size_scale_factor

    next_window_size = _clamp(next_window_size, _min_window_size, _max_window_size)

    next_end = previous_start - timedelta(seconds=1)
    next_start = next_end - next_window_size

    return (next_start, next_end)
