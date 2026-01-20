import asyncio
import json
import logging
import zlib
from typing import cast
from urllib.parse import urlparse

import asyncpg
import boto3

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.slack.slack_models import SlackChannelDayFile, SlackExportBackfillConfig
from connectors.slack.slack_utils import create_slack_message_artifact
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = logging.getLogger(__name__)


class SlackExportBackfillExtractor(BaseExtractor[SlackExportBackfillConfig]):
    """
    Extracts Slack export backfill messages from specific channel-day files.
    This is a child job of SlackExportBackfillRootExtractor.
    """

    source_name = "slack_export_backfill"

    async def process_job(
        self,
        job_id: str,
        config: SlackExportBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # Track completion if backfill_id exists
        try:
            logger.info(
                f"Processing {len(config.channel_day_files)} channel-day files for job {job_id}"
            )

            # Process channel-day files in parallel
            tasks = []
            for channel_day_file in config.channel_day_files:
                task = self._process_channel_day_file(
                    job_id, config.uri, channel_day_file, db_pool, config.message_limit
                )
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)

            all_message_entity_ids: list[str] = []
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Error processing channel-day file: {result}")
                    raise result
                # Type narrowing using cast - we know this isn't an exception now
                entity_ids = cast(list[str], result)
                all_message_entity_ids.extend(entity_ids)

            logger.info(
                f"Successfully processed {len(all_message_entity_ids)} message artifacts for job {job_id}"
            )

            # Trigger indexing on all message entities together. Many messages typically make up a single doc,
            # so we don't want to separate messages from the same channel-day into different index jobs.
            if all_message_entity_ids:
                # Track total index jobs if backfill_id exists
                if config.backfill_id:
                    await increment_backfill_total_index_jobs(
                        config.backfill_id, config.tenant_id, 1
                    )

                await trigger_indexing(
                    all_message_entity_ids,
                    DocumentSource.SLACK,
                    config.tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

                logger.info(
                    f"Successfully triggered index job for {len(all_message_entity_ids)} messages from job {job_id}"
                )

            if config.backfill_id:
                await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)
        finally:
            # Always track that we attempted this job, regardless of success/failure
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )

    async def _process_channel_day_file(
        self,
        job_id: str,
        uri: str,
        channel_day_file: SlackChannelDayFile,
        db_pool: asyncpg.Pool,
        message_limit: int | None = None,
    ) -> list[str]:
        """Process a single channel-day file using HTTP Range requests."""
        try:
            # Read the specific bytes from the S3 ZIP file
            file_bytes = await self._read_bytes_from_uri(
                uri, channel_day_file.start_byte, channel_day_file.size
            )

            # Decompress the bytes (ZIP entry might be compressed)
            file_content = await self._decompress_zip_entry_bytes(file_bytes)

            # Parse JSON content
            messages_data = json.loads(file_content)

            if not messages_data:
                logger.warning(
                    f"No messages found in {channel_day_file.channel_name}/{channel_day_file.filename}"
                )
                return []

            # Process messages
            entity_ids = []
            batch = []
            batch_size = 1000
            message_count = 0

            for msg in messages_data:
                if msg.get("type") == "message" and "client_msg_id" in msg:
                    # Create artifact using shared utility function
                    artifact = create_slack_message_artifact(
                        msg, job_id, channel_day_file.channel_id
                    )
                    batch.append(artifact)
                    message_count += 1

                    # Process batch when it reaches batch_size
                    if len(batch) >= batch_size:
                        await self.store_artifacts_batch(db_pool, batch)
                        # Only keep entity_ids to save memory
                        entity_ids.extend([a.entity_id for a in batch])
                        batch = []

                    if message_limit and message_count >= message_limit:
                        logger.info(f"Reached message limit of {message_limit}")
                        # Store any remaining messages in current batch
                        if batch:
                            await self.store_artifacts_batch(db_pool, batch)
                            entity_ids.extend([a.entity_id for a in batch])
                        return entity_ids

            # Process any remaining messages in the final batch
            if batch:
                await self.store_artifacts_batch(db_pool, batch)
                entity_ids.extend([a.entity_id for a in batch])

            logger.info(
                f"Processed {len(entity_ids)} messages from {channel_day_file.channel_name}/{channel_day_file.filename}"
            )
            return entity_ids

        except Exception as e:
            logger.error(
                f"Error processing {channel_day_file.channel_name}/{channel_day_file.filename}: {e}"
            )
            raise

    async def _read_bytes_from_uri(self, uri: str, start_byte: int, size: int) -> bytes:
        """Read specific byte range from S3 using GetObject with Range."""
        parsed_uri = urlparse(uri)

        if parsed_uri.scheme != "s3":
            raise ValueError(f"Only S3 URIs are supported, got: {uri}")

        bucket = parsed_uri.netloc
        key = parsed_uri.path.lstrip("/")
        end_byte = start_byte + size - 1

        s3_client = boto3.client("s3")
        response = s3_client.get_object(
            Bucket=bucket, Key=key, Range=f"bytes={start_byte}-{end_byte}"
        )
        return response["Body"].read()

    async def _decompress_zip_entry_bytes(self, file_bytes: bytes) -> str:
        """Decompress ZIP entry bytes and return as string."""
        # The bytes we received are ZIP-compressed DEFLATE data from inside a ZIP file
        # ZIP uses DEFLATE but with different framing than raw zlib
        # -zlib.MAX_WBITS tells zlib to expect raw DEFLATE data
        decompressed = zlib.decompress(file_bytes, -zlib.MAX_WBITS)
        return decompressed.decode("utf-8")
