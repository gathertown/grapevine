"""
Confluence API backfill extractor for processing individual space batches.
"""

import logging
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.confluence.confluence_artifacts import (
    ConfluencePageArtifact,
    ConfluenceSpaceArtifact,
)
from connectors.confluence.confluence_base import ConfluenceExtractor
from connectors.confluence.confluence_models import ConfluenceApiBackfillConfig
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

# Store and trigger indexing in batches of 10 to avoid memory issues for large spaces
ARTIFACT_BATCH_SIZE = 10


class ConfluenceApiBackfillExtractor(ConfluenceExtractor[ConfluenceApiBackfillConfig]):
    """Extractor for processing Confluence space batches via API."""

    source_name = "confluence_api_backfill"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__(ssm_client, sqs_client)

    async def process_job(
        self,
        job_id: str,
        config: ConfluenceApiBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process Confluence API backfill job for specified spaces."""
        logger.info(
            f"Starting Confluence API backfill job {job_id} for tenant {config.tenant_id} "
            f"with {len(config.space_batches)} space batches"
        )

        try:
            confluence_client = await self.get_confluence_client(config.tenant_id)

            artifact_batch: list[ConfluencePageArtifact | ConfluenceSpaceArtifact] = []
            page_entity_ids_batch: list[str] = []

            for space_batch in config.space_batches:
                logger.info(
                    f"Processing Confluence space: {space_batch.space_name} ({space_batch.space_key})"
                )

                try:
                    await self._load_space_info(space_batch.space_id, config.tenant_id)

                    cursor = None

                    while True:
                        response = confluence_client.get_space_pages(
                            space_id=space_batch.space_id, cursor=cursor
                        )

                        pages = response.get("results", [])
                        if not pages:
                            break

                        logger.info(
                            f"Processing {len(pages)} pages from space {space_batch.space_key}"
                        )

                        for page in pages:
                            page_id = page["id"]
                            try:
                                page_data = confluence_client.get_page(page_id)
                                if not page_data:
                                    logger.warning(f"Skipping missing page {page_id}")
                                    continue

                                if config.start_timestamp:
                                    page_updated_at = page_data.get("version", {}).get("when")
                                    if page_updated_at:
                                        try:
                                            updated_datetime = datetime.fromisoformat(
                                                page_updated_at.replace("Z", "+00:00")
                                            )
                                            if updated_datetime < config.start_timestamp.replace(
                                                tzinfo=None
                                            ):
                                                logger.debug(
                                                    f"Skipping page {page_id} - updated before start timestamp"
                                                )
                                                continue
                                        except (ValueError, TypeError):
                                            logger.warning(
                                                f"Failed to parse update timestamp for page {page_id}"
                                            )

                                page_artifacts = await self._process_page(
                                    job_id, page_data, config.tenant_id
                                )

                                artifact_batch.extend(page_artifacts)
                                for artifact in page_artifacts:
                                    if isinstance(artifact, ConfluencePageArtifact):
                                        page_entity_ids_batch.append(artifact.entity_id)

                                if len(artifact_batch) >= ARTIFACT_BATCH_SIZE:
                                    logger.info(
                                        f"Storing batch of {len(artifact_batch)} Confluence artifacts"
                                    )
                                    await self.store_artifacts_batch(db_pool, artifact_batch)

                                    if page_entity_ids_batch:
                                        await trigger_indexing(
                                            page_entity_ids_batch,
                                            DocumentSource.CONFLUENCE,
                                            config.tenant_id,
                                            config.backfill_id,
                                            config.suppress_notification,
                                        )
                                        logger.info(
                                            f"Triggered indexing for batch of {len(page_entity_ids_batch)} pages"
                                        )

                                    artifact_batch = []
                                    page_entity_ids_batch = []

                            except Exception as e:
                                logger.error(f"Failed to process page {page_id}: {e}")
                                continue

                        next_link = response.get("_links", {}).get("next")
                        if not next_link:
                            break

                        parsed = urlparse(next_link)
                        cursor_params = parse_qs(parsed.query).get("cursor", [])
                        cursor = cursor_params[0] if cursor_params else None
                        if not cursor:
                            break

                except Exception as e:
                    logger.error(f"Failed to process space {space_batch.space_key}: {e}")
                    continue

            if artifact_batch:
                logger.info(f"Storing final batch of {len(artifact_batch)} Confluence artifacts")
                await self.store_artifacts_batch(db_pool, artifact_batch)

                if page_entity_ids_batch:
                    await trigger_indexing(
                        page_entity_ids_batch,
                        DocumentSource.CONFLUENCE,
                        config.tenant_id,
                        config.backfill_id,
                        config.suppress_notification,
                    )
                    logger.info(
                        f"Triggered indexing for final batch of {len(page_entity_ids_batch)} pages"
                    )

        except Exception as e:
            logger.error(f"Confluence API backfill job {job_id} failed: {e}")
            raise
