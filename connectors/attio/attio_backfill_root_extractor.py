"""Root extractor that orchestrates all Attio backfill jobs with batch splitting."""

import secrets
from datetime import UTC, datetime, timedelta

import asyncpg
import requests

from connectors.attio.attio_artifacts import AttioObjectType
from connectors.attio.attio_models import (
    AttioBackfillRootConfig,
    AttioCompanyBackfillConfig,
    AttioDealBackfillConfig,
    AttioPersonBackfillConfig,
)
from connectors.base import BaseExtractor, TriggerIndexingCallback
from src.clients.attio import AttioClient, get_attio_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.services.attio import attio_object_sync_service
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)

# Batch size (records) per child job
BATCH_SIZE = 100

# Attio API rate limits: 100 reads/sec, 25 writes/sec
# We're conservative and assume ~2 API calls per record (fetch + notes/tasks for deals)
# Burst 50% of capacity upfront, leave headroom for webhooks
BURST_RECORD_COUNT = 5000  # ~50 seconds of burst at 100/sec
BURST_BATCH_COUNT = BURST_RECORD_COUNT // BATCH_SIZE

# After burst, process at a conservative rate to leave headroom
RECORDS_PER_HOUR_AFTER_BURST = 10000  # ~2.8 records/sec, well under 100/sec limit

# Delay between rate-limited batches (after burst)
# For 100-record batches: 100 * 3600 / 10000 = 36 seconds between batches
BATCH_DELAY_SECONDS = BATCH_SIZE * 3600 // RECORDS_PER_HOUR_AFTER_BURST


