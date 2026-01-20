"""Slack message pruner for handling complete deletion flow."""

import logging
from datetime import UTC, datetime

import asyncpg

from connectors.base import BasePruner
from src.utils.pacific_time import (
    get_message_pacific_document_id,
    get_pacific_day_boundaries_timestamps,
)

logger = logging.getLogger(__name__)


class SlackPruner(BasePruner):
    """Singleton class for handling Slack message deletions across all data stores."""

    async def delete_message(
        self,
        channel: str,
        deleted_ts: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        client_msg_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """
        Delete a Slack message by removing artifacts and deleting the entire channel-day document + chunks.
        Then, find an entity_id from the same channel-day and return it to be re-indexed.

        Args:
            channel: Slack channel ID
            deleted_ts: Timestamp of the deleted message
            tenant_id: The tenant ID
            db_pool: Database connection pool
            client_msg_id: Client message ID if available

        Returns:
            Tuple of (success, entity_id_for_reindex)
            entity_id_for_reindex is None if no messages remain in that channel-day
        """
        if not channel or not deleted_ts:
            logger.warning("Incomplete message deletion data: missing channel or timestamp")
            return False, None

        logger.info(
            f"Deleting Slack message in channel {channel}, ts: {deleted_ts}, client_msg_id: {client_msg_id}"
        )

        # For Slack, we need special handling, so we'll use template method with custom functions
        entity_id = client_msg_id or deleted_ts  # Use client_msg_id if available, fallback to ts

        try:
            async with db_pool.acquire() as conn:
                # Create custom artifact deletion function that handles Slack's special logic
                async def slack_artifact_deletion(
                    conn: asyncpg.Connection, entity_type: str, entity_id: str
                ) -> int:
                    return await self._delete_message_artifacts(
                        conn, channel, deleted_ts, client_msg_id
                    )

                # Create custom document ID resolver for Slack messages
                def slack_document_resolver(entity_id: str) -> str:
                    return get_message_pacific_document_id(channel, deleted_ts)

                # Use the template method with our custom functions
                success = await self.delete_entity(
                    entity_id=entity_id,
                    tenant_id=tenant_id,
                    db_pool=db_pool,
                    document_id_resolver=slack_document_resolver,
                    custom_artifact_deletion=slack_artifact_deletion,
                    entity_type="slack_message",
                )

                # Find remaining entity for re-indexing (Slack-specific)
                entity_id_for_reindex = None
                if success:
                    entity_id_for_reindex = await self._find_channel_day_entity_for_reindex(
                        conn, channel, deleted_ts
                    )

                return success, entity_id_for_reindex

        except Exception as e:
            logger.error(f"Error deleting message {client_msg_id or deleted_ts}: {e}")
            return False, None

    async def _delete_message_artifacts(
        self,
        conn: asyncpg.Connection,
        channel: str,
        deleted_ts: str,
        client_msg_id: str | None,
    ) -> int:
        """Delete artifacts for the given message."""
        if client_msg_id:
            # Delete by client_msg_id (preferred)
            deleted_count = await self.delete_artifacts(conn, "slack_message", client_msg_id)
            logger.info(f"Deleted {deleted_count} artifacts for message_id: {client_msg_id}")
            return deleted_count
        else:
            # Delete by timestamp as fallback
            result = await conn.execute(
                """
                DELETE FROM ingest_artifact
                WHERE entity = 'slack_message'
                AND content->>'ts' = $1
                AND metadata->>'channel_id' = $2
                """,
                deleted_ts,
                channel,
            )
            deleted_count = int(result.split()[-1]) if result else 0
            logger.info(f"Deleted {deleted_count} artifacts for timestamp: {deleted_ts}")
            return deleted_count

    async def _find_channel_day_entity_for_reindex(
        self, conn: asyncpg.Connection, channel: str, deleted_ts: str
    ) -> str | None:
        """Find any remaining message entity_id from the same channel-day for re-indexing."""
        try:
            # Convert timestamp to Pacific date
            message_dt = datetime.fromtimestamp(float(deleted_ts), tz=UTC)
            pacific_date = message_dt.strftime("%Y-%m-%d")

            # Get Pacific day boundaries as timestamps
            start_ts, end_ts = get_pacific_day_boundaries_timestamps(pacific_date)

            # Find any message entity_id from the same channel-day
            entity_id: str | None = await conn.fetchval(
                """
                SELECT entity_id FROM ingest_artifact
                WHERE entity = 'slack_message'
                AND metadata->>'channel_id' = $1
                AND (content->>'ts')::float >= $2
                AND (content->>'ts')::float <= $3
                LIMIT 1
                """,
                channel,
                start_ts,
                end_ts,
            )

            if entity_id:
                logger.info(f"Found entity_id {entity_id} for channel-day re-indexing")
            else:
                logger.info(
                    f"No remaining messages in channel-day {channel} {pacific_date}, skipping re-indexing"
                )

            return entity_id

        except Exception as e:
            logger.warning(f"Error finding entity for re-indexing: {e}")
            return None

    async def delete_channel(
        self,
        channel_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> bool:
        """
        Delete a Slack channel and all associated data from all data stores.

        This includes:
        - All slack_channel artifacts for this channel
        - All slack_message artifacts for this channel
        - All channel-day documents and their chunks

        Args:
            channel_id: The Slack channel ID to delete
            tenant_id: The tenant ID
            db_pool: Database connection pool

        Returns:
            True if deletion was successful, False otherwise
        """
        if not channel_id:
            logger.warning("No channel_id provided for channel deletion")
            return False

        logger.info(f"Starting Slack channel deletion: {channel_id} for tenant {tenant_id}")

        try:
            async with db_pool.acquire() as conn:
                # 1. Delete all slack_channel artifacts for this channel
                channel_artifacts_deleted = await self.delete_artifacts(
                    conn, "slack_channel", channel_id
                )
                logger.info(f"Deleted {channel_artifacts_deleted} slack_channel artifacts")

                # 2. Delete all slack_message artifacts for this channel
                message_result = await conn.execute(
                    "DELETE FROM ingest_artifact WHERE entity = 'slack_message' AND metadata->>'channel_id' = $1",
                    channel_id,
                )
                message_artifacts_deleted = int(message_result.split()[-1]) if message_result else 0
                logger.info(
                    f"Deleted {message_artifacts_deleted} slack_message artifacts for channel {channel_id}"
                )

                # 3. Find and delete all channel-day documents
                from connectors.base.doc_ids import get_slack_channel_doc_ids

                document_ids = await get_slack_channel_doc_ids(channel_id, conn)

                if not document_ids:
                    logger.info(f"No documents found for channel {channel_id}")
                    return True

                logger.info(
                    f"Found {len(document_ids)} documents to delete for channel {channel_id}: {document_ids}"
                )

                # Delete each document and its chunks
                successful_deletions = 0
                for document_id in document_ids:
                    success = await self.delete_document(document_id, tenant_id, db_pool)
                    if success:
                        successful_deletions += 1
                    else:
                        logger.warning(f"Failed to delete document {document_id}")

                total_artifacts_deleted = channel_artifacts_deleted + message_artifacts_deleted

                # Only consider it successful if ALL document deletions succeeded
                all_documents_deleted = successful_deletions == len(document_ids)

                if all_documents_deleted:
                    logger.info(
                        f"✅ Channel deletion completed successfully for {channel_id}: "
                        f"{total_artifacts_deleted} artifacts deleted, "
                        f"{successful_deletions}/{len(document_ids)} documents deleted"
                    )
                else:
                    logger.error(
                        f"❌ Channel deletion incomplete for {channel_id}: "
                        f"{total_artifacts_deleted} artifacts deleted, "
                        f"only {successful_deletions}/{len(document_ids)} documents deleted successfully"
                    )

                return all_documents_deleted

        except Exception as e:
            logger.error(f"❌ Error deleting Slack channel {channel_id}: {e}")
            return False


# Singleton instance
slack_pruner = SlackPruner()
