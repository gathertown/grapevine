import logging
from datetime import UTC, datetime
from typing import Any

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.intercom.intercom_artifacts import IntercomConversationArtifact
from connectors.intercom.intercom_extractor import IntercomExtractor
from connectors.intercom.intercom_models import IntercomApiConversationsBackfillConfig
from src.clients.intercom import IntercomClient
from src.ingest.repositories import ArtifactRepository
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.tenant_config import get_tenant_config_value, set_tenant_config_value

logger = logging.getLogger(__name__)


class IntercomConversationsBackfillExtractor(
    IntercomExtractor[IntercomApiConversationsBackfillConfig]
):
    """Extractor for processing Intercom conversation backfill jobs."""

    source_name = "intercom_api_conversations_backfill"

    async def process_job(
        self,
        job_id: str,
        config: IntercomApiConversationsBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process Intercom conversations for a tenant."""
        try:
            if config.conversation_ids:
                conversation_list_data = [
                    {"id": conversation_id, "updated_at": None}
                    for conversation_id in config.conversation_ids
                    if conversation_id
                ]
                await self.process_conversations_batch(
                    db_pool=db_pool,
                    job_id=job_id,
                    trigger_indexing=trigger_indexing,
                    tenant_id=config.tenant_id,
                    conversation_list_data=conversation_list_data,
                    backfill_id=config.backfill_id,
                    suppress_notification=config.suppress_notification,
                )
            else:
                await self.process_all_conversations(
                    job_id=job_id,
                    config=config,
                    db_pool=db_pool,
                    trigger_indexing=trigger_indexing,
                )
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            raise

    async def process_all_conversations(
        self,
        job_id: str,
        config: IntercomApiConversationsBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Fetch and process conversations for a tenant using search API with updated_at filter."""
        tenant_id = config.tenant_id
        intercom_client = await self.get_intercom_client(tenant_id, db_pool)

        # Fetch workspace_id once for all batches
        workspace_id = await self.get_workspace_id(intercom_client)

        # Get last sync timestamp from config
        last_sync_key = "INTERCOM_CONVERSATIONS_LAST_SYNC_UPDATED_AT"
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
                "No last sync timestamp found, will sync all conversations",
                extra={"tenant_id": tenant_id},
            )

        per_page = max(1, min(config.per_page, 150))  # Intercom max is 150
        starting_after = config.starting_after
        processed_total = 0
        page_count = 0
        current_max_updated_at: int | None = None

        # Use search API when filtering by timestamp, otherwise use list API
        use_search = updated_at_after is not None

        logger.info(
            f"Starting Intercom conversations backfill using {'search' if use_search else 'list'} API",
            extra={
                "tenant_id": tenant_id,
                "per_page": per_page,
                "updated_at_after": updated_at_after,
                "max_pages": config.max_pages,
                "max_conversations": config.max_conversations,
                "use_search": use_search,
            },
        )

        while True:
            if config.max_pages is not None and page_count >= config.max_pages:
                logger.info(
                    "Reached max_pages limit for Intercom backfill",
                    extra={"tenant_id": tenant_id, "max_pages": config.max_pages},
                )
                break

            page_count += 1
            logger.debug(
                f"{'Searching' if use_search else 'Fetching'} Intercom conversations",
                extra={
                    "tenant_id": tenant_id,
                    "page": page_count,
                    "starting_after": starting_after,
                    "updated_at_after": updated_at_after,
                },
            )

            # Use appropriate API based on whether we're filtering
            if use_search:
                response = intercom_client.search_conversations(
                    updated_at_after=updated_at_after,
                    per_page=per_page,
                    starting_after=starting_after,
                )
            else:
                # For first-time backfill without timestamp filter, use list API
                # Note: Both list and search APIs support per_page up to 150
                list_per_page = max(1, min(config.per_page, 150))
                response = intercom_client.get_conversations(
                    per_page=list_per_page,
                    starting_after=starting_after,
                    order=config.order,
                )
            conversations = response.get("conversations", [])

            if not conversations:
                logger.info(
                    "No conversations returned for Intercom page",
                    extra={"tenant_id": tenant_id, "page": page_count},
                )
                break

            # Extract conversation IDs and their updated_at timestamps from the list
            conversation_list_data = []
            for conversation in conversations:
                conversation_id = conversation.get("id")
                if not conversation_id:
                    continue
                conversation_list_data.append(
                    {
                        "id": conversation_id,
                        "updated_at": conversation.get("updated_at")
                        or conversation.get("updated")
                        or conversation.get("created_at")
                        or conversation.get("created"),
                    }
                )

            if not conversation_list_data:
                logger.warning(
                    "Intercom API returned conversations without IDs",
                    extra={"tenant_id": tenant_id, "page": page_count},
                )
            else:
                if config.max_conversations is not None:
                    remaining = config.max_conversations - processed_total
                    if remaining <= 0:
                        logger.info(
                            "Reached max_conversations limit for Intercom backfill",
                            extra={
                                "tenant_id": tenant_id,
                                "max_conversations": config.max_conversations,
                            },
                        )
                        break
                    if len(conversation_list_data) > remaining:
                        conversation_list_data = conversation_list_data[:remaining]

                await self.process_conversations_batch(
                    db_pool=db_pool,
                    job_id=job_id,
                    trigger_indexing=trigger_indexing,
                    tenant_id=tenant_id,
                    conversation_list_data=conversation_list_data,
                    backfill_id=config.backfill_id,
                    suppress_notification=config.suppress_notification,
                    intercom_client=intercom_client,
                    workspace_id=workspace_id,
                )
                processed_total += len(conversation_list_data)

            # Track the maximum updated_at we've seen for this batch
            for conv in conversations:
                conv_updated_at = (
                    conv.get("updated_at")
                    or conv.get("updated")
                    or conv.get("created_at")
                    or conv.get("created")
                )
                if conv_updated_at:
                    try:
                        # Convert to int if it's a string
                        conv_updated_at_int = (
                            int(conv_updated_at)
                            if isinstance(conv_updated_at, str)
                            else conv_updated_at
                        )
                        if (
                            current_max_updated_at is None
                            or conv_updated_at_int > current_max_updated_at
                        ):
                            current_max_updated_at = conv_updated_at_int
                    except (ValueError, TypeError):
                        pass

            # Get pagination cursor (per Intercom docs: pages.next is an object with starting_after)
            pages = response.get("pages")
            if not isinstance(pages, dict):
                logger.info(
                    "No more Intercom pages available (pages is not a dict)",
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
                    "No additional Intercom pages available (no next object)",
                    extra={"tenant_id": tenant_id, "page": page_count},
                )
                break

            starting_after = next_obj.get("starting_after")
            if not starting_after:
                logger.info(
                    "No additional Intercom pages available",
                    extra={"tenant_id": tenant_id, "page": page_count},
                )
                break

        # Update last sync timestamp to the maximum updated_at we processed
        if current_max_updated_at is not None:
            last_sync_dt = datetime.fromtimestamp(current_max_updated_at, tz=UTC)
            await set_tenant_config_value(last_sync_key, last_sync_dt.isoformat(), tenant_id)
            logger.info(
                f"Updated last sync timestamp to: {last_sync_dt.isoformat()} ({current_max_updated_at})",
                extra={"tenant_id": tenant_id, "last_sync": last_sync_dt.isoformat()},
            )
        elif updated_at_after is None and processed_total > 0:
            # If we didn't have a previous sync and processed conversations, set timestamp to now
            now = datetime.now(tz=UTC)
            await set_tenant_config_value(last_sync_key, now.isoformat(), tenant_id)
            logger.info(
                f"Set initial last sync timestamp to: {now.isoformat()}",
                extra={"tenant_id": tenant_id, "last_sync": now.isoformat()},
            )

        logger.info(
            "Completed Intercom backfill",
            extra={"tenant_id": tenant_id, "conversations_processed": processed_total},
        )

    async def process_conversations_batch(
        self,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        tenant_id: str,
        conversation_list_data: list[dict[str, Any]],
        backfill_id: str | None = None,
        suppress_notification: bool = False,
        intercom_client: IntercomClient | None = None,
        workspace_id: str | None = None,
    ) -> None:
        """Process a batch of Intercom conversations.

        Args:
            conversation_list_data: List of dicts with 'id' and 'updated_at' from the list endpoint
        """
        try:
            if not conversation_list_data:
                logger.warning(
                    "Received empty conversation batch, skipping",
                    extra={"tenant_id": tenant_id},
                )
                return

            artifacts_to_store = []
            conversation_ids_for_indexing: list[str] = []

            # Extract conversation IDs for database lookup
            conversation_ids = [
                str(conv["id"]) for conv in conversation_list_data if conv.get("id")
            ]

            logger.info(
                f"Processing batch of {len(conversation_list_data)} Intercom conversations",
                extra={"tenant_id": tenant_id, "conversation_count": len(conversation_list_data)},
            )

            # Get Intercom client
            intercom_client = intercom_client or await self.get_intercom_client(tenant_id, db_pool)

            # Fetch workspace_id if not provided
            if workspace_id is None:
                workspace_id = await self.get_workspace_id(intercom_client)

            # Check existing artifacts to avoid re-processing unchanged conversations
            repo = ArtifactRepository(db_pool)
            existing_artifacts = await repo.get_artifacts_by_entity_ids(
                IntercomConversationArtifact, conversation_ids
            )
            existing_by_id = {artifact.entity_id: artifact for artifact in existing_artifacts}

            successful_count = 0
            failed_count = 0
            skipped_count = 0

            # Helper function to normalize timestamp for comparison
            def _normalize_timestamp_for_comparison(value: Any | None) -> datetime | None:
                """Normalize timestamp to datetime for comparison."""
                if value is None:
                    return None
                if isinstance(value, int):
                    return datetime.fromtimestamp(value, tz=UTC)
                if isinstance(value, str):
                    try:
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except ValueError:
                        try:
                            epoch = int(value)
                            return datetime.fromtimestamp(epoch, tz=UTC)
                        except ValueError:
                            pass
                return None

            # Process each conversation from the list
            for conv_list_item in conversation_list_data:
                conversation_id_raw = conv_list_item.get("id")
                if not conversation_id_raw:
                    continue
                conversation_id = str(conversation_id_raw)

                try:
                    # Get updated_at from the list response
                    list_updated_at_raw = conv_list_item.get("updated_at")
                    list_updated_at = _normalize_timestamp_for_comparison(list_updated_at_raw)

                    # Check if conversation already exists and hasn't been updated
                    existing_artifact = existing_by_id.get(conversation_id)
                    if existing_artifact and list_updated_at:
                        existing_updated_at = existing_artifact.source_updated_at

                        # Skip if conversation hasn't been updated
                        if list_updated_at <= existing_updated_at:
                            skipped_count += 1
                            logger.debug(
                                f"Skipping conversation {conversation_id} - no updates since last sync",
                                extra={
                                    "tenant_id": tenant_id,
                                    "conversation_id": conversation_id,
                                    "existing_updated_at": existing_updated_at.isoformat(),
                                    "list_updated_at": list_updated_at.isoformat()
                                    if list_updated_at
                                    else None,
                                },
                            )
                            continue

                    # Fetch full conversation details only if needed
                    logger.debug(f"Fetching conversation {conversation_id} from Intercom API")
                    response = intercom_client.get_conversation(conversation_id)

                    if not response:
                        logger.warning(
                            f"Could not fetch conversation {conversation_id} from Intercom API - empty response"
                        )
                        continue

                    # Intercom API might wrap the conversation in a 'conversation' key
                    # or return it directly - handle both cases
                    conversation_data = response
                    if isinstance(response, dict) and "conversation" in response:
                        conversation_data = response["conversation"]
                    elif isinstance(response, dict) and "id" not in response:
                        # If response doesn't have an 'id' field, it might be wrapped
                        logger.warning(
                            f"Unexpected response structure for conversation {conversation_id}: {list(response.keys())}"
                        )
                        continue

                    logger.debug(
                        f"Processing conversation {conversation_id} - has id: {'id' in conversation_data if isinstance(conversation_data, dict) else False}"
                    )

                    # Process conversation into artifact
                    artifact = await self.process_conversation(
                        job_id, conversation_data, tenant_id, db_pool, workspace_id
                    )
                    artifacts_to_store.append(artifact)
                    conversation_ids_for_indexing.append(artifact.entity_id)
                    successful_count += 1

                    logger.debug(
                        f"Successfully created artifact for conversation {conversation_id}"
                    )

                except Exception as e:
                    failed_count += 1
                    logger.error(
                        f"Failed to process conversation {conversation_id}: {e}",
                        exc_info=True,  # Include full stack trace
                        extra={"conversation_id": conversation_id, "tenant_id": tenant_id},
                    )
                    # Continue processing other conversations even if one fails
                    continue

            logger.info(
                f"Processed {len(conversation_list_data)} conversations: {successful_count} successful, {skipped_count} skipped, {failed_count} failed",
                extra={
                    "tenant_id": tenant_id,
                    "successful": successful_count,
                    "skipped": skipped_count,
                    "failed": failed_count,
                    "total": len(conversation_list_data),
                },
            )

            # Batch store artifacts to database
            if artifacts_to_store:
                await self.store_artifacts_batch(db_pool, artifacts_to_store)
                logger.info(
                    f"Stored {len(artifacts_to_store)} Intercom conversation artifacts",
                    extra={
                        "tenant_id": tenant_id,
                        "artifact_count": len(artifacts_to_store),
                        "backfill_id": backfill_id,
                    },
                )
            else:
                logger.warning(
                    f"No artifacts to store for batch of {len(conversation_ids)} conversations",
                    extra={
                        "tenant_id": tenant_id,
                        "conversation_ids": conversation_ids,
                        "backfill_id": backfill_id,
                    },
                )

            # Trigger indexing for processed conversations
            if conversation_ids_for_indexing:
                # Split into batches for indexing
                for i in range(0, len(conversation_ids_for_indexing), DEFAULT_INDEX_BATCH_SIZE):
                    batch = conversation_ids_for_indexing[i : i + DEFAULT_INDEX_BATCH_SIZE]
                    await trigger_indexing(
                        entity_ids=batch,
                        source=DocumentSource.INTERCOM,
                        tenant_id=tenant_id,
                        backfill_id=backfill_id,
                        suppress_notification=suppress_notification,
                    )

            logger.info(
                f"Triggered indexing for {len(conversation_ids_for_indexing)} Intercom conversations"
            )

        except Exception as e:
            logger.error(f"Failed to process conversations batch: {e}")
            raise