class AttioBackfillRootExtractor(BaseExtractor[AttioBackfillRootConfig]):
    """Root extractor that collects all record IDs and splits into batch jobs.

    This extractor:
    1. Collects all record IDs for companies, people, and deals
    2. Splits them into batches of BATCH_SIZE records
    3. Sends child jobs with burst + rate-limited scheduling

    All child jobs share the same backfill_id for unified tracking and notification.
    """

    source_name = "attio_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: AttioBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or secrets.token_hex(8)
        tenant_id = config.tenant_id

        logger.info(
            "Starting Attio backfill root job",
            backfill_id=backfill_id,
            tenant_id=tenant_id,
        )

        try:
            attio_client = await get_attio_client_for_tenant(tenant_id, self.ssm_client)
        except Exception as e:
            logger.error(f"Failed to get Attio client: {e}")
            raise

        # Collect all record IDs for each object type
        company_ids = self._collect_record_ids(attio_client, AttioObjectType.COMPANIES)
        person_ids = self._collect_record_ids(attio_client, AttioObjectType.PEOPLE)
        deal_ids = self._collect_record_ids(attio_client, AttioObjectType.DEALS)

        logger.info(
            "Collected all Attio record IDs",
            backfill_id=backfill_id,
            companies=len(company_ids),
            people=len(person_ids),
            deals=len(deal_ids),
        )

        # Create batches for each object type
        company_batches = self._create_batches(company_ids)
        person_batches = self._create_batches(person_ids)
        deal_batches = self._create_batches(deal_ids)

        total_batches = len(company_batches) + len(person_batches) + len(deal_batches)

        if total_batches == 0:
            logger.warning("No Attio records found to backfill", tenant_id=tenant_id)
            # Still update last_synced_at to prevent repeated sync attempts every 4 hours
            sync_timestamp = datetime.now(UTC)
            for object_type in AttioObjectType:
                await attio_object_sync_service.set_object_last_synced_at(
                    object_type, sync_timestamp, db_pool
                )
            return

        logger.info(
            f"Splitting into {total_batches} batches",
            backfill_id=backfill_id,
            company_batches=len(company_batches),
            person_batches=len(person_batches),
            deal_batches=len(deal_batches),
        )

        # Track total number of child ingest jobs for this backfill
        await increment_backfill_total_ingest_jobs(backfill_id, tenant_id, total_batches)

        # Calculate burst and rate-limiting strategy
        burst_batch_count = min(total_batches, BURST_BATCH_COUNT)
        base_start_time = datetime.now(UTC)

        # Log the schedule
        rate_limited_batches = max(0, total_batches - burst_batch_count)
        if rate_limited_batches > 0:
            total_delay_minutes = rate_limited_batches * BATCH_DELAY_SECONDS / 60
            logger.info(
                f"Burst processing {burst_batch_count} batches, "
                f"then rate-limiting {rate_limited_batches} batches with {BATCH_DELAY_SECONDS}s delays "
                f"(rate-limited duration: {total_delay_minutes:.1f} minutes)",
                backfill_id=backfill_id,
            )
        else:
            logger.info(
                f"Burst processing all {burst_batch_count} batches",
                backfill_id=backfill_id,
            )

        # Send all batch jobs with interleaved scheduling
        # We interleave object types to spread load evenly
        batch_index = 0

        # Send company batches
        for batch in company_batches:
            await self._send_company_batch(
                tenant_id=tenant_id,
                record_ids=batch,
                batch_index=batch_index,
                base_start_time=base_start_time,
                burst_batch_count=burst_batch_count,
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )
            batch_index += 1

        # Send person batches
        for batch in person_batches:
            await self._send_person_batch(
                tenant_id=tenant_id,
                record_ids=batch,
                batch_index=batch_index,
                base_start_time=base_start_time,
                burst_batch_count=burst_batch_count,
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )
            batch_index += 1

        # Send deal batches
        for batch in deal_batches:
            await self._send_deal_batch(
                tenant_id=tenant_id,
                record_ids=batch,
                batch_index=batch_index,
                base_start_time=base_start_time,
                burst_batch_count=burst_batch_count,
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )
            batch_index += 1

        # Update last_synced_at for ALL object types unconditionally
        # This marks the sync as complete for the cron job's 4-week check
        # We update all types even if some have no records, to prevent repeated
        # backfills every 4 hours for empty object types
        sync_timestamp = datetime.now(UTC)
        for object_type in AttioObjectType:
            await attio_object_sync_service.set_object_last_synced_at(
                object_type, sync_timestamp, db_pool
            )

        logger.info(
            "Attio backfill root job completed - all child jobs sent",
            backfill_id=backfill_id,
            total_batches=total_batches,
            sync_timestamp=sync_timestamp.isoformat(),
        )

    def _collect_record_ids(
        self, attio_client: AttioClient, object_type: AttioObjectType
    ) -> list[str]:
        """Collect all record IDs for an object type.

        Re-raises all errors except for "standard_object_disabled" which indicates
        the object type is not enabled in this Attio workspace.
        """
        try:
            return attio_client.collect_all_record_ids(object_type.value)
        except requests.exceptions.HTTPError as e:
            # Check if this object type is disabled in this workspace
            if self._is_standard_object_disabled_error(e):
                logger.warning(
                    f"{object_type.value.capitalize()} object is not enabled "
                    "in this Attio workspace - skipping"
                )
                return []
            raise

    def _is_standard_object_disabled_error(self, error: requests.exceptions.HTTPError) -> bool:
        """Check if the HTTP error is due to a disabled standard object."""
        try:
            if error.response is not None and error.response.status_code == 400:
                response_json = error.response.json()
                return response_json.get("code") == "standard_object_disabled"
        except Exception:
            pass
        return False

    def _create_batches(self, record_ids: list[str]) -> list[list[str]]:
        """Split record IDs into batches of BATCH_SIZE."""
        return [record_ids[i : i + BATCH_SIZE] for i in range(0, len(record_ids), BATCH_SIZE)]

    def _calculate_start_timestamp(
        self,
        batch_index: int,
        base_start_time: datetime,
        burst_batch_count: int,
    ) -> datetime | None:
        """Calculate start timestamp for a batch based on burst/rate-limit strategy."""
        if batch_index < burst_batch_count:
            # Burst processing - no delay
            return None
        else:
            # Rate-limited processing - calculate delay
            rate_limited_index = batch_index - burst_batch_count
            delay_seconds = rate_limited_index * BATCH_DELAY_SECONDS
            return base_start_time + timedelta(seconds=delay_seconds)

    async def _send_company_batch(
        self,
        tenant_id: str,
        record_ids: list[str],
        batch_index: int,
        base_start_time: datetime,
        burst_batch_count: int,
        backfill_id: str,
        suppress_notification: bool,
    ) -> None:
        """Send a company batch job."""
        start_timestamp = self._calculate_start_timestamp(
            batch_index, base_start_time, burst_batch_count
        )

        config = AttioCompanyBackfillConfig(
            tenant_id=tenant_id,
            record_ids=record_ids,
            start_timestamp=start_timestamp,
            backfill_id=backfill_id,
            suppress_notification=suppress_notification,
        )

        await self.sqs_client.send_backfill_ingest_message(config)
        logger.debug(
            f"Sent company batch {batch_index}",
            records=len(record_ids),
            delayed=start_timestamp is not None,
        )

    async def _send_person_batch(
        self,
        tenant_id: str,
        record_ids: list[str],
        batch_index: int,
        base_start_time: datetime,
        burst_batch_count: int,
        backfill_id: str,
        suppress_notification: bool,
    ) -> None:
        """Send a person batch job."""
        start_timestamp = self._calculate_start_timestamp(
            batch_index, base_start_time, burst_batch_count
        )

        config = AttioPersonBackfillConfig(
            tenant_id=tenant_id,
            record_ids=record_ids,
            start_timestamp=start_timestamp,
            backfill_id=backfill_id,
            suppress_notification=suppress_notification,
        )

        await self.sqs_client.send_backfill_ingest_message(config)
        logger.debug(
            f"Sent person batch {batch_index}",
            records=len(record_ids),
            delayed=start_timestamp is not None,
        )

    async def _send_deal_batch(
        self,
        tenant_id: str,
        record_ids: list[str],
        batch_index: int,
        base_start_time: datetime,
        burst_batch_count: int,
        backfill_id: str,
        suppress_notification: bool,
    ) -> None:
        """Send a deal batch job."""
        start_timestamp = self._calculate_start_timestamp(
            batch_index, base_start_time, burst_batch_count
        )

        config = AttioDealBackfillConfig(
            tenant_id=tenant_id,
            record_ids=record_ids,
            start_timestamp=start_timestamp,
            backfill_id=backfill_id,
            suppress_notification=suppress_notification,
        )

        await self.sqs_client.send_backfill_ingest_message(config)
        logger.debug(
            f"Sent deal batch {batch_index}",
            records=len(record_ids),
            delayed=start_timestamp is not None,
        )
