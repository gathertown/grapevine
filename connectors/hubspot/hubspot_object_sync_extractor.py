"""
HubSpot object sync extractor.

Fetches objects for a specific date range that have been updated and processes them with associated company data.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.hubspot.hubspot_artifacts import (
    HUBSPOT_COMPANY_PROPERTIES,
    HUBSPOT_CONTACT_PROPERTIES,
    HUBSPOT_DEAL_PROPERTIES,
    HUBSPOT_TICKET_PROPERTIES,
)
from connectors.hubspot.hubspot_base import HubSpotExtractor
from connectors.hubspot.hubspot_company_backfill_extractor import (
    companies_to_artifacts,
)
from connectors.hubspot.hubspot_contact_backfill_extractor import (
    contacts_to_artifacts,
    fetch_associated_companies_for_contacts,
)
from connectors.hubspot.hubspot_deal_backfill_extractor import HubSpotDealBackfillExtractor
from connectors.hubspot.hubspot_models import HubSpotObjectSyncConfig
from connectors.hubspot.hubspot_ticket_backfill_extractor import (
    HubSpotTicketBackfillExtractor,
)
from src.clients.hubspot.hubspot_client import HubSpotClient
from src.clients.hubspot.hubspot_models import HubSpotSearchDateFilter, HubSpotSearchOptions
from src.ingest.services.hubspot import hubspot_object_sync_service
from src.ingest.services.hubspot_custom_properties import hubspot_custom_properties

logger = logging.getLogger(__name__)


class HubSpotObjectSyncExtractor(HubSpotExtractor[HubSpotObjectSyncConfig]):
    source_name = "hubspot_object_sync"

    async def process_job(
        self,
        job_id: str,
        config: HubSpotObjectSyncConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(
            f"[tenant={config.tenant_id}] Processing HubSpot object sync "
            f"for object type {config.object_type} "
        )

        last_synced_at = await hubspot_object_sync_service.get_object_last_synced_at(
            config.object_type, db_pool
        )
        if last_synced_at:
            logger.info(f"[tenant={config.tenant_id}] Last synced at: {last_synced_at.isoformat()}")
        else:
            # if no last synced at, set to 5 minutes ago
            last_synced_at = datetime.now(UTC) - timedelta(minutes=5)

        hubspot_client = await self.get_hubspot_client(config.tenant_id, db_pool)

        await self._load_custom_properties(hubspot_client, db_pool)

        synced_till = None

        if config.object_type == "company":
            synced_till = await self._process_company_sync(
                hubspot_client, config, last_synced_at, job_id, db_pool, trigger_indexing
            )
        elif config.object_type == "deal":
            synced_till = await self._process_deal_sync(
                hubspot_client, config, last_synced_at, job_id, db_pool, trigger_indexing
            )
        elif config.object_type == "contact":
            synced_till = await self._process_contact_sync(
                hubspot_client, config, last_synced_at, job_id, db_pool, trigger_indexing
            )
        elif config.object_type == "ticket":
            synced_till = await self._process_ticket_sync(
                hubspot_client, config, last_synced_at, job_id, db_pool, trigger_indexing
            )
        else:
            raise ValueError(f"Invalid object type: {config.object_type}")

        if synced_till:
            await hubspot_object_sync_service.set_object_last_synced_at(
                config.object_type, synced_till, db_pool
            )
        else:
            logger.warning(
                f"[tenant={config.tenant_id}] No synced till time found for object type {config.object_type}"
            )

        logger.info(
            f"Successfully processed HubSpot object sync for object type {config.object_type}"
        )

    async def _load_custom_properties(
        self, hubspot_client: HubSpotClient, db_pool: asyncpg.Pool
    ) -> None:
        async with db_pool.acquire() as conn:
            await hubspot_custom_properties.load_all(hubspot_client, conn)

    async def _process_company_sync(
        self,
        hubspot_client: HubSpotClient,
        config: HubSpotObjectSyncConfig,
        last_synced_at: datetime,
        job_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> datetime | None:
        logger.info(
            f"Processing HubSpot company sync for object type {config.object_type} since {last_synced_at.isoformat()}"
        )

        synced_till = datetime.now(UTC)

        custom_properties = await self.get_object_custom_properties("company", db_pool)
        custom_properties_names = [property.name for property in custom_properties]
        search_options = HubSpotSearchOptions(
            properties=HUBSPOT_COMPANY_PROPERTIES + custom_properties_names,
            date_filter=HubSpotSearchDateFilter(start=last_synced_at, end=synced_till),
            search_by="hs_lastmodifieddate",
        )

        companies_data: list[Any] = []
        async for res in hubspot_client.search_companies(search_options):
            companies_data.extend(res.results)

        if not companies_data:
            return synced_till

        logger.info(f"Found {len(companies_data)} companies to process")

        artifacts = companies_to_artifacts(companies_data, job_id)

        await self.process_and_store_artifacts(
            artifacts, DocumentSource.HUBSPOT_COMPANY, config.tenant_id, db_pool, trigger_indexing
        )
        logger.info(f"Processed company sync for companies {len(companies_data)}")
        return synced_till

    async def _process_deal_sync(
        self,
        hubspot_client: HubSpotClient,
        config: HubSpotObjectSyncConfig,
        last_synced_at: datetime,
        job_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> datetime | None:
        logger.info(
            f"Processing HubSpot deal sync for object type {config.object_type} since {last_synced_at.isoformat()}"
        )

        synced_till = datetime.now(UTC)

        custom_properties = await self.get_object_custom_properties("deal", db_pool)
        custom_properties_names = [property.name for property in custom_properties]
        search_options = HubSpotSearchOptions(
            properties=HUBSPOT_DEAL_PROPERTIES + custom_properties_names,
            date_filter=HubSpotSearchDateFilter(start=last_synced_at, end=synced_till),
            search_by="hs_lastmodifieddate",
        )
        deals_data: list[Any] = []
        async for page in hubspot_client.search_deals(search_options):
            deals_data.extend(page.results)

        logger.info(f"Found {len(deals_data)} deals to process")

        if not deals_data:
            return synced_till

        deal_backfill = HubSpotDealBackfillExtractor(self.ssm_client)
        pipelines = await hubspot_client.get_pipelines("deals")
        pipelines = [pipeline.to_dict() for pipeline in pipelines]

        associations, companies = await deal_backfill._fetch_associated_companies(
            hubspot_client, deals_data, config.tenant_id
        )
        deal_activities = await deal_backfill._fetch_deal_activities(
            hubspot_client, deals_data, config.tenant_id
        )

        artifacts = []
        for deal_data in deals_data:
            artifact = deal_backfill._deal_to_artifact(
                deal_data, associations, companies, deal_activities, pipelines, job_id
            )
            artifacts.append(artifact)

        await self.process_and_store_artifacts(
            artifacts, DocumentSource.HUBSPOT_DEAL, config.tenant_id, db_pool, trigger_indexing
        )
        logger.info(f"Processed deal sync for deals {len(deals_data)}")
        return synced_till

    async def _process_contact_sync(
        self,
        hubspot_client: HubSpotClient,
        config: HubSpotObjectSyncConfig,
        last_synced_at: datetime,
        job_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> datetime | None:
        logger.info(
            f"Processing HubSpot contact sync for object type {config.object_type} since {last_synced_at.isoformat()}"
        )

        synced_till = datetime.now(UTC)

        custom_properties = await self.get_object_custom_properties("contact", db_pool)
        custom_properties_names = [property.name for property in custom_properties]
        search_options = HubSpotSearchOptions(
            properties=list(HUBSPOT_CONTACT_PROPERTIES.keys()) + custom_properties_names,
            date_filter=HubSpotSearchDateFilter(start=last_synced_at, end=synced_till),
            search_by="hs_lastmodifieddate",
        )
        contacts_data: list[Any] = []
        async for page in hubspot_client.search_contacts(search_options):
            contacts_data.extend(page.results)

        if not contacts_data:
            return synced_till

        logger.info(f"Found {len(contacts_data)} contacts to process")

        associations, companies = await fetch_associated_companies_for_contacts(
            hubspot_client, contacts_data
        )
        artifacts = contacts_to_artifacts(contacts_data, associations, companies, job_id)

        await self.process_and_store_artifacts(
            artifacts, DocumentSource.HUBSPOT_CONTACT, config.tenant_id, db_pool, trigger_indexing
        )
        logger.info(f"Processed contact sync for contacts {len(contacts_data)}")
        return synced_till

    async def _process_ticket_sync(
        self,
        hubspot_client: HubSpotClient,
        config: HubSpotObjectSyncConfig,
        last_synced_at: datetime,
        job_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> datetime | None:
        logger.info(
            f"Processing HubSpot ticket sync for object type {config.object_type} since {last_synced_at.isoformat()}"
        )

        synced_till = datetime.now(UTC)

        custom_properties = await self.get_object_custom_properties("ticket", db_pool)
        custom_properties_names = [property.name for property in custom_properties]
        search_options = HubSpotSearchOptions(
            properties=list(HUBSPOT_TICKET_PROPERTIES.keys()) + custom_properties_names,
            date_filter=HubSpotSearchDateFilter(start=last_synced_at, end=synced_till),
            search_by="hs_lastmodifieddate",
        )

        tickets_data: list[Any] = []
        async for page in hubspot_client.search_tickets(search_options):
            tickets_data.extend(page.results)

        if not tickets_data:
            return synced_till

        logger.info(f"Found {len(tickets_data)} tickets to process")

        ticket_backfill = HubSpotTicketBackfillExtractor(self.ssm_client)
        pipelines = await hubspot_client.get_pipelines("tickets")
        pipelines = [pipeline.to_dict() for pipeline in pipelines]

        associations, companies = await ticket_backfill._fetch_associated_companies(
            hubspot_client, tickets_data, config.tenant_id
        )
        artifacts = ticket_backfill._tickets_to_artifacts(
            tickets_data, associations, companies, {}, pipelines, job_id
        )

        await self.process_and_store_artifacts(
            artifacts, DocumentSource.HUBSPOT_TICKET, config.tenant_id, db_pool, trigger_indexing
        )
        logger.info(f"Processed ticket sync for tickets {len(tickets_data)}")
        return synced_till
