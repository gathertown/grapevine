import asyncio
import logging
import secrets

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.salesforce.salesforce_artifacts import SALESFORCE_OBJECT_TYPES
from connectors.salesforce.salesforce_models import (
    SalesforceBackfillConfig,
    SalesforceBackfillRootConfig,
    SalesforceObjectBatch,
)
from src.clients.salesforce_factory import get_salesforce_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = logging.getLogger(__name__)

# Number of records per child job. We want this to be high enough to minimize Salesforce API requests (which have limits)
CHILD_JOB_BATCH_SIZE = 400

# Maximum concurrent SQS operations
MAX_CONCURRENT_SQS_OPERATIONS = 100


class SalesforceBackfillRootExtractor(BaseExtractor[SalesforceBackfillRootConfig]):
    """
    Extracts Salesforce objects from all specified types and sends child jobs to process them.
    """

    source_name = "salesforce_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        # Semaphore to limit concurrent SQS operations
        self._sqs_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SQS_OPERATIONS)

    async def process_job(
        self,
        job_id: str,
        config: SalesforceBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # Generate a unique backfill ID for this root job
        backfill_id = secrets.token_hex(8)
        logger.info(
            f"Processing Salesforce backfill_id {backfill_id} for tenant {config.tenant_id}"
        )

        # Get Salesforce client for this tenant
        salesforce_client = await get_salesforce_client_for_tenant(
            config.tenant_id, self.ssm_client, db_pool
        )

        # Collect record IDs for all object types
        all_object_batches = []

        for object_type in SALESFORCE_OBJECT_TYPES:
            logger.info(f"Discovering {object_type} records for tenant {config.tenant_id}")

            try:
                # Get all record IDs for this object type
                record_ids = await salesforce_client.get_all_object_ids(object_type)
                logger.info(f"Found {len(record_ids)} {object_type} records")

                # Split records into batches
                for i in range(0, len(record_ids), CHILD_JOB_BATCH_SIZE):
                    batch_record_ids = record_ids[i : i + CHILD_JOB_BATCH_SIZE]

                    object_batch = SalesforceObjectBatch(
                        object_type=object_type,
                        record_ids=batch_record_ids,
                    )

                    all_object_batches.append(object_batch)

            except Exception as e:
                logger.error(f"Failed to discover {object_type} records: {e}")
                raise

        logger.info(
            f"Root job {job_id} found {len(all_object_batches)} object batches across "
            f"{len(SALESFORCE_OBJECT_TYPES)} object types with backfill_id {backfill_id}"
        )

        # Send child jobs for processing
        if all_object_batches:
            # Track total number of ingest jobs (child batches) for this backfill
            await increment_backfill_total_ingest_jobs(
                backfill_id, config.tenant_id, len(all_object_batches)
            )

            await self._send_child_jobs(config, all_object_batches, backfill_id)
            logger.info(f"Sent child jobs for {len(all_object_batches)} object batches")

        # Clean up client resources
        await salesforce_client.close()

        logger.info(f"Successfully completed root job {job_id}")

    async def _send_child_jobs(
        self,
        config: SalesforceBackfillRootConfig,
        object_batches: list[SalesforceObjectBatch],
        backfill_id: str,
    ) -> None:
        """Send child jobs to process object batches."""
        total_batches = len(object_batches)
        logger.info(f"Preparing to send child jobs for {total_batches} object batches")

        # Create all child job tasks
        tasks = []
        for i, object_batch in enumerate(object_batches):
            child_config = SalesforceBackfillConfig(
                tenant_id=config.tenant_id,
                object_batches=[object_batch],
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )

            # Create task to send this batch
            task = self._send_single_child_job(child_config, i)
            tasks.append(task)

        # Send all child jobs in parallel
        logger.info(f"Sending {len(tasks)} child jobs to process {total_batches} object batches...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        jobs_sent = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send child job batch {i}: {result}")
                raise result
            jobs_sent += 1

        logger.info(f"Sent {jobs_sent} child jobs to process {total_batches} object batches!")

    async def _send_single_child_job(
        self,
        child_config: SalesforceBackfillConfig,
        batch_index: int,
    ) -> None:
        """Send a single child job message to SQS."""
        # Use semaphore to limit concurrent SQS operations
        async with self._sqs_semaphore:
            success = await self.sqs_client.send_backfill_ingest_message(
                backfill_config=child_config,
            )

            if not success:
                raise RuntimeError(f"Failed to send child job batch {batch_index} to SQS")

            log = logger.info if batch_index % 100 == 0 else logger.debug
            log(
                f"Sent child job batch {batch_index} with {len(child_config.object_batches)} object batches"
            )
