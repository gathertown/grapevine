"""
Full re-index extractor that triggers re-indexing of all artifacts for a given source type.
"""

import logging
from datetime import UTC, datetime

import asyncpg

from connectors.base import ArtifactEntity, BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from src.clients.sqs import SQSClient
from src.jobs.models import IndexJobMessage, ReindexJobMessage

logger = logging.getLogger(__name__)

# Hardcoded configuration
BATCH_SIZE = 20


class FullReindexExtractor(BaseExtractor[ReindexJobMessage]):
    """
    Extractor that triggers full re-indexing of all artifacts for a given source type.

    WARNING: This is an extractor meant for manual use only! Monitor the ingest worker
    that picks up this job to ensure it's processing the job correctly.
    """

    source_name = "full_reindex"

    def __init__(self):
        """Initialize the extractor."""
        super().__init__()
        self.source_to_entities = self._build_source_to_entities_map()

    def _build_source_to_entities_map(self) -> dict[DocumentSource, list[ArtifactEntity]]:
        """Build mapping from DocumentSource to the ArtifactEntity types it processes."""
        return {
            DocumentSource.SLACK: [ArtifactEntity.SLACK_MESSAGE],
            DocumentSource.GITHUB_PRS: [ArtifactEntity.GITHUB_PR],
            DocumentSource.GITHUB_CODE: [ArtifactEntity.GITHUB_FILE],
            DocumentSource.NOTION: [ArtifactEntity.NOTION_PAGE],
            DocumentSource.LINEAR: [ArtifactEntity.LINEAR_ISSUE],
            DocumentSource.GOOGLE_DRIVE: [ArtifactEntity.GOOGLE_DRIVE_FILE],
            # Add other sources as needed
            DocumentSource.GOOGLE_EMAIL: [ArtifactEntity.GOOGLE_EMAIL_MESSAGE],
            DocumentSource.HUBSPOT_DEAL: [ArtifactEntity.HUBSPOT_DEAL],
            DocumentSource.HUBSPOT_COMPANY: [ArtifactEntity.HUBSPOT_COMPANY],
            DocumentSource.ZENDESK_TICKET: [ArtifactEntity.ZENDESK_TICKET],
            DocumentSource.TRELLO: [ArtifactEntity.TRELLO_CARD],
            DocumentSource.ASANA_TASK: [ArtifactEntity.ASANA_TASK],
        }

    async def process_job(
        self,
        job_id: str,
        config: ReindexJobMessage,
        readonly_db_pool: asyncpg.Pool,
        _trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a full re-index job by fetching all artifacts for the source type
        and triggering index jobs in batches with random delays.

        Args:
            job_id: The ingest job ID
            config: ReindexJobMessage with source and tenant_id
            readonly_db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing jobs
        """
        source = config.source
        tenant_id = config.tenant_id

        logger.info(f"Starting full re-index for source {source.value}, tenant {tenant_id}")

        # Get entity types for this source
        entity_types = self.source_to_entities.get(source, [])
        if not entity_types:
            raise ValueError(f"No entity types configured for source {source.value}")

        # Get minimal artifact data for these entity types
        all_artifacts = []

        async with readonly_db_pool.acquire() as conn:
            for entity_type in entity_types:
                logger.info(f"Fetching artifacts for entity type {entity_type.value}")

                # Use minimal query based on source type
                if source == DocumentSource.SLACK:
                    # For Slack, we need entity_id, channel_id, and timestamp for grouping
                    query = """
                        SELECT entity_id,
                               metadata->>'channel_id' as channel_id,
                               content->>'ts' as ts
                        FROM ingest_artifact
                        WHERE entity = $1
                    """
                    rows = await conn.fetch(query, entity_type.value)
                    artifacts = [dict(row) for row in rows]
                else:
                    # For other sources, we only need entity_id
                    query = """
                        SELECT entity_id
                        FROM ingest_artifact
                        WHERE entity = $1
                    """
                    rows = await conn.fetch(query, entity_type.value)
                    artifacts = [dict(row) for row in rows]

                logger.info(f"Found {len(artifacts)} artifacts for entity type {entity_type.value}")
                all_artifacts.extend(artifacts)

        if not all_artifacts:
            logger.warning(f"No artifacts found for source {source.value}")
            return

        logger.info(f"Total artifacts to re-index: {len(all_artifacts)}")

        # Handle Slack specially - group by channel-days
        if source == DocumentSource.SLACK:
            entity_ids_to_process = self._group_slack_by_channel_days(all_artifacts)
            logger.info(
                f"Slack: Grouped {len(all_artifacts)} messages into "
                f"{len(entity_ids_to_process)} channel-day representatives"
            )
        else:
            entity_ids_to_process = [artifact["entity_id"] for artifact in all_artifacts]

        # Send index jobs directly to SQS with delays
        await self._send_index_jobs(
            entity_ids_to_process, source, tenant_id, config.turbopuffer_only
        )

        logger.info(
            f"Successfully triggered re-indexing for {len(entity_ids_to_process)} entities "
            f"(source: {source.value}, tenant: {tenant_id})"
        )

    async def _send_index_jobs(
        self,
        entity_ids: list[str],
        source: DocumentSource,
        tenant_id: str,
        turbopuffer_only: bool = False,
    ) -> None:
        """Send index jobs to SQS with delays to distribute load."""
        if not entity_ids:
            logger.warning("No entity IDs to send for indexing")
            return

        # Get the index jobs queue ARN
        sqs_client = SQSClient()

        # Process in batches
        batch_count = 0
        total_batches = (len(entity_ids) + BATCH_SIZE - 1) // BATCH_SIZE

        for i in range(0, len(entity_ids), BATCH_SIZE):
            batch = entity_ids[i : i + BATCH_SIZE]
            batch_count += 1

            logger.info(
                f"Sending index job batch {batch_count}/{total_batches} "
                f"with {len(batch)} entities (source: {source.value})"
            )

            # Create the index job message
            index_message = IndexJobMessage(
                entity_ids=batch,
                source=source,
                tenant_id=tenant_id,
                force_reindex=True,
                turbopuffer_only=turbopuffer_only,
            )

            # Send message to SQS
            success = await sqs_client.send_index_message(
                index_message=index_message,
            )

            if not success:
                logger.error(
                    f"Failed to send index job batch {batch_count} to SQS "
                    f"for {len(batch)} {source.value} entities"
                )
                raise RuntimeError(f"Failed to send index job batch {batch_count} to SQS")

        logger.info(f"Successfully sent {batch_count} index job batches for {source.value} to SQS")

    def _group_slack_by_channel_days(self, artifact_rows: list[dict]) -> list[str]:
        """
        Group Slack message artifacts by channel-day and return one representative per group.

        Args:
            artifacts: List of minimal Slack message artifact dictionaries with entity_id, channel_id, ts

        Returns:
            List of representative entity IDs (one per channel-day)
        """
        if not artifact_rows:
            return []

        logger.info(f"Grouping {len(artifact_rows)} Slack messages by channel-day")

        # Group by (channel_id, date) and pick one representative per group
        channel_day_reps = {}

        for artifact in artifact_rows:
            entity_id = artifact["entity_id"]
            channel_id = artifact.get("channel_id")
            ts: str = artifact.get("ts", "")

            try:
                # Convert timestamp to date
                dt = datetime.fromtimestamp(float(ts), tz=UTC)
                date_str = dt.strftime("%Y-%m-%d")

                # Use (channel_id, date) as key
                key = (channel_id, date_str)

                # If this channel-day combo hasn't been seen, use this entity as representative
                if key not in channel_day_reps:
                    channel_day_reps[key] = entity_id

            except (ValueError, TypeError) as e:
                logger.error(f"Invalid timestamp {ts} for entity {entity_id}: {e}")
                continue

        representatives = list(channel_day_reps.values())
        logger.info(
            f"Selected {len(representatives)} representative messages from "
            f"{len(channel_day_reps)} unique channel-days"
        )

        return representatives
