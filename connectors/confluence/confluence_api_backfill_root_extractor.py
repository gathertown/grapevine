"""
Confluence API backfill root extractor for discovering spaces and creating child jobs.
"""

import logging
from datetime import UTC, datetime
from uuid import uuid4

import asyncpg

from connectors.base import TriggerIndexingCallback, get_confluence_space_entity_id
from connectors.confluence.confluence_artifacts import (
    ConfluenceSpaceArtifact,
    ConfluenceSpaceArtifactContent,
    ConfluenceSpaceArtifactMetadata,
)
from connectors.confluence.confluence_base import ConfluenceExtractor
from connectors.confluence.confluence_models import (
    ConfluenceApiBackfillConfig,
    ConfluenceApiBackfillRootConfig,
    ConfluenceSpaceBatch,
)
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


class ConfluenceApiBackfillRootExtractor(ConfluenceExtractor[ConfluenceApiBackfillRootConfig]):
    """Root extractor for Confluence API backfill - discovers spaces and creates child jobs."""

    source_name = "confluence_api_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__(ssm_client, sqs_client)

    async def process_job(
        self,
        job_id: str,
        config: ConfluenceApiBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process root Confluence API backfill job - discover spaces and create child jobs."""
        logger.info(
            f"Starting Confluence API backfill root job {job_id} for tenant {config.tenant_id}"
        )

        try:
            confluence_client = await self.get_confluence_client(config.tenant_id)

            # Get all spaces or filter by specified space keys
            all_spaces = confluence_client.get_spaces()

            # Filter spaces if specific space keys were requested
            if config.space_keys:
                filtered_spaces = [space for space in all_spaces if space.key in config.space_keys]
                logger.info(
                    f"Filtered {len(all_spaces)} spaces to {len(filtered_spaces)} "
                    f"based on requested keys: {config.space_keys}"
                )
                spaces_to_process = filtered_spaces
            else:
                spaces_to_process = all_spaces
                logger.info(f"Processing all {len(spaces_to_process)} accessible spaces")

            if not spaces_to_process:
                logger.warning("No Confluence spaces found to process")
                return

            # First, discover and store all space artifacts (following Google Drive pattern)
            logger.info(f"Storing {len(spaces_to_process)} Confluence space artifacts")
            for space in spaces_to_process:
                try:
                    site_domain = await confluence_client.get_site_domain(config.tenant_id)

                    space_artifact = ConfluenceSpaceArtifact(
                        entity_id=get_confluence_space_entity_id(space_id=space.id),
                        ingest_job_id=uuid4(),
                        content=ConfluenceSpaceArtifactContent(space_data=space.__dict__),
                        metadata=ConfluenceSpaceArtifactMetadata(
                            space_id=space.id,
                            space_key=space.key,
                            space_name=space.name,
                            space_type=space.type,
                            site_domain=site_domain,
                        ),
                        source_updated_at=datetime.now(UTC),
                    )

                    await self.store_artifact(db_pool, space_artifact)
                    logger.debug(f"Stored space artifact for {space.name} ({space.key})")

                except Exception as e:
                    logger.error(f"Failed to store space artifact for {space.key}: {e}")

            # Create space batches
            space_batches = []
            for space in spaces_to_process:
                batch = ConfluenceSpaceBatch(
                    space_key=space.key,
                    space_id=space.id,
                    space_name=space.name,
                )
                space_batches.append(batch)

            logger.info(f"Created {len(space_batches)} space batches")

            # Generate backfill ID for tracking
            backfill_id = str(uuid4())

            # Send child backfill jobs - one space per child job
            for i, space_batch in enumerate(space_batches):
                child_config = ConfluenceApiBackfillConfig(
                    tenant_id=config.tenant_id,
                    space_batches=[space_batch],  # Single space per child job
                    backfill_id=backfill_id,
                    suppress_notification=config.suppress_notification,
                )

                await self.send_backfill_child_job_message(
                    child_config,
                    f"Confluence space {space_batch.space_key}",
                )

                logger.info(
                    f"Sent child job {i + 1}/{len(space_batches)} for space {space_batch.space_key} ({space_batch.space_name})"
                )

            logger.info(
                f"Completed Confluence API backfill root job {job_id}. "
                f"Created {len(space_batches)} child jobs (one per space)."
            )

        except Exception as e:
            logger.error(f"Confluence API backfill root job {job_id} failed: {e}")
            raise
