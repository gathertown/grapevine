"""Pylon full backfill extractor for ingesting issues."""

import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.base.models import BackfillIngestConfig
from connectors.pylon.client.pylon_client import PylonClient
from connectors.pylon.client.pylon_client_factory import get_pylon_client_for_tenant
from connectors.pylon.client.pylon_models import PylonIssue
from connectors.pylon.extractors.pylon_artifacts import (
    PylonAccountArtifact,
    PylonContactArtifact,
    PylonIssueArtifact,
    PylonTeamArtifact,
    PylonUserArtifact,
)
from connectors.pylon.pylon_sync_service import PylonSyncService
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.repositories.artifact_repository import ArtifactRepository
from src.utils.logging import LogContext, get_logger

logger = get_logger(__name__)


class PylonFullBackfillConfig(BackfillIngestConfig, frozen=True):
    """Configuration for Pylon full backfill job."""

    source: Literal["pylon_full_backfill"] = "pylon_full_backfill"

    # How long the backfill job should run for, SQS visibility timeout is 15 mins
    duration_seconds: int = 60 * 13


class PylonFullBackfillExtractor(BaseExtractor[PylonFullBackfillConfig]):
    """
    Extractor to make progress on a full Pylon issue backfill.
    Makes progress and then enqueues the next job if not complete.
    """

    source_name = "pylon_full_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient) -> None:
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def process_job(
        self,
        job_id: str,
        config: PylonFullBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        start_time = time.perf_counter()
        backfill_id = config.backfill_id or secrets.token_hex(8)
        logger.info(
            "Started Pylon full/progress backfill job",
            backfill_id=backfill_id,
            estimated_duration=config.duration_seconds,
        )

        sync_service = PylonSyncService(db_pool)

        is_backfill_complete = await sync_service.get_full_issues_backfill_complete()
        if is_backfill_complete:
            logger.info("Pylon full/progress backfill job already complete, skipping")
            return

        pylon_client = await get_pylon_client_for_tenant(config.tenant_id, self.ssm_client)

        backfiller = PylonFullBackfiller(
            artifact_repo=ArtifactRepository(db_pool),
            config=config,
            job_id=UUID(job_id),
            process_until=datetime.now(UTC) + timedelta(seconds=config.duration_seconds),
            trigger_indexing=trigger_indexing,
            service=sync_service,
            api=pylon_client,
        )

        with LogContext(backfill_id=backfill_id):
            async with pylon_client:
                is_complete = await backfiller.backfill()

                duration = time.perf_counter() - start_time

                if is_complete:
                    logger.info(
                        "Pylon full/progress backfill complete, no job enqueued",
                        backfill_id=backfill_id,
                        duration=duration,
                    )
                else:
                    logger.info(
                        "Pylon full/progress backfill incomplete, job enqueued",
                        backfill_id=backfill_id,
                        duration=duration,
                    )

                    # Trigger the same job again, adding backfill_id in case this is the first run
                    await self.sqs_client.send_backfill_ingest_message(
                        backfill_config=PylonFullBackfillConfig(
                            duration_seconds=config.duration_seconds,
                            backfill_id=backfill_id,
                            tenant_id=config.tenant_id,
                            suppress_notification=config.suppress_notification,
                        )
                    )


class PylonFullBackfiller:
    """Backfiller that iterates through all Pylon issues."""

    def __init__(
        self,
        artifact_repo: ArtifactRepository,
        api: PylonClient,
        service: PylonSyncService,
        trigger_indexing: TriggerIndexingCallback,
        config: PylonFullBackfillConfig,
        job_id: UUID,
        process_until: datetime,
    ) -> None:
        self.artifact_repo = artifact_repo
        self.api = api
        self.service = service
        self.trigger_indexing = trigger_indexing
        self.config = config
        self.job_id = job_id
        self.process_until = process_until

    async def backfill(self) -> bool:
        """
        Backfill Pylon issues.

        Returns True if complete, False if more work is needed.
        """
        sync_complete = await self.service.get_full_issues_backfill_complete()
        if sync_complete:
            logger.info("Skipping Pylon issue backfill, already complete")
            return True

        # First, sync reference data (users, accounts, teams, contacts)
        # This ensures we have name information when transforming issues
        await self._sync_reference_data()

        # Pylon API requires time windows of <= 30 days
        # We'll process in 30-day windows, going backwards from now
        synced_after = await self.service.get_full_issues_synced_after()

        # Start from 30 days ago if this is the first run
        end_time = synced_after if synced_after else datetime.now(UTC)
        # Go back 30 days for each window
        start_time = end_time - timedelta(days=30)

        # Set a floor - don't go back more than 2 years
        floor_time = datetime.now(UTC) - timedelta(days=365 * 2)

        issues_processed_count = 0

        # Process windows until end_time passes the floor
        # (we check end_time, not start_time, to ensure we process the final partial window)
        while end_time > floor_time:
            # Clamp start_time to floor_time for the final partial window
            start_time = max(start_time, floor_time)
            # Load saved cursor for resuming pagination within this window
            cursor = await self.service.get_full_issues_cursor()

            logger.info(
                "Processing Pylon issues window",
                start_time=start_time.isoformat(),
                end_time=end_time.isoformat(),
                resuming_from_cursor=cursor is not None,
            )

            # Fetch all issues in this time window with pagination
            while True:
                response = await self.api.list_issues(
                    start_time=start_time,
                    end_time=end_time,
                    cursor=cursor,
                )

                if response.data:
                    await self._process_issues_batch(response.data)
                    issues_processed_count += len(response.data)

                # Check if window is complete (no more pages) BEFORE checking time limit
                # This prevents reprocessing a completed window on timeout
                if not response.cursor:
                    break

                # Check if we're out of time after processing each page
                if datetime.now(UTC) >= self.process_until:
                    # Save cursor to resume from this page on next run
                    await self.service.set_full_issues_cursor(response.cursor)
                    logger.info(
                        "Pylon backfill time limit reached, enqueuing another job",
                        issues_processed_count=issues_processed_count,
                    )
                    # Save window end_time so we resume this window on next run
                    await self.service.set_full_issues_synced_after(end_time)
                    return False

                cursor = response.cursor

            # Window complete - clear cursor for next window
            await self.service.set_full_issues_cursor(None)

            # Move to the next window
            # Save end_time for next window (start_time - 1ms) to avoid reprocessing boundary issues
            end_time = start_time - timedelta(milliseconds=1)
            await self.service.set_full_issues_synced_after(end_time)
            start_time = end_time - timedelta(days=30)

            # Check if we're out of time
            if datetime.now(UTC) >= self.process_until:
                logger.info(
                    "Pylon backfill time limit reached at window boundary",
                    issues_processed_count=issues_processed_count,
                )
                return False

        # All windows processed
        await self.service.set_full_issues_backfill_complete(True)
        logger.info(
            "Pylon full backfill complete",
            total_issues_processed=issues_processed_count,
        )
        return True

    async def _process_issues_batch(self, issues: list["PylonIssue"]) -> None:
        """Process a batch of issues."""
        artifacts = [PylonIssueArtifact.from_api_issue(issue, self.job_id) for issue in issues]

        await self.artifact_repo.upsert_artifacts_batch(artifacts)

        entity_ids = [a.entity_id for a in artifacts]
        await self.trigger_indexing(
            entity_ids,
            source=DocumentSource.PYLON_ISSUE,
            tenant_id=self.config.tenant_id,
            backfill_id=self.config.backfill_id,
            suppress_notification=self.config.suppress_notification,
        )

        logger.info(
            "Backfilled Pylon issues batch",
            count=len(issues),
        )

    async def _sync_reference_data(self) -> None:
        """
        Sync reference data (users, accounts, teams, contacts).

        This ensures we have names for users, accounts, and teams
        when transforming issues into documents.
        Reference data is synced once per backfill run.
        """
        # Check if we've already synced reference data recently (within the last day)
        last_synced = await self.service.get_reference_data_synced_at()
        if last_synced:
            time_since_sync = datetime.now(UTC) - last_synced
            if time_since_sync.total_seconds() < 86400:  # 24 hours
                logger.info(
                    "Skipping reference data sync, already synced recently",
                    last_synced=last_synced.isoformat(),
                )
                return

        logger.info("Syncing Pylon reference data (users, accounts, teams, contacts)")

        # Sync users
        users_count = 0
        user_artifacts = []
        async for user in self.api.iterate_users():
            user_artifacts.append(PylonUserArtifact.from_api_user(user, self.job_id))
            users_count += 1

            if len(user_artifacts) >= 100:
                await self.artifact_repo.upsert_artifacts_batch(user_artifacts)
                user_artifacts = []

        if user_artifacts:
            await self.artifact_repo.upsert_artifacts_batch(user_artifacts)

        logger.info("Synced Pylon users", count=users_count)

        # Sync teams
        teams_count = 0
        team_artifacts = []
        async for team in self.api.iterate_teams():
            team_artifacts.append(PylonTeamArtifact.from_api_team(team, self.job_id))
            teams_count += 1

            if len(team_artifacts) >= 100:
                await self.artifact_repo.upsert_artifacts_batch(team_artifacts)
                team_artifacts = []

        if team_artifacts:
            await self.artifact_repo.upsert_artifacts_batch(team_artifacts)

        logger.info("Synced Pylon teams", count=teams_count)

        # Sync accounts
        accounts_count = 0
        account_artifacts = []
        async for account in self.api.iterate_accounts():
            account_artifacts.append(PylonAccountArtifact.from_api_account(account, self.job_id))
            accounts_count += 1

            if len(account_artifacts) >= 100:
                await self.artifact_repo.upsert_artifacts_batch(account_artifacts)
                account_artifacts = []

        if account_artifacts:
            await self.artifact_repo.upsert_artifacts_batch(account_artifacts)

        logger.info("Synced Pylon accounts", count=accounts_count)

        # Sync contacts
        contacts_count = 0
        contact_artifacts = []
        async for contact in self.api.iterate_contacts():
            contact_artifacts.append(PylonContactArtifact.from_api_contact(contact, self.job_id))
            contacts_count += 1

            if len(contact_artifacts) >= 100:
                await self.artifact_repo.upsert_artifacts_batch(contact_artifacts)
                contact_artifacts = []

        if contact_artifacts:
            await self.artifact_repo.upsert_artifacts_batch(contact_artifacts)

        logger.info("Synced Pylon contacts", count=contacts_count)

        # Mark reference data as synced
        await self.service.set_reference_data_synced_at(datetime.now(UTC))

        logger.info(
            "Pylon reference data sync complete",
            users=users_count,
            teams=teams_count,
            accounts=accounts_count,
            contacts=contacts_count,
        )
