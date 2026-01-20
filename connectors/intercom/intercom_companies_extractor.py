import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_api_types import IntercomCompanyData
from connectors.intercom.intercom_artifacts import (
    IntercomCompanyArtifact,
    IntercomCompanyArtifactContent,
    IntercomCompanyArtifactMetadata,
)
from connectors.intercom.intercom_extractor import IntercomExtractor
from connectors.intercom.intercom_models import IntercomApiCompaniesBackfillConfig
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.tenant_config import get_tenant_config_value, set_tenant_config_value

logger = logging.getLogger(__name__)


class IntercomCompaniesBackfillExtractor(IntercomExtractor[IntercomApiCompaniesBackfillConfig]):
    """Extractor for processing Intercom companies backfill jobs."""

    source_name = "intercom_api_companies_backfill"

    async def process_job(
        self,
        job_id: str,
        config: IntercomApiCompaniesBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process Intercom companies for a tenant."""
        try:
            if config.company_ids:
                await self.process_companies_batch(
                    db_pool=db_pool,
                    job_id=job_id,
                    trigger_indexing=trigger_indexing,
                    tenant_id=config.tenant_id,
                    company_ids=config.company_ids or [],
                    backfill_id=config.backfill_id,
                    suppress_notification=config.suppress_notification,
                )
            else:
                await self.process_all_companies(
                    job_id=job_id,
                    config=config,
                    db_pool=db_pool,
                    trigger_indexing=trigger_indexing,
                )
        except Exception as e:
            logger.error(f"Failed to process Intercom companies backfill: {e}", exc_info=True)
            raise

    async def process_all_companies(
        self,
        job_id: str,
        config: IntercomApiCompaniesBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process companies from Intercom API using list API with client-side updated_at filtering.

        Note: The Intercom Companies API doesn't have a search endpoint, so we use the list API
        and filter client-side by comparing updated_at against stored artifacts.
        """
        tenant_id = config.tenant_id
        intercom_client = await self.get_intercom_client(tenant_id, db_pool)

        # Fetch workspace_id once for all batches
        workspace_id = await self.get_workspace_id(intercom_client)

        # Get last sync timestamp from config for client-side filtering
        last_sync_key = "INTERCOM_COMPANIES_LAST_SYNC_UPDATED_AT"
        last_sync_str = await get_tenant_config_value(last_sync_key, tenant_id)

        updated_at_after: int | None = None
        if last_sync_str:
            try:
                last_sync_dt = datetime.fromisoformat(last_sync_str)
                updated_at_after = int(last_sync_dt.timestamp())
                logger.info(
                    f"Will filter companies updated after: {last_sync_dt.isoformat()} ({updated_at_after})",
                    extra={"tenant_id": tenant_id, "last_sync": last_sync_dt.isoformat()},
                )
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to parse last sync timestamp '{last_sync_str}': {e}, will sync all",
                    extra={"tenant_id": tenant_id},
                )
        else:
            logger.info(
                "No last sync timestamp found, will sync all companies",
                extra={"tenant_id": tenant_id},
            )

        per_page = max(1, min(config.per_page, 50))  # Intercom Companies API max is 50
        starting_after = config.starting_after
        page_count = 0
        total_companies_processed = 0
        total_companies_skipped = 0
        current_max_updated_at: int | None = None

        logger.info(
            "Starting Intercom companies backfill using list API",
            extra={
                "tenant_id": tenant_id,
                "per_page": per_page,
                "updated_at_after": updated_at_after,
                "max_pages": config.max_pages,
                "max_companies": config.max_companies,
            },
        )

        while True:
            if config.max_pages and page_count >= config.max_pages:
                logger.info(
                    "Reached max pages limit for Intercom companies backfill",
                    extra={"tenant_id": tenant_id, "max_pages": config.max_pages},
                )
                break

            try:
                logger.debug(
                    "Fetching Intercom companies page",
                    extra={
                        "tenant_id": tenant_id,
                        "page": page_count + 1,
                        "starting_after": starting_after,
                    },
                )

                response = intercom_client.get_companies(
                    per_page=per_page,
                    starting_after=starting_after,
                    order=config.order,
                )

                companies = response.get("data", [])
                if not companies:
                    logger.info(
                        "No more companies to process",
                        extra={"tenant_id": tenant_id, "page": page_count + 1},
                    )
                    break

                # Filter companies client-side based on updated_at
                companies_to_process: list[dict[str, Any]] = []
                for company in companies:
                    company_updated_at = company.get("updated_at")
                    if company_updated_at:
                        try:
                            company_updated_at_int = (
                                int(company_updated_at)
                                if isinstance(company_updated_at, str)
                                else company_updated_at
                            )
                            # Track max updated_at for later
                            if (
                                current_max_updated_at is None
                                or company_updated_at_int > current_max_updated_at
                            ):
                                current_max_updated_at = company_updated_at_int

                            # Skip if company hasn't been updated since last sync
                            if updated_at_after and company_updated_at_int <= updated_at_after:
                                total_companies_skipped += 1
                                continue
                        except (ValueError, TypeError):
                            pass

                    companies_to_process.append(company)

                if companies_to_process:
                    company_ids = [str(c.get("id")) for c in companies_to_process if c.get("id")]
                    if company_ids:
                        await self.process_companies_batch(
                            db_pool=db_pool,
                            job_id=job_id,
                            trigger_indexing=trigger_indexing,
                            tenant_id=tenant_id,
                            company_ids=company_ids,
                            backfill_id=config.backfill_id,
                            suppress_notification=config.suppress_notification,
                            intercom_client=intercom_client,
                            workspace_id=workspace_id,
                        )
                        total_companies_processed += len(company_ids)

                page_count += 1

                # Check max companies limit
                if config.max_companies and total_companies_processed >= config.max_companies:
                    logger.info(
                        f"Reached max companies limit: {config.max_companies}",
                        extra={"tenant_id": tenant_id},
                    )
                    break

                # Get pagination cursor (per Intercom docs: pages.next is an object with starting_after)
                pages = response.get("pages")
                if not isinstance(pages, dict):
                    logger.info(
                        "No more pages to process (pages is not a dict)",
                        extra={
                            "tenant_id": tenant_id,
                            "page": page_count,
                            "pages_type": type(pages).__name__,
                        },
                    )
                    break

                next_obj = pages.get("next")
                if not isinstance(next_obj, dict):
                    logger.info(
                        "No more pages to process (no next object)",
                        extra={"tenant_id": tenant_id, "page": page_count},
                    )
                    break

                starting_after = next_obj.get("starting_after")
                if not starting_after:
                    logger.info(
                        "No more pages to process",
                        extra={"tenant_id": tenant_id, "page": page_count},
                    )
                    break

            except Exception as e:
                logger.error(
                    f"Failed to fetch companies page: {e}",
                    exc_info=True,
                    extra={"tenant_id": tenant_id},
                )
                raise

        # Update last sync timestamp to the maximum updated_at we processed
        if current_max_updated_at is not None:
            last_sync_dt = datetime.fromtimestamp(current_max_updated_at, tz=UTC)
            await set_tenant_config_value(last_sync_key, last_sync_dt.isoformat(), tenant_id)
            logger.info(
                f"Updated last sync timestamp to: {last_sync_dt.isoformat()} ({current_max_updated_at})",
                extra={"tenant_id": tenant_id, "last_sync": last_sync_dt.isoformat()},
            )
        elif updated_at_after is None and total_companies_processed > 0:
            # If we didn't have a previous sync and processed companies, set timestamp to now
            now = datetime.now(tz=UTC)
            await set_tenant_config_value(last_sync_key, now.isoformat(), tenant_id)
            logger.info(
                f"Set initial last sync timestamp to: {now.isoformat()}",
                extra={"tenant_id": tenant_id, "last_sync": now.isoformat()},
            )

        logger.info(
            f"Completed Intercom companies backfill: {total_companies_processed} processed, "
            f"{total_companies_skipped} skipped (unchanged)",
            extra={
                "tenant_id": tenant_id,
                "companies_processed": total_companies_processed,
                "companies_skipped": total_companies_skipped,
            },
        )

    async def process_companies_batch(
        self,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        tenant_id: str,
        company_ids: list[str],
        backfill_id: str | None = None,
        suppress_notification: bool = False,
        intercom_client: Any | None = None,
        workspace_id: str | None = None,
    ) -> None:
        """Process a batch of companies by ID."""
        if not intercom_client:
            intercom_client = await self.get_intercom_client(tenant_id, db_pool)

        # Fetch workspace_id if not provided
        if workspace_id is None:
            workspace_id = await self.get_workspace_id(intercom_client)

        artifacts_to_store: list[IntercomCompanyArtifact] = []
        company_ids_for_indexing: list[str] = []

        successful_count = 0
        failed_count = 0

        # Fetch company data for each company ID
        for company_id in company_ids:
            try:
                logger.debug(f"Fetching company {company_id} from Intercom API")

                # Fetch company from Intercom API
                response = intercom_client.get_company(company_id)

                if not response:
                    logger.warning(
                        f"Could not fetch company {company_id} from Intercom API - empty response"
                    )
                    continue

                # Intercom API might wrap the company in a 'company' key or return it directly
                company_data = response
                if isinstance(response, dict) and "company" in response:
                    company_data = response["company"]
                elif isinstance(response, dict) and "id" not in response:
                    logger.warning(
                        f"Unexpected response structure for company {company_id}: {list(response.keys())}"
                    )
                    continue

                logger.debug(
                    f"Processing company {company_id} - has id: {'id' in company_data if isinstance(company_data, dict) else False}"
                )

                # Process company into artifact
                artifact = await self.process_company(
                    job_id, company_data, tenant_id, db_pool, workspace_id
                )
                artifacts_to_store.append(artifact)
                company_ids_for_indexing.append(artifact.entity_id)
                successful_count += 1

                logger.debug(
                    f"Successfully processed company {company_id} (entity_id: {artifact.entity_id})"
                )

            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to process company {company_id}: {e}", exc_info=True)
                continue

        # Store artifacts in batches
        if artifacts_to_store:
            batch_size = DEFAULT_INDEX_BATCH_SIZE
            for i in range(0, len(artifacts_to_store), batch_size):
                batch = artifacts_to_store[i : i + batch_size]
                await self.store_artifacts_batch(db_pool, batch)
                logger.debug(f"Stored batch of {len(batch)} company artifacts")

        # Trigger indexing for all successfully processed companies
        if company_ids_for_indexing:
            await trigger_indexing(
                entity_ids=company_ids_for_indexing,
                source=DocumentSource.INTERCOM,
                tenant_id=tenant_id,
                backfill_id=backfill_id,
                suppress_notification=suppress_notification,
            )
            logger.info(
                f"Triggered indexing for {len(company_ids_for_indexing)} companies "
                f"(successful: {successful_count}, failed: {failed_count})"
            )

    async def process_company(
        self,
        job_id: str,
        company_data: dict[str, Any],
        tenant_id: str,
        db_pool: asyncpg.Pool,
        workspace_id: str | None = None,
    ) -> IntercomCompanyArtifact:
        """Process a single company and create an artifact."""
        company_id = str(company_data.get("id", ""))
        if not company_id:
            raise ValueError("Company data missing 'id' field")

        # Normalize timestamps
        def _normalize_timestamp(value: Any | None) -> tuple[str, datetime]:
            if value is None:
                now = datetime.now(tz=UTC)
                return str(int(now.timestamp())), now

            if isinstance(value, (int, float)):
                dt = datetime.fromtimestamp(value, tz=UTC)
                return str(int(value)), dt

            if isinstance(value, str):
                try:
                    # Attempt to parse ISO-style strings
                    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
                    return value, dt
                except ValueError:
                    # Fall back to treating numeric strings as epoch seconds
                    try:
                        epoch = int(value)
                        dt = datetime.fromtimestamp(epoch, tz=UTC)
                        return str(epoch), dt
                    except ValueError:
                        pass
            # Fallback: use current time
            now = datetime.now(tz=UTC)
            return str(int(now.timestamp())), now

        created_at_raw = company_data.get("created_at")
        created_at_str, created_at_dt = _normalize_timestamp(created_at_raw)

        updated_at_raw = company_data.get("updated_at")
        updated_at_str, updated_at_dt = _normalize_timestamp(updated_at_raw or created_at_raw)

        # Use passed workspace_id, or try to get from company data (unlikely to be present)
        effective_workspace_id = workspace_id or company_data.get("workspace_id")

        metadata = IntercomCompanyArtifactMetadata(
            company_id=company_id,
            name=company_data.get("name"),
            created_at=created_at_str,
            updated_at=updated_at_str,
            workspace_id=effective_workspace_id,
        )

        # Convert raw dict to typed Pydantic model, injecting workspace_id if available
        company_data_with_workspace = {**company_data}
        if effective_workspace_id:
            company_data_with_workspace["workspace_id"] = effective_workspace_id
        typed_company_data = IntercomCompanyData.model_validate(company_data_with_workspace)

        content = IntercomCompanyArtifactContent(
            company_data=typed_company_data,
        )

        artifact = IntercomCompanyArtifact(
            entity_id=company_id,
            ingest_job_id=UUID(job_id),
            content=content,
            metadata=metadata,
            # Use Intercom's updated_at timestamp so re-runs only upsert when data changes
            source_updated_at=updated_at_dt,
        )

        return artifact
