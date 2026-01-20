"""
Index job worker entrypoint.

Processes index jobs from SQS queue.
"""

# Initialize New Relic agent before any other imports
from pathlib import Path

import newrelic.agent

from src.utils.config import get_grapevine_environment
from src.utils.tenant_deletion import is_tenant_deleted

# Get the directory containing this file and environment
current_dir = Path(__file__).parent
config_path = current_dir / "newrelic_index_worker.toml"
grapevine_env = get_grapevine_environment()
# Initialize New Relic with the index worker-specific TOML config and environment
newrelic.agent.initialize(str(config_path), environment=grapevine_env)

import asyncio
import json
import time
from typing import Any

from connectors.base.external_source import (
    ExternalSource,
    get_external_source_for_document_source,
)
from src.clients.sqs import SQSClient
from src.ingest.services.index_job_handler import IndexJobHandler
from src.jobs.base_worker import BaseJobWorker
from src.jobs.lanes import get_slackbot_lane
from src.jobs.models import BackfillCompleteNotificationMessage, DeleteJobMessage, IndexJobMessage
from src.jobs.sqs_job_processor import SQSJobProcessor, SQSMessageMetadata
from src.utils.config import get_config_value
from src.utils.logging import LogContext, get_logger
from src.utils.tenant_config import (
    check_and_mark_backfill_complete,
    increment_backfill_done_index_jobs,
)

logger = get_logger(__name__)


def log_job_complete(entity_count: int, duration_seconds: float | None = None) -> None:
    """Log successful completion of an index job with consistent format.

    Args:
        entity_count: Number of entities processed
        duration_seconds: Optional processing duration in seconds
    """
    log_data: dict[str, int | float] = {
        "entity_count": entity_count,
    }
    if duration_seconds is not None:
        log_data["duration_seconds"] = round(duration_seconds, 3)

    logger.info("Successfully processed index job", **log_data)


