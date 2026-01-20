"""HubSpot webhook extractor for processing webhook events."""

import logging
from typing import Any

import asyncpg
from pydantic import BaseModel

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
from connectors.hubspot.hubspot_ticket_backfill_extractor import (
    HubSpotTicketBackfillExtractor,
)

logger = logging.getLogger(__name__)


class HubSpotWebhookConfig(BaseModel):
    """Configuration for HubSpot webhook processing."""

    body: dict[str, Any]
    tenant_id: str


class HubSpotWebhookExtractor(HubSpotExtractor[HubSpotWebhookConfig]):
    """Extractor for processing HubSpot webhook events."""

    source_name = "hubspot_webhook"

    async def process_job(
        self,
        job_id: str,
        config: HubSpotWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # The webhook body now contains deduplicated objects: {"companies": [...], "deals": [...]}
        objects_to_process = config.body

        logger.info(
            f"Processing HubSpot webhook job {job_id} for tenant {config.tenant_id}: "
            f"{len(objects_to_process.get('companies', []))} companies, "
            f"{len(objects_to_process.get('deals', []))} deals, "
            f"{len(objects_to_process.get('tickets', []))} tickets, "
            f"{len(objects_to_process.get('contacts', []))} contacts"
        )

        # Process all unique companies
        companies_ids = objects_to_process.get("companies", [])
        if companies_ids:
            await self._handle_company_webhook(
                company_ids=companies_ids,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )

        # Process all unique deals
        deals_ids = objects_to_process.get("deals", [])
        if deals_ids:
            await self._handle_deal_webhook(
                deal_ids=deals_ids,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )

        tickets_ids = objects_to_process.get("tickets", [])
        if tickets_ids:
            await self._handle_ticket_webhook(
                ticket_ids=tickets_ids,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )

        contacts_ids = objects_to_process.get("contacts", [])
        if contacts_ids:
            await self._handle_contact_webhook(
                contact_ids=contacts_ids,
                job_id=job_id,
                config=config,
                db_pool=db_pool,
                trigger_indexing=trigger_indexing,
            )

        logger.info(f"Successfully processed HubSpot webhook job {job_id}")

    async def _handle_ticket_webhook(
        self,
        ticket_ids: list[str],
        job_id: str,
        config: HubSpotWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Handling ticket webhook for tickets {len(ticket_ids)}")

        hubspot_client = await self.get_hubspot_client(config.tenant_id, db_pool)

        ticket_backfill = HubSpotTicketBackfillExtractor(self.ssm_client)
        custom_properties = await self.get_object_custom_properties("ticket", db_pool)
        custom_properties_names = [property.name for property in custom_properties]

        pipelines = await hubspot_client.get_pipelines("tickets")
        pipelines = [pipeline.to_dict() for pipeline in pipelines]

        tickets_data = await hubspot_client.get_tickets(
            ticket_ids, list(HUBSPOT_TICKET_PROPERTIES.keys()) + custom_properties_names
        )

        if not tickets_data:
            return

        associations, companies = await ticket_backfill._fetch_associated_companies(
            hubspot_client, tickets_data, config.tenant_id
        )
        artifacts = ticket_backfill._tickets_to_artifacts(
            tickets_data, associations, companies, {}, pipelines, job_id
        )

        await self.process_and_store_artifacts(
            artifacts, DocumentSource.HUBSPOT_TICKET, config.tenant_id, db_pool, trigger_indexing
        )
        logger.info(f"Processed ticket webhook for tickets {len(ticket_ids)}")

    async def _handle_contact_webhook(
        self,
        contact_ids: list[str],
        job_id: str,
        config: HubSpotWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Handling contact webhook for contacts {len(contact_ids)}")

        hubspot_client = await self.get_hubspot_client(config.tenant_id, db_pool)

        custom_properties = await self.get_object_custom_properties("contact", db_pool)
        custom_properties_names = [property.name for property in custom_properties]

        contacts = await hubspot_client.get_contacts(
            contact_ids, list(HUBSPOT_CONTACT_PROPERTIES.keys()) + custom_properties_names
        )

        if not contacts:
            return

        associations, companies = await fetch_associated_companies_for_contacts(
            hubspot_client, contacts
        )
        artifacts = contacts_to_artifacts(contacts, associations, companies, job_id)

        await self.process_and_store_artifacts(
            artifacts, DocumentSource.HUBSPOT_CONTACT, config.tenant_id, db_pool, trigger_indexing
        )
        logger.info(f"Processed contact webhook for contacts {len(contact_ids)}")

    async def _handle_company_webhook(
        self,
        company_ids: list[str],
        job_id: str,
        config: HubSpotWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Handling company webhook for companies {len(company_ids)}")

        # Get HubSpot client
        hubspot_client = await self.get_hubspot_client(config.tenant_id, db_pool)

        custom_properties = await self.get_object_custom_properties("company", db_pool)
        custom_properties_names = [property.name for property in custom_properties]

        # Fetch current company data from API
        company_data = await hubspot_client.get_companies(
            company_ids, HUBSPOT_COMPANY_PROPERTIES + custom_properties_names
        )

        if not company_data:
            return

        artifacts = companies_to_artifacts(company_data, job_id)

        await self.process_and_store_artifacts(
            artifacts, DocumentSource.HUBSPOT_COMPANY, config.tenant_id, db_pool, trigger_indexing
        )
        logger.info(f"Processed company webhook for companies {len(company_ids)}")

    async def _handle_deal_webhook(
        self,
        deal_ids: list[str],
        job_id: str,
        config: HubSpotWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Handling deal webhook for deals {len(deal_ids)}")

        hubspot_client = await self.get_hubspot_client(config.tenant_id, db_pool)

        custom_properties = await self.get_object_custom_properties("deal", db_pool)
        custom_properties_names = [property.name for property in custom_properties]

        deals_data = await hubspot_client.get_deals(
            deal_ids, HUBSPOT_DEAL_PROPERTIES + custom_properties_names
        )

        if not deals_data:
            return

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
        logger.info(f"Processed deal webhook for deals {len(deal_ids)}")
