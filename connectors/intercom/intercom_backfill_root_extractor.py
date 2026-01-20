"""Root extractor that orchestrates all Intercom backfill jobs."""

import secrets

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.intercom.intercom_models import (
    IntercomApiBackfillRootConfig,
    IntercomApiCompaniesBackfillConfig,
    IntercomApiContactsBackfillConfig,
    IntercomApiConversationsBackfillConfig,
    IntercomApiHelpCenterBackfillConfig,
)
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)

# Number of child jobs spawned by the root extractor
NUM_CHILD_JOBS = 4  # companies, contacts, conversations, help_center


class IntercomBackfillRootExtractor(BaseExtractor[IntercomApiBackfillRootConfig]):
    """Root extractor that triggers all Intercom backfill jobs.

    This extractor sends child jobs to SQS for:
    - Companies
    - Contacts
    - Conversations
    - Help Center articles

    All child jobs share the same backfill_id for unified tracking and notification.
    """

    source_name = "intercom_api_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: IntercomApiBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or secrets.token_hex(8)
        logger.info("Starting Intercom backfill root job", backfill_id=backfill_id)

        # Create and send child jobs for all Intercom data types
        companies_config = IntercomApiCompaniesBackfillConfig(
            tenant_id=config.tenant_id,
            backfill_id=backfill_id,
            suppress_notification=config.suppress_notification,
        )
        await self.sqs_client.send_backfill_ingest_message(companies_config)
        logger.info("Sent companies backfill job", backfill_id=backfill_id)

        contacts_config = IntercomApiContactsBackfillConfig(
            tenant_id=config.tenant_id,
            backfill_id=backfill_id,
            suppress_notification=config.suppress_notification,
        )
        await self.sqs_client.send_backfill_ingest_message(contacts_config)
        logger.info("Sent contacts backfill job", backfill_id=backfill_id)

        conversations_config = IntercomApiConversationsBackfillConfig(
            tenant_id=config.tenant_id,
            backfill_id=backfill_id,
            suppress_notification=config.suppress_notification,
        )
        await self.sqs_client.send_backfill_ingest_message(conversations_config)
        logger.info("Sent conversations backfill job", backfill_id=backfill_id)

        help_center_config = IntercomApiHelpCenterBackfillConfig(
            tenant_id=config.tenant_id,
            backfill_id=backfill_id,
            suppress_notification=config.suppress_notification,
        )
        await self.sqs_client.send_backfill_ingest_message(help_center_config)
        logger.info("Sent help center backfill job", backfill_id=backfill_id)

        # Track total number of child ingest jobs for this backfill
        await increment_backfill_total_ingest_jobs(backfill_id, config.tenant_id, NUM_CHILD_JOBS)

        logger.info(
            "Intercom backfill root job completed - all child jobs sent",
            backfill_id=backfill_id,
            num_child_jobs=NUM_CHILD_JOBS,
        )
