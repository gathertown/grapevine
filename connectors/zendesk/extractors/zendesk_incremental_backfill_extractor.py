import secrets
import time
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
from connectors.zendesk.zendesk_service import ZendeskSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class ZendeskIncrementalBackfillConfig(BackfillIngestConfig, frozen=True):
    source: Literal["zendesk_incremental_backfill"] = "zendesk_incremental_backfill"


class ZendeskIncrementalBackfillExtractor(BaseExtractor[ZendeskIncrementalBackfillConfig]):
    source_name = "zendesk_incremental_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.sqs_client = sqs_client
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: ZendeskIncrementalBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = secrets.token_hex(8)
        logger.info(
            "Processing Zendesk incremental backfill job",
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

        with LogContext(backfill_id=backfill_id):
            await zendesk_backfiller.backfill_context()
            await zendesk_backfiller.backfill_incremental()

        total_duration = time.perf_counter() - start_time

        logger.info(
            "Zendesk incremental backfill job completed",
            backfill_id=backfill_id,
            total_duration=total_duration,
        )
