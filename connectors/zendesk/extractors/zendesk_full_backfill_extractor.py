import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.models import BackfillIngestConfig
from connectors.zendesk.client.zendesk_factory import get_zendesk_client_for_tenant
from connectors.zendesk.extractors.zendesk_backfiller import (
    ZendeskBackfiller,
    ZendeskBackfillerConfig,
)
from connectors.zendesk.extractors.zendesk_window_with_next_backfill_extractor import (
    ZendeskWindowWithNextBackfillConfig,
)
from connectors.zendesk.zendesk_service import ZendeskSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class ZendeskFullBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["zendesk_full_backfill"] = "zendesk_full_backfill"


class ZendeskFullBackfillExtractor(BaseExtractor[ZendeskFullBackfillConfig]):
    source_name = "zendesk_full_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: ZendeskFullBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)
        logger.info("Started Zendesk full backfill job", backfill_id=backfill_id)

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

        synced_after = await zendesk_service.get_synced_after()

        week_ago = datetime.now(tz=UTC) - timedelta(weeks=1)

        # Pick up before tickets_synced_after or default to last week
        start = synced_after - timedelta(weeks=1) if synced_after else week_ago
        end = synced_after - timedelta(seconds=1) if synced_after else None

        # backfill quick-to-fetch context and then kick off the first window_next backfill
        with LogContext(backfill_id=backfill_id):
            await zendesk_backfiller.backfill_context()
        await self.sqs_client.send_backfill_ingest_message(
            backfill_config=ZendeskWindowWithNextBackfillConfig(
                tenant_id=config.tenant_id,
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
                start=start.isoformat(),
                end=end.isoformat() if end else None,
            )
        )

        total_duration = time.perf_counter() - start_time
        logger.info(
            "Completed Zendesk full backfill job", backfill_id=backfill_id, duration=total_duration
        )
