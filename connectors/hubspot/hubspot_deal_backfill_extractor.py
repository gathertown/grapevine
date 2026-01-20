from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, get_hubspot_deal_entity_id
from connectors.base.base_extractor import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.hubspot.hubspot_artifacts import (
    HUBSPOT_ACTIVITY_ALL_PROPERTIES,
    HUBSPOT_DEAL_PROPERTIES,
    HubspotDealArtifact,
)
from connectors.hubspot.hubspot_models import HubSpotDealBackfillConfig
from src.clients.hubspot.hubspot_client import HubSpotClient, HubSpotProperty
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

# Batch size for indexing
INDEX_BATCH_SIZE = 200


class HubSpotDealBackfillExtractor(BaseExtractor[HubSpotDealBackfillConfig]):
    source_name = "hubspot_deal_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: HubSpotDealBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(
            "Processing HubSpot deal backfill",
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
        )

        # Get HubSpot client from factory
        hubspot_client = await get_hubspot_client_for_tenant(
            config.tenant_id, self.ssm_client, db_pool
        )

        # Fetch pipelines from API for resolving names
        pipelines = await hubspot_client.get_pipelines("deals")
        # Convert Pipeline objects to dicts for compatibility with _resolve_pipeline_and_stage_names
        pipelines = [pipeline.to_dict() for pipeline in pipelines]

        custom_properties = await self._get_deal_custom_properties(db_pool)
        custom_properties_names = [property.name for property in custom_properties]
        logger.info(f"Found {len(custom_properties_names)} custom properties for deals")

        # Pagination loop for this month's deals
        total_deals_processed = 0
        after_cursor: int | None = None
        page_num = 0

        search_options = HubSpotSearchOptions(
            properties=HUBSPOT_DEAL_PROPERTIES + custom_properties_names,
            date_filter=HubSpotSearchDateFilter(start=config.start_date, end=config.end_date),
            search_by="createdate",
        )

        async for page in hubspot_client.search_deals(search_options, after_cursor):
            page_num += 1

            total_deals_processed += await self._process_deals_page(
                hubspot_client=hubspot_client,
                config=config,
                job_id=job_id,
                db_pool=db_pool,
                pipelines=pipelines,
                deals=page.results,
                page_num=page_num,
                total_deals_processed=total_deals_processed,
                trigger_indexing=trigger_indexing,
            )

        logger.info(
            "Completed HubSpot deal backfill",
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
            processed_deals=total_deals_processed,
        )

        if config.backfill_id:
            await increment_backfill_attempted_ingest_jobs(config.backfill_id, config.tenant_id, 1)
            await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

    async def _get_deal_custom_properties(self, db_pool: asyncpg.Pool) -> list[HubSpotProperty]:
        async with db_pool.acquire() as conn:
            return await hubspot_custom_properties.get_by_object_type(object_type="deal", conn=conn)

    async def _process_deals_page(
        self,
        hubspot_client: HubSpotClient,
        config: HubSpotDealBackfillConfig,
        job_id: str,
        db_pool: asyncpg.Pool,
        pipelines: list[dict[str, Any]],
        deals: list[Any],
        page_num: int,
        total_deals_processed: int,
        trigger_indexing: Callable[
            [list[str], DocumentSource, str, str | None, bool], Awaitable[None]
        ],
    ) -> int:
        logger.info(f"Hubspot deal page {page_num}: fetched {len(deals)} deals")

        if not deals:
            return 0

        # Fetch associated companies
        associations, companies = await self._fetch_associated_companies(
            hubspot_client, deals, config.tenant_id
        )

        # Fetch deal activities
        deal_activities = await self._fetch_deal_activities(hubspot_client, deals, config.tenant_id)
        # Convert deals to artifacts with embedded data
        artifacts = self._deals_to_artifacts(
            deals, associations, companies, deal_activities, pipelines, job_id
        )

        # Store this page of artifacts
        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

            logger.info(
                f"Hubspot Processed page {page_num}: {len(artifacts)} deals "
                f"(total: {total_deals_processed + len(artifacts)})"
            )

            # Trigger indexing for this page's deals immediately
            entity_ids = [artifact.entity_id for artifact in artifacts]
            await trigger_indexing(
                entity_ids,
                DocumentSource.HUBSPOT_DEAL,
                config.tenant_id,
                config.backfill_id,
                config.suppress_notification,
            )

            # Track index job for backfill progress (one job per page)
            if config.backfill_id:
                await increment_backfill_total_index_jobs(config.backfill_id, config.tenant_id, 1)

        return len(artifacts)

    async def _fetch_deal_activities(
        self, hubspot_client: HubSpotClient, deals: Sequence[Any], tenant_id: str
    ) -> dict[str, dict[str, list[Any]]]:
        deal_ids = [str(deal.id) for deal in deals]
        return await hubspot_client.get_deals_activities(deal_ids, HUBSPOT_ACTIVITY_ALL_PROPERTIES)

    async def _fetch_associated_companies(
        self, hubspot_client: HubSpotClient, deals: Sequence[Any], tenant_id: str
    ) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
        # Extract deal IDs
        deal_ids = [str(deal.id) for deal in deals]

        # Get company associations for these deals
        associations = await hubspot_client.get_company_associations("deals", deal_ids)
        logger.info(f"Hubspot fetched associations for {len(associations)} deals")

        # Extract unique company IDs from associations
        all_company_ids = set[str]()
        for company_ids in associations.values():
            all_company_ids.update(company_ids)

        # Batch fetch company data
        companies = {}
        if all_company_ids:
            # Explicit business logic: exclude archived companies
            companies = await hubspot_client.batch_read_companies(
                list(all_company_ids), filters={"archived": False}
            )
            logger.info(f"Hubspot fetched {len(companies)} companies")

        return associations, companies

    def _deals_to_artifacts(
        self,
        deals: Sequence[Any],
        associations: dict[str, list[str]],
        companies: dict[str, dict[str, Any]],
        deal_activities: dict[str, dict[str, list[Any]]],
        pipelines: list[dict[str, Any]],
        job_id: str,
    ) -> list[HubspotDealArtifact]:
        """Convert deals to artifacts with embedded company and pipeline info.

        Args:
            deals: List of deal objects from API
            associations: Deal ID -> list of company IDs mapping
            companies: Company ID -> company data mapping
            pipelines: Pipeline ID -> pipeline data mapping
            job_id: Job ID for tracking

        Returns:
            List of deal artifacts
        """
        artifacts = []
        for deal in deals:
            artifact = self._deal_to_artifact(
                deal, associations, companies, deal_activities, pipelines, job_id
            )
            artifacts.append(artifact)

        return artifacts

    def _deal_to_artifact(
        self,
        deal: Any,
        associations: dict[str, list[str]],
        companies: dict[str, dict[str, Any]],
        deal_activities: dict[str, dict[str, list[Any]]],
        pipelines: list[dict[str, Any]],
        job_id: str,
    ) -> HubspotDealArtifact:
        """Convert a single deal to an artifact.

        Args:
            deal: Deal object from API
            associations: Deal ID -> list of company IDs mapping
            companies: Company ID -> company data mapping
            pipelines: Pipeline ID -> pipeline data mapping
            job_id: Job ID for tracking

        Returns:
            Deal artifact
        """
        # Convert deal to dict and handle datetimes
        deal_data = deal.to_dict()
        deal_data = self._convert_datetimes_to_iso(deal_data)

        deal_id = str(deal.id)
        deal_properties = deal_data.get("properties", {})

        # Get associated company IDs
        company_ids = associations.get(deal_id, [])

        # Get deal activities
        activities = deal_activities.get(deal_id, {})

        # Get company names
        company_names = self._extract_company_names(company_ids, companies)

        # Resolve pipeline and stage names
        pipeline_name, stage_name = self._resolve_pipeline_and_stage_names(
            deal_properties, pipelines
        )

        # Build content with complete deal data structure matching API response
        content = {
            "id": deal_id,
            "properties": deal_properties,
            "createdAt": deal_data.get("created_at"),
            "updatedAt": deal_data.get("updated_at"),
            "archived": deal_data.get("archived", False),
            # Our additions for convenience:
            "pipeline_name": pipeline_name,
            "stage_name": stage_name,
            "company_names": company_names,
            "activities": activities,
        }

        # Create artifact
        return self._create_deal_artifact(
            deal_id, deal_properties, content, company_ids, job_id, deal_data
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
        company_names: list[str] = []
        for company_id in company_ids:
            if company_id in companies:
                company_data = companies[company_id]
                company_name = company_data.get("properties", {}).get("name")
                if company_name:
                    company_names.append(company_name)
        return company_names

    def _create_deal_artifact(
        self,
        deal_id: str,
        deal_properties: dict[str, Any],
        content: dict[str, Any],
        company_ids: list[str],
        job_id: str,
        deal_data: dict[str, Any],
    ) -> HubspotDealArtifact:
        """Create a HubSpot deal artifact.

        Args:
            deal_id: Deal ID
            deal_properties: Deal properties
            content: Content for the artifact
            company_ids: Associated company IDs
            job_id: Job ID for tracking

        Returns:
            Deal artifact
        """
        metadata = {
            "deal_id": deal_id,
            "pipeline_id": deal_properties.get("pipeline"),
            "stage_id": deal_properties.get("dealstage"),
            "company_ids": company_ids,
            "source_created_at": deal_data.get("created_at"),
            "source_updated_at": deal_data.get("updated_at"),
        }

        # Use actual updated_at from HubSpot, fallback to now if missing
        source_updated_at = deal_data.get("updated_at")

        if isinstance(source_updated_at, str):
            source_updated_at = datetime.fromisoformat(source_updated_at.replace("Z", "+00:00"))
        elif not source_updated_at:
            source_updated_at = datetime.now(tz=UTC)

        return HubspotDealArtifact(
            entity_id=get_hubspot_deal_entity_id(deal_id=deal_id),
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
        self, deal: dict[str, Any], pipelines: list[dict[str, Any]]
    ) -> tuple[str | None, str | None]:
        """Resolve pipeline and stage names from IDs.

        Args:
            deal: Deal data with pipeline and dealstage fields
            pipelines: Pipeline data from API

        Returns:
            Tuple of (pipeline_name, stage_name)
        """
        pipeline_id = deal.get("pipeline")
        stage_id = deal.get("dealstage")

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
