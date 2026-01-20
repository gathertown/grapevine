import secrets
from datetime import UTC, datetime, timedelta

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.hubspot.hubspot_models import (
    HubSpotBackfillRootConfig,
    HubSpotCompanyBackfillConfig,
    HubSpotContactBackfillConfig,
    HubSpotDealBackfillConfig,
    HubSpotTicketBackfillConfig,
)
from src.clients.hubspot.hubspot_factory import get_hubspot_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.services.hubspot_custom_properties import hubspot_custom_properties
from src.utils.logging import get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)

# Number of HubSpot object types to backfill (company, deal, ticket, contact)
HUBSPOT_OBJECT_TYPE_COUNT = 4

# Default lookback period for backfill
DEFAULT_BACKFILL_YEARS = 3


class HubSpotBackfillRootExtractor(BaseExtractor[HubSpotBackfillRootConfig]):
    source_name = "hubspot_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: HubSpotBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        backfill_id = config.backfill_id or secrets.token_hex(8)
        logger.info("Starting HubSpot backfill root job", backfill_id=backfill_id)

        await self._load_custom_properties(config.tenant_id, db_pool)

        # Generate monthly ranges and calculate total child jobs
        monthly_ranges = _generate_monthly_ranges(datetime.now(tz=UTC))
        total_child_jobs = len(monthly_ranges) * HUBSPOT_OBJECT_TYPE_COUNT

        # Track total ingest jobs for backfill completion notification
        await increment_backfill_total_ingest_jobs(backfill_id, config.tenant_id, total_child_jobs)

        logger.info(
            "HubSpot backfill root job dispatching child jobs",
            backfill_id=backfill_id,
            total_child_jobs=total_child_jobs,
            monthly_ranges_count=len(monthly_ranges),
        )

        # Create and send child jobs for each period (company, deal, ticket, contact jobs)
        for period_start, period_end in monthly_ranges:
            company_config = HubSpotCompanyBackfillConfig(
                tenant_id=config.tenant_id,
                start_date=period_start,
                end_date=period_end,
                backfill_id=backfill_id,  # Pass backfill_id to child jobs
                suppress_notification=config.suppress_notification,
            )

            await self.sqs_client.send_backfill_ingest_message(company_config)

            deal_config = HubSpotDealBackfillConfig(
                tenant_id=config.tenant_id,
                start_date=period_start,
                end_date=period_end,
                backfill_id=backfill_id,  # Pass backfill_id to child jobs
                suppress_notification=config.suppress_notification,
            )
            await self.sqs_client.send_backfill_ingest_message(deal_config)

            ticket_config = HubSpotTicketBackfillConfig(
                tenant_id=config.tenant_id,
                start_date=period_start,
                end_date=period_end,
                backfill_id=backfill_id,  # Pass backfill_id to child jobs
                suppress_notification=config.suppress_notification,
            )
            await self.sqs_client.send_backfill_ingest_message(ticket_config)

            contact_config = HubSpotContactBackfillConfig(
                tenant_id=config.tenant_id,
                start_date=period_start,
                end_date=period_end,
                backfill_id=backfill_id,  # Pass backfill_id to child jobs
                suppress_notification=config.suppress_notification,
            )
            await self.sqs_client.send_backfill_ingest_message(contact_config)

    async def _load_custom_properties(self, tenant_id: str, db_pool: asyncpg.Pool) -> None:
        hubspot_client = await get_hubspot_client_for_tenant(tenant_id, self.ssm_client, db_pool)
        async with db_pool.acquire() as conn:
            await hubspot_custom_properties.load_all(hubspot_client, conn)


def _generate_monthly_ranges(
    end_date: datetime, years_back: float = DEFAULT_BACKFILL_YEARS
) -> list[tuple[datetime, datetime]]:
    ranges: list[tuple[datetime, datetime]] = []

    current = (end_date - timedelta(days=years_back * 365)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )

    while current < end_date:
        next_month_start = (current + timedelta(days=32)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        month_end = min(next_month_start - timedelta(microseconds=1), end_date)

        ranges.append((current, month_end))
        current = next_month_start

    return ranges
