from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, get_hubspot_contact_entity_id
from connectors.base.document_source import DocumentSource
from connectors.hubspot.hubspot_artifacts import (
    HUBSPOT_CONTACT_PROPERTIES,
    HubspotContactArtifact,
)
from connectors.hubspot.hubspot_models import HubSpotContactBackfillConfig
from src.clients.hubspot.hubspot_client import HubSpotClient, HubSpotProperty
from src.clients.hubspot.hubspot_factory import get_hubspot_client_for_tenant
from src.clients.hubspot.hubspot_models import (
    HubSpotSearchDateFilter,
    HubSpotSearchOptions,
)
from src.clients.ssm import SSMClient
from src.ingest.services.hubspot_custom_properties import hubspot_custom_properties
from src.utils.logging import get_logger
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = get_logger(__name__)

INDEX_BATCH_SIZE = 200


class HubSpotContactBackfillExtractor(BaseExtractor[HubSpotContactBackfillConfig]):
    source_name = "hubspot_contact_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client

    async def process_job(
        self,
        job_id: str,
        config: HubSpotContactBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: Callable[
            [list[str], DocumentSource, str, str | None, bool], Awaitable[None]
        ],
    ) -> None:
        logger.info(
            "Processing HubSpot contact backfill",
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
        )

        # Get HubSpot client from factory
        hubspot_client = await get_hubspot_client_for_tenant(
            config.tenant_id, self.ssm_client, db_pool
        )

        custom_properties = await self._get_contact_custom_properties(db_pool)
        custom_properties_names = [property.name for property in custom_properties]
        logger.info(
            f"[tenant={config.tenant_id}] Found {len(custom_properties_names)} custom properties for contacts"
        )

        # Pagination loop for this month's contacts
        total_contacts_processed = 0
        page_num = 0

        search_options = HubSpotSearchOptions(
            properties=list(HUBSPOT_CONTACT_PROPERTIES.keys()) + custom_properties_names,
            date_filter=HubSpotSearchDateFilter(start=config.start_date, end=config.end_date),
            search_by="createdate",
        )

        async for res in hubspot_client.search_contacts(search_options):
            page_num += 1

            # Process one page of contacts
            total_contacts_processed += await self._process_contacts_page(
                hubspot_client=hubspot_client,
                config=config,
                job_id=job_id,
                db_pool=db_pool,
                contacts=res.results,
                page_num=page_num,
                total_contacts_processed=total_contacts_processed,
                trigger_indexing=trigger_indexing,
            )

        logger.info(
            "Completed HubSpot contact backfill",
            start_date=config.start_date.isoformat(),
            end_date=config.end_date.isoformat(),
            total_contacts_processed=total_contacts_processed,
        )

        if config.backfill_id:
            await increment_backfill_attempted_ingest_jobs(config.backfill_id, config.tenant_id, 1)
            await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

    async def _get_contact_custom_properties(self, db_pool: asyncpg.Pool) -> list[HubSpotProperty]:
        async with db_pool.acquire() as conn:
            return await hubspot_custom_properties.get_by_object_type(
                object_type="contact", conn=conn
            )

    async def _process_contacts_page(
        self,
        hubspot_client: HubSpotClient,
        config: HubSpotContactBackfillConfig,
        job_id: str,
        db_pool: asyncpg.Pool,
        contacts: list[Any],
        page_num: int,
        total_contacts_processed: int,
        trigger_indexing: Callable[
            [list[str], DocumentSource, str, str | None, bool], Awaitable[None]
        ],
    ) -> int:
        logger.info("Hubspot contact page fetched", page_num=page_num, contact_count=len(contacts))

        if not contacts:
            return 0

        # Fetch associated companies
        associations, companies = await fetch_associated_companies_for_contacts(
            hubspot_client, contacts
        )

        # Convert contacts to artifacts with embedded data
        artifacts = contacts_to_artifacts(contacts, associations, companies, job_id)
        # Store this page of artifacts
        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

            logger.info(
                f"Hubspot contact page processed {page_num}: {len(artifacts)} contacts "
                f"(total: {total_contacts_processed + len(artifacts)})"
            )

            # Trigger indexing for this page's contacts immediately
            entity_ids = [artifact.entity_id for artifact in artifacts]
            await trigger_indexing(
                entity_ids,
                DocumentSource.HUBSPOT_CONTACT,
                config.tenant_id,
                config.backfill_id,
                config.suppress_notification,
            )

            # Track index job for backfill progress (one job per page)
            if config.backfill_id:
                await increment_backfill_total_index_jobs(config.backfill_id, config.tenant_id, 1)

        return len(artifacts)


