import logging
import math
from datetime import UTC, datetime

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.linear.linear_base import LinearExtractor
from connectors.linear.linear_models import LinearApiBackfillConfig
from src.clients.sqs import cap_sqs_visibility_timeout
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = logging.getLogger(__name__)


class LinearApiBackfillExtractor(LinearExtractor[LinearApiBackfillConfig]):
    source_name = "linear_api_backfill"

    async def process_job(
        self,
        job_id: str,
        config: LinearApiBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # Check if we should start processing yet (for rate limiting)
        if config.start_timestamp:
            current_time = datetime.now(UTC)
            if current_time < config.start_timestamp:
                # Not time to start yet - extend visibility timeout until start_timestamp
                # Add a 3s buffer to ensure we don't process too early
                delay_seconds = cap_sqs_visibility_timeout(
                    3 + int((config.start_timestamp - current_time).total_seconds())
                )

                logger.info(
                    f"Delaying batch processing until {config.start_timestamp.isoformat()} "
                    f"(current time: {current_time.isoformat()}, delay: {delay_seconds}s)"
                )

                raise ExtendVisibilityException(
                    visibility_timeout_seconds=delay_seconds,
                    message=f"Delaying processing until {config.start_timestamp.isoformat()}",
                )

        try:
            # Process the batch of Linear issues
            await self.process_linear_issues_batch(
                db_pool,
                job_id,
                trigger_indexing,
                config.tenant_id,
                config.issue_ids,
                config.backfill_id,
                config.suppress_notification,
            )
        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}")
            raise

    async def process_linear_issues_batch(
        self,
        db_pool: asyncpg.Pool,
        job_id: str,
        trigger_indexing: TriggerIndexingCallback,
        tenant_id: str,
        issue_ids: list[str],
        backfill_id: str | None = None,
        suppress_notification: bool = False,
    ) -> None:
        """Process a batch of Linear issues by their IDs."""
        try:
            artifacts_to_store = []
            issue_ids_for_indexing: list[str] = []

            logger.info(f"Processing batch of {len(issue_ids)} Linear issues")

            # Get Linear client
            linear_client = await self.get_linear_client(tenant_id, db_pool)

            # Fetch all issues data in a single API call
            logger.info(f"Fetching data for {len(issue_ids)} issues in batch")
            issues_data = linear_client.get_issues_by_ids(issue_ids)

            if not issues_data:
                logger.error("Could not fetch any issue data from Linear API")
                return

            logger.info(f"Successfully fetched {len(issues_data)} issues from Linear API")

            # Process each issue that was successfully fetched
            for issue_id in issue_ids:
                logger.debug(f"Processing issue: {issue_id}")

                try:
                    # Get the issue data from our batch fetch
                    issue_data = issues_data.get(issue_id)
                    if not issue_data:
                        logger.warning(f"Issue {issue_id} was not returned from Linear API")
                        continue

                    # Process the issue using the base class method
                    artifact = await self._process_issue(job_id, issue_data, tenant_id, db_pool)
                    # Collect artifacts for batch storage and issue IDs for indexing at the end
                    artifacts_to_store.append(artifact)
                    issue_ids_for_indexing.append(issue_id)

                    # Log progress
                    if len(artifacts_to_store) % 10 == 0:
                        logger.info(
                            f"Processed {len(artifacts_to_store)} of {len(issue_ids)} issues"
                        )

                except Exception as e:
                    logger.error(f"Error processing issue {issue_id}: {e}")
                    raise

            # Store all artifacts in batch first
            if artifacts_to_store:
                logger.info(f"Storing {len(artifacts_to_store)} artifacts in batch")
                await self.store_artifacts_batch(db_pool, artifacts_to_store)

            # Only trigger indexing after all artifacts are stored, since indexing needs to read the artifacts
            if issue_ids_for_indexing:
                logger.info(f"Triggering indexing for {len(issue_ids_for_indexing)} issues")
                # Calculate total number of index batches and track them upfront
                total_index_batches = math.ceil(
                    len(issue_ids_for_indexing) / DEFAULT_INDEX_BATCH_SIZE
                )
                if backfill_id and total_index_batches > 0:
                    await increment_backfill_total_index_jobs(
                        backfill_id, tenant_id, total_index_batches
                    )

                for i in range(0, len(issue_ids_for_indexing), DEFAULT_INDEX_BATCH_SIZE):
                    batch = issue_ids_for_indexing[i : i + DEFAULT_INDEX_BATCH_SIZE]
                    await trigger_indexing(
                        batch,
                        DocumentSource.LINEAR,
                        tenant_id,
                        backfill_id,
                        suppress_notification,
                    )

            logger.info(
                f"Completed processing batch: {len(artifacts_to_store)} issues processed successfully"
            )

            # Track completion and send notification if backfill is done
            if backfill_id:
                await increment_backfill_done_ingest_jobs(backfill_id, tenant_id, 1)

        except Exception as e:
            logger.error(f"Failed to process linear_issues batch: {e}")
            raise
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if backfill_id:
                await increment_backfill_attempted_ingest_jobs(backfill_id, tenant_id, 1)
