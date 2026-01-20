from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, get_hubspot_company_entity_id
from connectors.base.base_extractor import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.hubspot.hubspot_artifacts import HUBSPOT_COMPANY_PROPERTIES, HubspotCompanyArtifact
from connectors.hubspot.hubspot_models import HubSpotCompanyBackfillConfig
from src.clients.hubspot.hubspot_factory import get_hubspot_client_for_tenant
from src.clients.hubspot.hubspot_models import HubSpotSearchDateFilter, HubSpotSearchOptions
from src.clients.ssm import SSMClient
from src.ingest.services.hubspot_custom_properties import hubspot_custom_properties
from src.utils.logging import get_logger
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = get_logger(__name__)


class HubSpotCompanyBackfillExtractor(BaseExtractor[HubSpotCompanyBackfillConfig]):
    """
    Extracts HubSpot companies created within a specific date range.

    Fetches all companies whose 'createdate' falls between the configured
    start_date and end_date. This is a child job of HubSpotBackfillRootExtractor,
    which assigns each child a single month to process.
    """

    source_name = "hubspot_company_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def _get_custom_properties(self, db_pool: asyncpg.Pool) -> list[str]:
        async with db_pool.acquire() as conn:
            custom_properties = await hubspot_custom_properties.get_by_object_type(
                object_type="company", conn=conn
            )
            return [property.name for property in custom_properties]

    async def process_job(
        self,
        job_id: str,
        config: HubSpotCompanyBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(
            "Processing HubSpot company backfill",
            start_date=config.start_date,
            end_date=config.end_date,
        )

        # Get HubSpot client from factory
        hubspot_client = await get_hubspot_client_for_tenant(
            config.tenant_id, self.ssm_client, db_pool
        )

        # Load custom properties
        custom_properties_names = await self._get_custom_properties(db_pool)
        if custom_properties_names:
            logger.info(f"Found {len(custom_properties_names)} custom properties for companies")

        # Pagination loop for this month's companies
        total_companies_processed = 0
        page_num = 0

        # Build search options with explicit archived filter
        # Search endpoints do not return archived CRM Objects, so we don't need
        # to explicitly filter out archived companies
        search_options = HubSpotSearchOptions(
            properties=HUBSPOT_COMPANY_PROPERTIES + custom_properties_names,
            date_filter=HubSpotSearchDateFilter(start=config.start_date, end=config.end_date),
            search_by="createdate",
        )

        async for res in hubspot_client.search_companies(search_options):
            # Fetch one page of companies
            page_num += 1

            # Convert companies to artifacts
            artifacts = companies_to_artifacts(res.results, job_id)

            # Store this page of artifacts
            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)
                total_companies_processed += len(artifacts)

                # Trigger indexing for this page's companies immediately
                entity_ids = [artifact.entity_id for artifact in artifacts]

                await trigger_indexing(
                    entity_ids,
                    DocumentSource.HUBSPOT_COMPANY,
                    config.tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

                # Track index job for backfill progress (one job per page)
                if config.backfill_id:
                    await increment_backfill_total_index_jobs(
                        config.backfill_id, config.tenant_id, 1
                    )

        logger.info(
            "Completed HubSpot company backfill",
            start_date=config.start_date,
            end_date=config.end_date,
            total_companies_processed=total_companies_processed,
            total_pages=page_num,
        )

        if config.backfill_id:
            await increment_backfill_attempted_ingest_jobs(config.backfill_id, config.tenant_id, 1)
            await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)


def companies_to_artifacts(companies: Sequence[Any], job_id: str) -> list[HubspotCompanyArtifact]:
    return [company_to_artifact(company, job_id) for company in companies]


def company_to_artifact(company: Any, job_id: str) -> HubspotCompanyArtifact:
    # Convert HubSpot object to dict
    company_data = company.to_dict()
    company_id = str(company.id)

    # Convert datetime objects to ISO format strings for JSON serialization
    for key, value in company_data.items():
        if isinstance(value, datetime):
            company_data[key] = value.isoformat()

    # Also convert properties dict values if they contain datetime objects
    if "properties" in company_data:
        for key, value in company_data["properties"].items():
            if isinstance(value, datetime):
                company_data["properties"][key] = value.isoformat()

    source_updated_at = company_data.get("updated_at")

    artifact = HubspotCompanyArtifact(
        entity_id=get_hubspot_company_entity_id(company_id=company_id),
        ingest_job_id=UUID(job_id),
        content=company_data.get("properties", {}),
        metadata={
            "company_id": company_id,
            "source_created_at": company_data.get("created_at"),
            "source_updated_at": source_updated_at,
        },
        source_updated_at=source_updated_at,
    )

    return artifact
