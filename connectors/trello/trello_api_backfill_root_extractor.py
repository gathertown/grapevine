"""Trello API backfill root extractor for orchestrating workspace, board collection and batching."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import asyncpg

from connectors.base import TriggerIndexingCallback, get_trello_workspace_entity_id
from connectors.trello.trello_artifacts import (
    TrelloWebhooksConfig,
    TrelloWorkspaceArtifact,
    TrelloWorkspaceArtifactContent,
    TrelloWorkspaceArtifactMetadata,
)
from connectors.trello.trello_base import TrelloExtractor
from connectors.trello.trello_models import (
    TrelloApiBackfillConfig,
    TrelloApiBackfillRootConfig,
    TrelloBoardBatch,
)
from connectors.trello.trello_webhook_handler import (
    get_trello_webhook_callback_url,
    store_webhook_config,
)
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = logging.getLogger(__name__)

# Batch size (boards) per child job
BATCH_SIZE = 5

# Trello API rate limits: Start with a burst then rate limit
# Process initial burst quickly, then rate limit remaining batches
BURST_BOARD_COUNT = 10
BURST_BATCH_COUNT = BURST_BOARD_COUNT // BATCH_SIZE

# Conservative rate limiting: 100 boards per hour after burst
BOARDS_PER_HOUR_AFTER_BURST = 100

# Delay between rate-limited batches (after burst)
BATCH_DELAY_SECONDS = BATCH_SIZE * 3600 // BOARDS_PER_HOUR_AFTER_BURST


class TrelloApiBackfillRootExtractor(TrelloExtractor[TrelloApiBackfillRootConfig]):
    """Root extractor for Trello API backfill.

    This extractor:
    1. Fetches all boards for the tenant
    2. Creates board batches
    3. Sends child jobs to process each batch
    """

    source_name = "trello_api_backfill_root"

    async def process_job(
        self,
        job_id: str,
        config: TrelloApiBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process root backfill job - collect boards and create child jobs.

        Args:
            job_id: The job ID
            config: Root backfill configuration
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing (unused in root job)

        Raises:
            Exception: If job processing fails
        """
        try:
            backfill_id = secrets.token_hex(8)
            logger.info(
                f"Processing Trello backfill_id {backfill_id} for tenant {config.tenant_id}"
            )

            # First, collect and store workspaces/organizations
            await self.collect_and_store_workspaces(config.tenant_id, db_pool)

            # Register member-level webhook first (covers all boards across all orgs)
            await self.register_member_webhook(config.tenant_id)

            # Then collect all boards
            all_boards = await self.collect_all_boards(config.tenant_id)

            if not all_boards:
                logger.warning(f"No Trello boards found for tenant {config.tenant_id}")
                return

            # Split boards into batches
            batches = [
                all_boards[i : i + BATCH_SIZE] for i in range(0, len(all_boards), BATCH_SIZE)
            ]

            logger.info(
                f"Splitting {len(all_boards)} Trello boards into {len(batches)} batches "
                f"for tenant {config.tenant_id} with backfill_id {backfill_id}"
            )

            # Send child jobs with burst and rate limiting strategy
            burst_batch_count = min(len(batches), BURST_BATCH_COUNT)

            # Calculate base start time (now) for rate-limited batches
            base_start_time = datetime.now(UTC)

            # Log the delay schedule
            rate_limited_batches = max(0, len(batches) - burst_batch_count)

            if rate_limited_batches > 0:
                total_delay_minutes = rate_limited_batches * BATCH_DELAY_SECONDS / 60
                logger.info(
                    f"Burst processing {burst_batch_count} batches, "
                    f"then rate-limiting {rate_limited_batches} batches with {BATCH_DELAY_SECONDS}s delays "
                    f"(rate-limited duration: {total_delay_minutes:.1f} minutes)"
                )
            else:
                logger.info(
                    f"Burst processing all {burst_batch_count} batches ({len(all_boards)} boards)"
                )

            # Track total number of ingest jobs (child batches) for this backfill
            if batches:
                await increment_backfill_total_ingest_jobs(
                    backfill_id, config.tenant_id, len(batches)
                )

            # Send all jobs sequentially to guarantee increasing start_timestamp order
            for batch_index, batch in enumerate(batches):
                if batch:
                    await self.send_child_job(
                        config.tenant_id,
                        batch,
                        batch_index,
                        base_start_time,
                        burst_batch_count,
                        backfill_id,
                        config.suppress_notification,
                    )

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            raise

    async def collect_and_store_workspaces(self, tenant_id: str, db_pool: asyncpg.Pool) -> None:
        """Collect and store all Trello workspaces/organizations for a tenant.

        Args:
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Raises:
            Exception: If workspace collection fails
        """
        try:
            trello_client = await self.get_trello_client(tenant_id)

            # Get all organizations for the authenticated user
            organizations = trello_client.get_organizations()

            if not organizations:
                logger.info("No Trello workspaces/organizations found.")
                return

            # Create workspace artifacts
            workspace_artifacts = []
            for org in organizations:
                org_id = org.get("id", "")
                org_name = org.get("name", "Unknown Workspace")

                workspace_content = TrelloWorkspaceArtifactContent(workspace_data=org)

                workspace_metadata = TrelloWorkspaceArtifactMetadata(
                    workspace_id=org_id,
                    workspace_name=org_name,
                    display_name=org.get("displayName"),
                    desc=org.get("desc"),
                    desc_data=org.get("descData"),
                    website=org.get("website"),
                    url=org.get("url"),
                    logo_url=org.get("logoUrl"),
                    premium_features=org.get("premiumFeatures", []),
                )

                workspace_artifact = TrelloWorkspaceArtifact(
                    entity_id=get_trello_workspace_entity_id(workspace_id=org_id),
                    ingest_job_id=uuid4(),
                    content=workspace_content,
                    metadata=workspace_metadata,
                    source_updated_at=datetime.now(UTC),
                )
                workspace_artifacts.append(workspace_artifact)

            # Store workspace artifacts
            if workspace_artifacts:
                await self.store_artifacts_batch(db_pool, workspace_artifacts)
                logger.info(
                    f"Stored {len(workspace_artifacts)} Trello workspace artifacts: "
                    f"{[w.metadata.workspace_name for w in workspace_artifacts]}"
                )

        except Exception as e:
            logger.error(f"Failed to collect and store Trello workspaces: {e}")
            raise

    async def collect_all_boards(self, tenant_id: str) -> list[TrelloBoardBatch]:
        """Collect all Trello boards for a tenant.

        Args:
            tenant_id: The tenant ID

        Returns:
            List of TrelloBoardBatch objects

        Raises:
            Exception: If board collection fails
        """
        try:
            trello_client = await self.get_trello_client(tenant_id)

            # Get all open boards for the authenticated user
            boards = trello_client.get_boards()

            if not boards:
                logger.warning("No Trello boards found. No cards will be indexed.")
                return []

            # Convert to board batches
            board_batches = []
            for board in boards:
                board_batch = TrelloBoardBatch(
                    board_id=board.id,
                    board_name=board.name,
                )
                board_batches.append(board_batch)

            logger.info(
                f"Collected {len(board_batches)} Trello boards for tenant {tenant_id}: "
                f"{[b.board_name for b in board_batches]}"
            )
            return board_batches

        except Exception as e:
            logger.error(f"Failed to collect Trello boards: {e}")
            raise

    async def register_member_webhook(self, tenant_id: str) -> None:
        """Register a single member-level webhook for complete coverage.

        Member-level webhooks (created with admin token) receive ALL events:
        - ALL card events across ALL boards in ALL organizations
        - createBoard events for new board discovery
        - Board lifecycle events (close/delete)
        - Admin lifecycle events (demotion/removal)
        - Events from private boards (when token has admin privileges)

        This is the recommended approach per Trello documentation:
        "Webhooks on boards created by an admin's token will receive actions
        regardless of whether the admin is a member of the board or not."

        Args:
            tenant_id: The tenant ID

        Note:
            Webhook registration failures are logged but don't fail the backfill.
            If token lacks admin privileges in some orgs, a warning is logged.
        """
        try:
            trello_client = await self.get_trello_client(tenant_id)

            member_data = trello_client.get_member("me")
            member_id = member_data.get("id")
            member_username = member_data.get("username", "unknown")

            if not member_id:
                logger.error("Failed to get authenticated member ID. Cannot register webhook.")
                return

            callback_url = get_trello_webhook_callback_url(tenant_id)

            logger.info(
                f"Registering member-level webhook for member '{member_username}' ({member_id}) "
                f"with callback: {callback_url}"
            )

            webhook_data = trello_client.create_webhook(
                callback_url=callback_url,
                id_model=member_id,
                description=f"Grapevine webhook for {member_username}",
            )

            webhook_id = webhook_data.get("id")
            if not webhook_id:
                logger.error("Webhook created but no ID returned")
                return

            webhook_config = TrelloWebhooksConfig(
                webhook_id=webhook_id,
                member_id=member_id,
                member_username=member_username,
                created_at=datetime.now(UTC).isoformat(),
            )

            await store_webhook_config(tenant_id, webhook_config)

            logger.info(
                f"Successfully registered member webhook {webhook_id} for '{member_username}' ({member_id})"
            )

        except Exception as e:
            logger.error(f"Error during webhook registration for tenant {tenant_id}: {e}")

    async def send_child_job(
        self,
        tenant_id: str,
        board_batches: list[TrelloBoardBatch],
        batch_index: int,
        base_start_time: datetime,
        burst_batch_count: int,
        backfill_id: str,
        suppress_notification: bool,
    ) -> None:
        """Send a child job to process a batch of boards with rate limiting.

        Args:
            tenant_id: The tenant ID
            board_batches: List of board batches to process
            batch_index: Index of this batch (for logging and delay calculation)
            base_start_time: Base time for calculating delays for rate-limited batches
            burst_batch_count: Number of batches to process in burst mode
            backfill_id: Unique ID for tracking this backfill
        """
        # Determine if this batch should be burst processed or rate-limited
        if batch_index < burst_batch_count:
            # Burst processing - no delay
            start_timestamp = None
            description = f"burst child job batch {batch_index}"
        else:
            # Rate-limited processing - calculate delay
            rate_limited_index = batch_index - burst_batch_count
            delay_seconds = (rate_limited_index + 1) * BATCH_DELAY_SECONDS

            start_timestamp = base_start_time + timedelta(seconds=delay_seconds)
            description = f"rate-limited child job batch {batch_index}"

        # Create the child job config with backfill_id
        child_config = TrelloApiBackfillConfig(
            tenant_id=tenant_id,
            board_batches=board_batches,
            start_timestamp=start_timestamp,
            backfill_id=backfill_id,
            suppress_notification=suppress_notification,
        )

        # Use the shared base method to send the message
        await self.send_backfill_child_job_message(
            config=child_config,
            _description=description,
        )