async def fetch_associated_companies_for_contacts(
    client: HubSpotClient, contacts: Sequence[Any]
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    contact_ids = [str(contact.id) for contact in contacts]

    # Get company associations for these contacts
    associations = await client.get_company_associations("contacts", contact_ids)
    logger.info(f"Hubspot Fetched associations for {len(associations)} contacts")

    # Extract unique company IDs from associations
    all_company_ids = set[str]()
    for company_ids in associations.values():
        all_company_ids.update(company_ids)

    # Batch fetch company data
    companies = {}
    if all_company_ids:
        # Explicit business logic: exclude archived companies
        companies = await client.batch_read_companies(
            list(all_company_ids), filters={"archived": False}
        )
        logger.info(f"Hubspot Fetched {len(companies)} companies")

    return associations, companies


def contacts_to_artifacts(
    contacts: Sequence[Any],
    associations: dict[str, list[str]],
    companies: dict[str, dict[str, Any]],
    job_id: str,
) -> list[HubspotContactArtifact]:
    return [contact_to_artifact(contact, associations, companies, job_id) for contact in contacts]


def contact_to_artifact(
    contact: Any,
    associations: dict[str, list[str]],
    companies: dict[str, dict[str, Any]],
    job_id: str,
) -> HubspotContactArtifact:
    # Convert contact to dict and handle datetimes
    contact_data = contact.to_dict()
    contact_data = _convert_datetimes_to_iso(contact_data)

    contact_id = str(contact.id)
    contact_properties = contact_data.get("properties", {})

    # Get associated company IDs
    company_ids = associations.get(contact_id, [])

    # Get company names
    company_names = _extract_company_names(company_ids, companies)

    # Build content with complete contact data structure matching API response
    content = {
        "id": contact_id,
        "properties": contact_properties,
        "createdAt": contact_data.get("created_at"),
        "updatedAt": contact_data.get("updated_at"),
        "archived": contact_data.get("archived", False),
        # Our additions for convenience:
        "company_names": company_names,
    }

    metadata = {
        "contact_id": contact_id,
        "company_ids": company_ids,
        "source_created_at": contact_data.get("created_at"),
        "source_updated_at": contact_data.get("updated_at"),
    }

    # Use actual updated_at from HubSpot, fallback to now if missing
    source_updated_at = contact_data.get("updated_at")

    if isinstance(source_updated_at, str):
        source_updated_at = datetime.fromisoformat(source_updated_at.replace("Z", "+00:00"))
    elif not source_updated_at:
        source_updated_at = datetime.now(tz=UTC)

    return HubspotContactArtifact(
        entity_id=get_hubspot_contact_entity_id(contact_id=contact_id),
        ingest_job_id=UUID(job_id),
        content=content,
        metadata=metadata,
        source_updated_at=source_updated_at,
    )


def _extract_company_names(
    company_ids: list[str], companies: dict[str, dict[str, Any]]
) -> list[str]:
    company_names: list[str] = []
    for company_id in company_ids:
        if company_id in companies:
            company_data = companies[company_id]
            company_name = company_data.get("properties", {}).get("name")
            if company_name:
                company_names.append(company_name)
    return company_names


def _convert_datetimes_to_iso(data: Any) -> Any:
    """Recursively convert datetime objects to ISO format strings for JSON serialization."""
    if isinstance(data, datetime):
        return data.isoformat()
    elif isinstance(data, dict):
        return {key: _convert_datetimes_to_iso(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_convert_datetimes_to_iso(item) for item in data]
    return data