class IndexJobWorker(BaseJobWorker):
    """Worker for processing index jobs from SQS."""

    def __init__(self, http_port: int | None = None):
        super().__init__(http_port)
        self.index_handler = IndexJobHandler()
        self.sqs_client = SQSClient()

    def _get_default_http_port(self) -> int:
        """Get the default HTTP server port for index worker."""
        return int(get_config_value("INDEX_HTTP_PORT", "8081"))

    def _register_custom_routes(self, app) -> None:
        """Register index worker specific routes."""
        pass

    async def send_backfill_complete_notification(
        self, tenant_id: str, source: ExternalSource, backfill_id: str
    ) -> None:
        """Send backfill complete notification to Slack queue."""
        try:
            # Get the Slack jobs queue ARN from environment
            slack_queue_arn = (
                get_config_value("SLACK_JOBS_QUEUE_ARN") or "corporate-context-slack-jobs"
            )

            message = BackfillCompleteNotificationMessage(
                tenant_id=tenant_id, source=source, backfill_id=backfill_id
            )

            success = await self.sqs_client.send_message(
                queue_arn=slack_queue_arn,
                message_body=message.model_dump_json(),
                message_group_id=get_slackbot_lane(message),
            )

            if success:
                logger.info(
                    f"Sent backfill complete notification for backfill_id {backfill_id} to tenant {tenant_id}"
                )
            else:
                logger.error(
                    f"Failed to send backfill complete notification for backfill_id {backfill_id}"
                )

        except Exception as e:
            logger.error(f"Error sending backfill complete notification: {e}")
            # Don't raise - we don't want to fail the index job if notification fails

    async def _run_post_backfill_cleanup(
        self, tenant_id: str, backfill_id: str, source: ExternalSource
    ) -> None:
        """Run post-backfill cleanup tasks like pruning stale entities.

        Args:
            tenant_id: The tenant ID
            backfill_id: The backfill ID that just completed
            source: The external source that was backfilled
        """
        try:
            # Only run pruning for Gong source
            if source == "gong":
                logger.info(
                    f"Running Gong pruning for backfill {backfill_id}",
                    tenant_id=tenant_id,
                    backfill_id=backfill_id,
                )

                from connectors.gong.gong_pruner import gong_pruner

                async with self.tenant_db_manager.acquire_pool(tenant_id) as pool:
                    deletion_stats = await gong_pruner.prune_unmarked_entities(
                        tenant_id=tenant_id,
                        backfill_id=backfill_id,
                        db_pool=pool,
                    )

                logger.info(
                    f"Gong pruning completed for backfill {backfill_id}",
                    tenant_id=tenant_id,
                    deletion_stats=deletion_stats,
                )

        except Exception as e:
            logger.error(
                f"Error during post-backfill cleanup for {backfill_id}: {e}",
                tenant_id=tenant_id,
                source=source,
            )
            # Don't raise - we don't want to fail the index job if cleanup fails

    # See context: AIVP-584
    async def _track_backfill_completion(self, index_message: IndexJobMessage) -> None:
        """
        Track backfill completion and send notification if ALL jobs (ingest+index) are done for this backfill_id.
        """
        if not index_message.backfill_id:
            return

        backfill_id = index_message.backfill_id
        tenant_id = index_message.tenant_id

        try:
            # Atomically increment completed count and get new value
            await increment_backfill_done_index_jobs(backfill_id, tenant_id, 1)

            # Check if backfill is complete and send notification if needed
            should_send_notification = await check_and_mark_backfill_complete(
                backfill_id, tenant_id
            )

            if should_send_notification:
                # Determine source from index_message.source
                external_source = get_external_source_for_document_source(index_message.source)

                # Check if we should suppress the notification
                if index_message.suppress_notification:
                    logger.info(
                        f"Backfill {backfill_id} is complete, but suppressing notification as requested"
                    )
                    # Still run pruning even if notification is suppressed
                    await self._run_post_backfill_cleanup(tenant_id, backfill_id, external_source)
                    return

                logger.info(
                    f"Backfill {backfill_id} is complete! Sending notification for {external_source}"
                )

                # Send completion notification
                await self.send_backfill_complete_notification(
                    tenant_id=tenant_id, source=external_source, backfill_id=backfill_id
                )

                # Run post-backfill cleanup (e.g., pruning stale entities)
                await self._run_post_backfill_cleanup(tenant_id, backfill_id, external_source)

        except Exception as e:
            logger.error(f"Error tracking backfill completion for {backfill_id}: {e}")
            # Don't raise - we don't want to fail the index job if tracking fails

    async def process_index_message(
        self,
        index_message: IndexJobMessage,
        sqs_metadata: SQSMessageMetadata | None = None,
    ) -> None:
        """Process an index job message.

        Args:
            index_message: The index job message from SQS
            sqs_metadata: Optional SQS message metadata for job completion tracking
        """
        start_time = time.perf_counter()

        logger.info("Processing index job", entity_count=len(index_message.entity_ids))

        async with self.tenant_db_manager.acquire_pool(
            index_message.tenant_id, readonly=True
        ) as readonly_tenant_db_pool:
            await self.index_handler.handle_index_job(
                index_message, readonly_tenant_db_pool, sqs_metadata
            )

            # Track backfill completion if backfill_id exists
            if index_message.backfill_id:
                await self._track_backfill_completion(index_message)

            duration = time.perf_counter() - start_time
            log_job_complete(len(index_message.entity_ids), duration)

    async def process_delete_message(
        self,
        delete_message: DeleteJobMessage,
    ) -> None:
        """Process a delete job message.

        Args:
            delete_message: The delete job message from SQS
        """
        from src.clients.tenant_opensearch import tenant_opensearch_manager
        from src.ingest.services.deletion_service import delete_documents_and_chunks

        start_time = time.perf_counter()
        tenant_id = delete_message.tenant_id
        document_ids = delete_message.document_ids

        logger.info("Processing delete job", document_count=len(document_ids))

        async with (
            self.tenant_db_manager.acquire_pool(tenant_id) as pool,
            tenant_opensearch_manager.acquire_client(tenant_id) as (
                opensearch_client,
                _index_alias,
            ),
        ):
            deleted_count = await delete_documents_and_chunks(
                document_ids=document_ids,
                tenant_id=tenant_id,
                opensearch_client=opensearch_client,
                pool=pool,
            )

            duration = time.perf_counter() - start_time
            logger.info(
                f"Successfully deleted {deleted_count} documents",
                deleted_count=deleted_count,
                duration_seconds=round(duration, 3),
            )


# Global worker instance
worker = IndexJobWorker()


