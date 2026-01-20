import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_api_types import IntercomContactData
from connectors.intercom.intercom_artifacts import (
    IntercomContactArtifact,
    IntercomContactArtifactContent,
    IntercomContactArtifactMetadata,
)
from connectors.intercom.intercom_extractor import IntercomExtractor
from connectors.intercom.intercom_models import IntercomApiContactsBackfillConfig
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.tenant_config import get_tenant_config_value, set_tenant_config_value

logger = logging.getLogger(__name__)


class IntercomContactsBackfillExtractor(IntercomExtractor[IntercomApiContactsBackfillConfig]):
    """Extractor for processing Intercom contacts backfill jobs."""

    source_name = "intercom_api_contacts_backfill"

    async def process_job(
        self,
        job_id: str,
        config: IntercomApiContactsBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process Intercom contacts for a tenant."""
        try:
            if config.contact_ids:
                await self.process_contacts_batch(
                    db_pool=db_pool,
                    job_id=job_id,
                    trigger_indexing=trigger_indexing,
                    tenant_id=config.tenant_id,
                    contact_ids=config.contact_ids or [],
                    backfill_id=config.backfill_id,
                    suppress_notification=config.suppress_notification,
                )
            else:
                await self.process_all_contacts(
                    job_id=job_id,
                    config=config,
                    db_pool=db_pool,
                    trigger_indexing=trigger_indexing,
                )
        except Exception as e:
            logger.error(f"Failed to process Intercom contacts backfill: {e}", exc_info=True)
            raise

    async def process_all_contacts(
        self,
        job_id: str,
        config: IntercomApiContactsBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process contacts from Intercom API using search API with updated_at filter."""
        tenant_id = config.tenant_id
        intercom_client = await self.get_intercom_client(tenant_id, db_pool)

        # Fetch workspace_id once for all batches
        workspace_id = await self.get_workspace_id(intercom_client)

        # Get last sync timestamp from config
        last_sync_key = "INTERCOM_CONTACTS_LAST_SYNC_UPDATED_AT"
        last_sync_str = await get_tenant_config_value(last_sync_key, tenant_id)

        # Convert to Unix timestamp for Intercom API (they expect Unix epoch seconds)
        updated_at_after: int | None = None
        if last_sync_str:
            try:
                last_sync_dt = datetime.fromisoformat(last_sync_str)
                updated_at_after = int(last_sync_dt.timestamp())
                logger.info(
                    f"Using last sync timestamp: {last_sync_dt.isoformat()} ({updated_at_after})",
                    extra={"tenant_id": tenant_id, "last_sync": last_sync_dt.isoformat()},
                )
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to parse last sync timestamp '{last_sync_str}': {e}, starting from beginning",
                    extra={"tenant_id": tenant_id},
                )
        else:
            logger.info(
                "No last sync timestamp found, will sync all contacts",
                extra={"tenant_id": tenant_id},
            )

        per_page = max(1, min(config.per_page, 150))  # Intercom max is 150
        starting_after = config.starting_after
        page_count = 0
        total_contacts = 0
        current_max_updated_at: int | None = None

        # Use search API when filtering by timestamp, otherwise use list API
        use_search = updated_at_after is not None

        logger.info(
            f"Starting Intercom contacts backfill using {'search' if use_search else 'list'} API",
            extra={
                "tenant_id": tenant_id,
                "per_page": per_page,
                "updated_at_after": updated_at_after,
                "max_pages": config.max_pages,
                "max_contacts": config.max_contacts,
                "use_search": use_search,
            },
        )

        while True:
            if config.max_pages and page_count >= config.max_pages:
                logger.info(
                    "Reached max pages limit for Intercom contacts backfill",
                    extra={"tenant_id": tenant_id, "max_pages": config.max_pages},
                )
                break

            try:
                logger.debug(
                    f"{'Searching' if use_search else 'Fetching'} Intercom contacts",
                    extra={
                        "tenant_id": tenant_id,
                        "page": page_count + 1,
                        "starting_after": starting_after,
                        "updated_at_after": updated_at_after,
                    },
                )

                # Use appropriate API based on whether we're filtering
                if use_search:
                    response = intercom_client.search_contacts(
                        updated_at_after=updated_at_after,
                        per_page=per_page,
                        starting_after=starting_after,
                    )
                else:
                    # For first-time backfill without timestamp filter, use list API
                    # Note: Both list and search APIs support per_page up to 150
                    list_per_page = max(1, min(config.per_page, 150))
                    response = intercom_client.get_contacts(
                        per_page=list_per_page,
                        starting_after=starting_after,
                        order=config.order,
                    )

                contacts = response.get("data", [])
                if not contacts:
                    logger.info(
                        "No more contacts to process",
                        extra={"tenant_id": tenant_id, "page": page_count + 1},
                    )
                    break

                # Track the maximum updated_at we've seen for this batch
                for contact in contacts:
                    contact_updated_at = (
                        contact.get("updated_at")
                        or contact.get("updated")
                        or contact.get("created_at")
                        or contact.get("created")
                    )
                    if contact_updated_at:
                        try:
                            # Convert to int if it's a string
                            contact_updated_at_int = (
                                int(contact_updated_at)
                                if isinstance(contact_updated_at, str)
                                else contact_updated_at
                            )
                            if (
                                current_max_updated_at is None
                                or contact_updated_at_int > current_max_updated_at
                            ):
                                current_max_updated_at = contact_updated_at_int
                        except (ValueError, TypeError):
                            pass

                contact_ids = [str(contact.get("id")) for contact in contacts if contact.get("id")]

                if not contact_ids:
                    logger.warning(
                        "No valid contact IDs found in response",
                        extra={"tenant_id": tenant_id},
                    )
                    break

                # Process this batch
                await self.process_contacts_batch(
                    db_pool=db_pool,
                    job_id=job_id,
                    trigger_indexing=trigger_indexing,
                    tenant_id=tenant_id,
                    contact_ids=contact_ids,
                    backfill_id=config.backfill_id,
                    suppress_notification=config.suppress_notification,
                    intercom_client=intercom_client,
                    workspace_id=workspace_id,
                )

                total_contacts += len(contact_ids)
                page_count += 1

                # Check max contacts limit
                if config.max_contacts and total_contacts >= config.max_contacts:
                    logger.info(
                        f"Reached max contacts limit: {config.max_contacts}",
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
                    f"Failed to fetch contacts page: {e}",
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
        elif updated_at_after is None and total_contacts > 0:
            # If we didn't have a previous sync and processed contacts, set timestamp to now
            now = datetime.now(tz=UTC)
            await set_tenant_config_value(last_sync_key, now.isoformat(), tenant_id)
            logger.info(
                f"Set initial last sync timestamp to: {now.isoformat()}",
                extra={"tenant_id": tenant_id, "last_sync": now.isoformat()},
            )

        logger.info(
            f"Completed Intercom contacts backfill: {total_contacts} contacts processed",
            extra={"tenant_id": tenant_id, "contacts_processed": total_contacts},
        )

    async def process_contacts_batch(
        self,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        tenant_id: str,
        contact_ids: list[str],
        backfill_id: str | None = None,
        suppress_notification: bool = False,
        intercom_client: Any | None = None,
        workspace_id: str | None = None,
    ) -> None:
        """Process a batch of contacts by ID."""
        if not intercom_client:
            intercom_client = await self.get_intercom_client(tenant_id, db_pool)

        # Fetch workspace_id if not provided
        if workspace_id is None:
            workspace_id = await self.get_workspace_id(intercom_client)

        artifacts_to_store: list[IntercomContactArtifact] = []
        contact_ids_for_indexing: list[str] = []

        successful_count = 0
        failed_count = 0

        # Fetch contact data for each contact ID
        for contact_id in contact_ids:
            try:
                logger.debug(f"Fetching contact {contact_id} from Intercom API")

                # Fetch contact from Intercom API
                response = intercom_client.get_contact(contact_id)

                if not response:
                    logger.warning(
                        f"Could not fetch contact {contact_id} from Intercom API - empty response"
                    )
                    continue

                # Intercom API might wrap the contact in a 'contact' key or return it directly
                contact_data = response
                if isinstance(response, dict) and "contact" in response:
                    contact_data = response["contact"]
                elif isinstance(response, dict) and "id" not in response:
                    logger.warning(
                        f"Unexpected response structure for contact {contact_id}: {list(response.keys())}"
                    )
                    continue

                logger.debug(
                    f"Processing contact {contact_id} - has id: {'id' in contact_data if isinstance(contact_data, dict) else False}"
                )

                # Process contact into artifact
                artifact = await self.process_contact(
                    job_id, contact_data, tenant_id, db_pool, workspace_id
                )
                artifacts_to_store.append(artifact)
                contact_ids_for_indexing.append(artifact.entity_id)
                successful_count += 1

                logger.debug(
                    f"Successfully processed contact {contact_id} (entity_id: {artifact.entity_id})"
                )

            except Exception as e:
                failed_count += 1
                logger.error(f"Failed to process contact {contact_id}: {e}", exc_info=True)
                continue

        # Store artifacts in batches
        if artifacts_to_store:
            batch_size = DEFAULT_INDEX_BATCH_SIZE
            for i in range(0, len(artifacts_to_store), batch_size):
                batch = artifacts_to_store[i : i + batch_size]
                await self.store_artifacts_batch(db_pool, batch)
                logger.debug(f"Stored batch of {len(batch)} contact artifacts")

        # Trigger indexing for all successfully processed contacts
        if contact_ids_for_indexing:
            await trigger_indexing(
                entity_ids=contact_ids_for_indexing,
                source=DocumentSource.INTERCOM,
                tenant_id=tenant_id,
                backfill_id=backfill_id,
                suppress_notification=suppress_notification,
            )
            logger.info(
                f"Triggered indexing for {len(contact_ids_for_indexing)} contacts "
                f"(successful: {successful_count}, failed: {failed_count})"
            )

    async def process_contact(
        self,
        job_id: str,
        contact_data: dict[str, Any],
        tenant_id: str,
        db_pool: asyncpg.Pool,
        workspace_id: str | None = None,
    ) -> IntercomContactArtifact:
        """Process a single contact and create an artifact."""
        contact_id = str(contact_data.get("id", ""))
        if not contact_id:
            raise ValueError("Contact data missing 'id' field")

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

        created_at_raw = contact_data.get("created_at")
        created_at_str, created_at_dt = _normalize_timestamp(created_at_raw)

        updated_at_raw = contact_data.get("updated_at")
        updated_at_str, updated_at_dt = _normalize_timestamp(updated_at_raw or created_at_raw)

        # Use passed workspace_id, or try to get from contact data (unlikely to be present)
        effective_workspace_id = workspace_id or contact_data.get("workspace_id")

        metadata = IntercomContactArtifactMetadata(
            contact_id=contact_id,
            email=contact_data.get("email"),
            name=contact_data.get("name"),
            role=contact_data.get("role"),
            created_at=created_at_str,
            updated_at=updated_at_str,
            workspace_id=effective_workspace_id,
        )

        # Convert raw dict to typed Pydantic model, injecting workspace_id if available
        contact_data_with_workspace = {**contact_data}
        if effective_workspace_id:
            contact_data_with_workspace["workspace_id"] = effective_workspace_id
        typed_contact_data = IntercomContactData.model_validate(contact_data_with_workspace)

        content = IntercomContactArtifactContent(
            contact_data=typed_contact_data,
        )

        artifact = IntercomContactArtifact(
            entity_id=contact_id,
            ingest_job_id=UUID(job_id),
            content=content,
            metadata=metadata,
            # Use Intercom's updated_at timestamp so re-runs only upsert when data changes
            source_updated_at=updated_at_dt,
        )

        return artifact
