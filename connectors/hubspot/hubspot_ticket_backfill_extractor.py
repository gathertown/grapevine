"""
HubSpot ticket backfill extractor.

Fetches tickets for a specific date range and processes them with associated company data.
"""

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, get_hubspot_ticket_entity_id
from connectors.base.document_source import DocumentSource
from connectors.hubspot.hubspot_artifacts import (
    HUBSPOT_TICKET_PROPERTIES,
    HubspotTicketArtifact,
)
from connectors.hubspot.hubspot_models import HubSpotTicketBackfillConfig
from src.clients.hubspot.hubspot_client import HubSpotClient, HubSpotProperty
from src.clients.hubspot.hubspot_factory import get_hubspot_client_for_tenant
from src.clients.hubspot.hubspot_models import HubSpotSearchDateFilter, HubSpotSearchOptions
from src.clients.ssm import SSMClient
from src.ingest.services.hubspot_custom_properties import hubspot_custom_properties
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = logging.getLogger(__name__)

# Batch size for indexing
INDEX_BATCH_SIZE = 200


class HubSpotTicketBackfillExtractor(BaseExtractor[HubSpotTicketBackfillConfig]):
    source_name = "hubspot_ticket_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: HubSpotTicketBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: Callable[
            [list[str], DocumentSource, str, str | None, bool], Awaitable[None]
        ],
    ) -> None:
        logger.info(
            f"[tenant={config.tenant_id}] Processing HubSpot ticket backfill "
            f"from {config.start_date.isoformat()} to {config.end_date.isoformat()} "
        )

        # Get HubSpot client from factory
        hubspot_client = await get_hubspot_client_for_tenant(
            config.tenant_id, self.ssm_client, db_pool
        )

        # Fetch pipelines from API for resolving names
        pipelines = await hubspot_client.get_pipelines("tickets")
        # Convert Pipeline objects to dicts for compatibility with _resolve_pipeline_and_stage_names
        pipelines = [pipeline.to_dict() for pipeline in pipelines]

        custom_properties = await self._get_ticket_custom_properties(db_pool)
        custom_properties_names = [property.name for property in custom_properties]
        logger.info(
            f"[tenant={config.tenant_id}] Found {len(custom_properties_names)} custom properties for tickets"
        )

        # Pagination loop for this month's tickets
        total_tickets_processed = 0
        page_num = 0

        search_options = HubSpotSearchOptions(
            properties=list(HUBSPOT_TICKET_PROPERTIES.keys()) + custom_properties_names,
            date_filter=HubSpotSearchDateFilter(start=config.start_date, end=config.end_date),
            search_by="createdate",
        )

        async for page in hubspot_client.search_tickets(search_options):
            page_num += 1

            total_tickets_processed += await self._process_tickets_page(
                hubspot_client=hubspot_client,
                config=config,
                job_id=job_id,
                db_pool=db_pool,
                pipelines=pipelines,
                tickets=page.results,
                page_num=page_num,
                total_tickets_processed=total_tickets_processed,
                trigger_indexing=trigger_indexing,
            )

        logger.info(
            f"[tenant={config.tenant_id}] Completed HubSpot ticket backfill: "
            f"processed {total_tickets_processed} tickets for {config.start_date.isoformat()} to {config.end_date.isoformat()}"
        )

        if config.backfill_id:
            await increment_backfill_attempted_ingest_jobs(config.backfill_id, config.tenant_id, 1)
            await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

    async def _get_ticket_custom_properties(self, db_pool: asyncpg.Pool) -> list[HubSpotProperty]:
        async with db_pool.acquire() as conn:
            return await hubspot_custom_properties.get_by_object_type(
                object_type="ticket", conn=conn
            )

    async def _process_tickets_page(
        self,
        hubspot_client: HubSpotClient,
        config: HubSpotTicketBackfillConfig,
        job_id: str,
        db_pool: asyncpg.Pool,
        pipelines: list[dict[str, Any]],
        tickets: list[Any],
        page_num: int,
        total_tickets_processed: int,
        trigger_indexing: Callable[
            [list[str], DocumentSource, str, str | None, bool], Awaitable[None]
        ],
    ) -> int:
        logger.info(f"[tenant={config.tenant_id}] Page {page_num}: fetched {len(tickets)} tickets")

        if not tickets:
            return 0

        # Fetch associated companies
        associations, companies = await self._fetch_associated_companies(
            hubspot_client, tickets, config.tenant_id
        )

        # Convert tickets to artifacts with embedded data
        artifacts = self._tickets_to_artifacts(
            tickets, associations, companies, {}, pipelines, job_id
        )

        # Store this page of artifacts
        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

            logger.info(
                f"[tenant={config.tenant_id}] Processed page {page_num}: {len(artifacts)} tickets "
                f"(total: {total_tickets_processed + len(artifacts)})"
            )

            # Trigger indexing for this page's tickets immediately
            entity_ids = [artifact.entity_id for artifact in artifacts]

            logger.info(
                f"[tenant={config.tenant_id}] Triggering indexing for {len(entity_ids)} "
                f"entities from page {page_num}"
            )

            await trigger_indexing(
                entity_ids,
                DocumentSource.HUBSPOT_TICKET,
                config.tenant_id,
                config.backfill_id,
                config.suppress_notification,
            )

            # Track index job for backfill progress (one job per page)
            if config.backfill_id:
                await increment_backfill_total_index_jobs(config.backfill_id, config.tenant_id, 1)

        return len(artifacts)

    async def _fetch_associated_companies(
        self, hubspot_client: HubSpotClient, tickets: Sequence[Any], tenant_id: str
    ) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
        """Fetch company associations and data for tickets.

        Args:
            hubspot_client: HubSpot API client
            tickets: List of ticket objects
            tenant_id: Tenant identifier

        Returns:
            Tuple of (associations dict, companies dict)
        """
        # Extract ticket IDs
        ticket_ids = [str(ticket.id) for ticket in tickets]

        # Get company associations for these tickets
        associations = await hubspot_client.get_company_associations("tickets", ticket_ids)
        logger.info(f"[tenant={tenant_id}] Fetched associations for {len(associations)} tickets")

        # Extract unique company IDs from associations
        all_company_ids = set()
        for company_ids in associations.values():
            all_company_ids.update(company_ids)

        # Batch fetch company data
        companies = {}
        if all_company_ids:
            # Explicit business logic: exclude archived companies
            companies = await hubspot_client.batch_read_companies(
                list(all_company_ids), filters={"archived": False}
            )
            logger.info(f"[tenant={tenant_id}] Fetched {len(companies)} companies")

        return associations, companies

    def _tickets_to_artifacts(
        self,
        tickets: Sequence[Any],
        associations: dict[str, list[str]],
        companies: dict[str, dict[str, Any]],
        ticket_activities: dict[str, dict[str, list[Any]]],
        pipelines: list[dict[str, Any]],
        job_id: str,
    ) -> list[HubspotTicketArtifact]:
        """Convert tickets to artifacts with embedded company and pipeline info.

        Args:
            tickets: List of ticket objects from API
            associations: Ticket ID -> list of company IDs mapping
            companies: Company ID -> company data mapping
            pipelines: Pipeline ID -> pipeline data mapping
            job_id: Job ID for tracking

        Returns:
            List of ticket artifacts
        """
        artifacts = []
        for ticket in tickets:
            artifact = self._ticket_to_artifact(
                ticket, associations, companies, {}, pipelines, job_id
            )
            artifacts.append(artifact)

        return artifacts

    def _ticket_to_artifact(
        self,
        ticket: Any,
        associations: dict[str, list[str]],
        companies: dict[str, dict[str, Any]],
        ticket_activities: dict[str, dict[str, list[Any]]],
        pipelines: list[dict[str, Any]],
        job_id: str,
    ) -> HubspotTicketArtifact:
        """Convert a single ticket to an artifact.

        Args:
            ticket: Ticket object from API
            associations: Ticket ID -> list of company IDs mapping
            companies: Company ID -> company data mapping
            pipelines: Pipeline ID -> pipeline data mapping
            job_id: Job ID for tracking

        Returns:
            Ticket artifact
        """
        # Convert ticket to dict and handle datetimes
        ticket_data = ticket.to_dict()
        ticket_data = self._convert_datetimes_to_iso(ticket_data)

        ticket_id = str(ticket.id)
        ticket_properties = ticket_data.get("properties", {})

        # Get associated company IDs
        company_ids = associations.get(ticket_id, [])

        # Get ticket activities
        # activities = ticket_activities.get(ticket_id, {})

        # Get company names
        company_names = self._extract_company_names(company_ids, companies)

        # Resolve pipeline and stage names
        pipeline_name, stage_name = self._resolve_pipeline_and_stage_names(
            ticket_properties, pipelines
        )

        # Build content with complete ticket data structure matching API response
        content = {
            "id": ticket_id,
            "properties": ticket_properties,
            "createdAt": ticket_data.get("created_at"),
            "updatedAt": ticket_data.get("updated_at"),
            "archived": ticket_data.get("archived", False),
            # Our additions for convenience:
            "pipeline_name": pipeline_name,
            "stage_name": stage_name,
            "company_names": company_names,
        }

        # Create artifact
        return self._create_ticket_artifact(
            ticket_id, ticket_properties, content, company_ids, job_id, ticket_data
        )

    def _extract_company_names(
        self, company_ids: list[str], companies: dict[str, dict[str, Any]]
    ) -> list[str]:
        """Extract company names from company data.

        Args:
            company_ids: List of company IDs
            companies: Company ID -> company data mapping

        Returns:
            List of company names
        """
        company_names = []
        for company_id in company_ids:
            if company_id in companies:
                company_data = companies[company_id]
                company_name = company_data.get("properties", {}).get("name")
                if company_name:
                    company_names.append(company_name)
        return company_names

    def _create_ticket_artifact(
        self,
        ticket_id: str,
        ticket_properties: dict[str, Any],
        content: dict[str, Any],
        company_ids: list[str],
        job_id: str,
        ticket_data: dict[str, Any],
    ) -> HubspotTicketArtifact:
        """Create a HubSpot ticket artifact.

        Args:
            ticket_id: Ticket ID
            ticket_properties: Ticket properties
            content: Content for the artifact
            company_ids: Associated company IDs
            job_id: Job ID for tracking

        Returns:
            Ticket artifact
        """
        metadata = {
            "ticket_id": ticket_id,
            "pipeline_id": ticket_properties.get("hs_pipeline"),
            "stage_id": ticket_properties.get("hs_pipeline_stage"),
            "company_ids": company_ids,
            "source_created_at": ticket_data.get("created_at"),
            "source_updated_at": ticket_data.get("updated_at"),
        }

        # Use actual updated_at from HubSpot, fallback to now if missing
        source_updated_at = ticket_data.get("updated_at")

        if isinstance(source_updated_at, str):
            source_updated_at = datetime.fromisoformat(source_updated_at.replace("Z", "+00:00"))
        elif not source_updated_at:
            source_updated_at = datetime.now(tz=UTC)

        return HubspotTicketArtifact(
            entity_id=get_hubspot_ticket_entity_id(ticket_id=ticket_id),
            ingest_job_id=UUID(job_id),
            content=content,
            metadata=metadata,
            source_updated_at=source_updated_at,
        )

    def _convert_datetimes_to_iso(self, data: Any) -> Any:
        """Recursively convert datetime objects to ISO format strings for JSON serialization."""
        if isinstance(data, datetime):
            return data.isoformat()
        elif isinstance(data, dict):
            return {key: self._convert_datetimes_to_iso(value) for key, value in data.items()}
        elif isinstance(data, list):
            return [self._convert_datetimes_to_iso(item) for item in data]
        return data

    def _resolve_pipeline_and_stage_names(
        self, ticket: dict[str, Any], pipelines: list[dict[str, Any]]
    ) -> tuple[str | None, str | None]:
        """Resolve pipeline and stage names from IDs.

        Args:
            ticket: Ticket data with pipeline and pipeline_stage fields
            pipelines: Pipeline data from API

        Returns:
            Tuple of (pipeline_name, stage_name)
        """
        pipeline_id = ticket.get("hs_pipeline")
        stage_id = ticket.get("hs_pipeline_stage")

        pipeline_name = None
        stage_name = None

        if not pipeline_id:
            return pipeline_name, stage_name

        # Find the matching pipeline
        for pipeline in pipelines:
            if pipeline.get("id") == pipeline_id:
                pipeline_name = pipeline.get("label")

                # Find stage name
                if stage_id and "stages" in pipeline:
                    for stage in pipeline["stages"]:
                        if str(stage.get("id")) == str(stage_id):
                            stage_name = stage.get("label")
                            break

                return pipeline_name, stage_name

        return pipeline_name, stage_name