@newrelic.agent.background_task(name="IndexWorker/process_index_job")
async def process_index_job(message_data: dict[str, Any], sqs_metadata: SQSMessageMetadata) -> None:
    """Process an index or delete job message.

    Args:
        message_data: Parsed message data from SQS
        sqs_metadata: SQS message metadata
    """
    # Check message type to determine how to process
    message_type = message_data.get("message_type")

    if message_type == "delete":
        # Handle delete job
        try:
            delete_message = DeleteJobMessage.model_validate(message_data)
        except Exception as e:
            logger.error(f"Failed to parse delete job message: {e}")
            logger.error(f"Raw message data: {json.dumps(message_data, indent=2)}")
            raise

        # Add New Relic attributes
        newrelic.agent.add_custom_attribute("tenant_id", delete_message.tenant_id)
        newrelic.agent.add_custom_attribute("job_type", "delete")
        newrelic.agent.add_custom_attribute(
            "delete.document_count", len(delete_message.document_ids)
        )
        if sqs_metadata["message_id"]:
            newrelic.agent.add_custom_attribute("sqs.message_id", sqs_metadata["message_id"])

        with LogContext(tenant_id=delete_message.tenant_id, job_type="delete"):
            # Check if tenant is deleted before processing
            control_db_pool = await worker.tenant_db_manager.get_control_db()
            if await is_tenant_deleted(control_db_pool, delete_message.tenant_id):
                logger.warning(f"Skipping delete job for deleted tenant {delete_message.tenant_id}")
                return

            logger.info(
                f"Processing delete job for tenant {delete_message.tenant_id} "
                f"with {len(delete_message.document_ids)} documents"
            )

            await worker.process_delete_message(delete_message)
        return

    # Default: Handle index job
    try:
        index_message = IndexJobMessage.model_validate(message_data)
    except Exception as e:
        logger.error(f"Failed to parse index job message: {e}")
        logger.error(f"Raw message data: {json.dumps(message_data, indent=2)}")
        raise

    # Add New Relic attributes
    newrelic.agent.add_custom_attribute("tenant_id", index_message.tenant_id)
    newrelic.agent.add_custom_attribute("index.source", index_message.source.value)
    newrelic.agent.add_custom_attribute("index.entity_count", len(index_message.entity_ids))
    if sqs_metadata["message_id"]:
        newrelic.agent.add_custom_attribute("sqs.message_id", sqs_metadata["message_id"])
    if sqs_metadata["approximate_receive_count"]:
        newrelic.agent.add_custom_attribute(
            "sqs.receive_count", sqs_metadata["approximate_receive_count"]
        )

    with LogContext(tenant_id=index_message.tenant_id, source=index_message.source.value):
        # Check if tenant is deleted before processing
        control_db_pool = await worker.tenant_db_manager.get_control_db()
        if await is_tenant_deleted(control_db_pool, index_message.tenant_id):
            logger.warning(f"Skipping index job for deleted tenant {index_message.tenant_id}")
            return

        logger.info(
            f"Processing index job for tenant {index_message.tenant_id} "
            f"from {index_message.source.value} with {len(index_message.entity_ids)} entities"
        )

        # Process using the global worker instance
        await worker.process_index_message(index_message, sqs_metadata)


async def main() -> None:
    """Main entry point for index job worker."""
    # Get queue ARN from configuration
    queue_arn = get_config_value("INDEX_JOBS_QUEUE_ARN") or "corporate-context-index-jobs"

    logger.info(f"Starting index job worker for queue: {queue_arn}")

    # manually register the newrelic APM application since index worker only does background jobs (no web requests)
    # See https://docs.newrelic.com/docs/apm/agents/python-agent/python-agent-api/registerapplication-python-agent-api/#description
    newrelic.agent.register_application()

    async def run_sqs_processor():
        """Run the SQS processor."""
        try:
            # Create and start the processor
            processor = SQSJobProcessor(
                queue_arn=queue_arn,
                process_function=process_index_job,
                max_messages=1,  # Process one job at a time
                wait_time_seconds=20,  # Long polling
                # 6 minute vis timeout
                # TODO AIVP-460 extend visibility timeouts for long running tasks
                visibility_timeout_seconds=6 * 60,
            )

            await processor.start()
        finally:
            # Clean up worker resources
            await worker.cleanup()

    # Run both SQS processor and HTTP server
    await worker.run_with_http_server(run_sqs_processor())


if __name__ == "__main__":
    asyncio.run(main())
