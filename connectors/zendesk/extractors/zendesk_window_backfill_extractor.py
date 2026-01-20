import secrets
import time
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.models import BackfillIngestConfig
from connectors.zendesk.client.zendesk_factory import get_zendesk_client_for_tenant
from connectors.zendesk.client.zendesk_models import DateWindow
from connectors.zendesk.extractors.zendesk_backfiller import (
    ZendeskBackfiller,
    ZendeskBackfillerConfig,
)
from connectors.zendesk.zendesk_service import ZendeskSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class ZendeskWindowBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["zendesk_window_backfill"] = "zendesk_window_backfill"

    start: str | None
    end: str | None


class ZendeskWindowBackfillExtractor(BaseExtractor[ZendeskWindowBackfillConfig]):
    source_name = "zendesk_window_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: ZendeskWindowBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = secrets.token_hex(8)

        logger.info(
            f"Starting single Zendesk window ({config.start}, {config.end}) backfill job",
            backfill_id=backfill_id,
        )

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

        if not config.start:
            logger.warning(
                "No start date provided for Zendesk window backfill",
                backfill_id=backfill_id,
            )
        if not config.end:
            logger.warning(
                "No end date provided for Zendesk window backfill",
                backfill_id=backfill_id,
            )

        start = datetime.fromisoformat(config.start).astimezone(UTC) if config.start else None
        end = datetime.fromisoformat(config.end).astimezone(UTC) if config.end else None
        window = DateWindow(start=start, end=end)

        with LogContext(backfill_id=backfill_id):
            await zendesk_backfiller.backfill_context()
            await zendesk_backfiller.backfill_window(window)

        total_duration = time.perf_counter() - start_time

        logger.info(
            f"Completed single Zendesk window ({config.start}, {config.end}) backfill job",
            backfill_id=backfill_id,
            total_duration=total_duration,
        )
