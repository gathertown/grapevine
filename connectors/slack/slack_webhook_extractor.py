import logging
from typing import Any

import asyncpg
from pydantic import BaseModel

from connectors.base import BaseExtractor, BaseIngestArtifact, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.slack.slack_pruner import slack_pruner
from connectors.slack.slack_utils import create_slack_message_artifact
from src.utils.slack_bot_rate_limiter import extract_bot_id, should_allow_slack_bot_message
from src.utils.slack_filters import is_bot_message

logger = logging.getLogger(__name__)


class ProcessingDecision(BaseModel):
    """Decision about how to process a Slack webhook payload."""

    should_process: bool
    should_delete_channel: bool
    reason: str | None


class SlackWebhookConfig(BaseModel):
    body: dict[str, Any]
    tenant_id: str


class SlackWebhookExtractor(BaseExtractor[SlackWebhookConfig]):
    """Extractor for processing Slack webhook events."""

    source_name = "slack_webhook"

    async def process_job(
        self,
        job_id: str,
        config: SlackWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a Slack webhook ingest job.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to Slack webhooks
            db_pool: Database connection pool

        Raises:
            Exception: If processing fails
        """
        try:
            logger.info(f"Processing Slack webhook job {job_id}")

            payload = config.body

            if payload.get("type") == "url_verification":
                raise ValueError(
                    "URL verification challenge received in extractor - this should be handled by controller"
                )

            decision = self._should_process_payload(payload)

            if decision.should_delete_channel:
                # Handle non-public channel deletion
                event_payload = payload.get("event", {})
                if isinstance(event_payload, dict):
                    await self._handle_non_public_channel_deletion(
                        job_id, event_payload, db_pool, config.tenant_id
                    )
                logger.info(f"Processed non-public channel deletion: {decision.reason}")
                return
            elif not decision.should_process:
                logger.info(f"Ignoring Slack event: {decision.reason}")
                return

            artifacts: list[BaseIngestArtifact] = []

            event_payload = payload.get("event", None)
            if isinstance(event_payload, dict):
                artifacts.extend(
                    await self._handle_slack_event(
                        job_id, event_payload, db_pool, config.tenant_id, trigger_indexing
                    )
                )
            else:
                logger.info(f"Ignoring unsupported Slack event type: {payload.get('type')}")

            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)

            logger.info(f"Successfully updated {len(artifacts)} artifacts for job {job_id}")

            if artifacts:
                entity_ids = [artifact.entity_id for artifact in artifacts]
                await trigger_indexing(entity_ids, DocumentSource.SLACK, config.tenant_id)

        except Exception as e:
            logger.error(f"Failed to process Slack webhook job {job_id}: {e}")
            raise

    def _should_process_payload(self, payload: dict[str, Any]) -> ProcessingDecision:
        event = payload.get("event", {})
        if not event and payload.get("type") != "event_callback":
            event = payload

        if event.get("type") and event["type"] != "message":
            return ProcessingDecision(should_process=True, should_delete_channel=False, reason=None)

        channel_type = event.get("channel_type", "")
        if channel_type in ["group", "im", "mpim"]:
            return ProcessingDecision(
                should_process=False,
                should_delete_channel=True,
                reason=f"private channel/DM (channel_type={channel_type})",
            )

        user_profile = event.get("user_profile", {})
        if user_profile.get("is_stranger", False):
            return ProcessingDecision(
                should_process=False,
                should_delete_channel=False,
                reason="external user (is_stranger=true)",
            )

        user_team = event.get("user_team", "")
        team = event.get("team", "")
        if user_team and team and user_team != team:
            return ProcessingDecision(
                should_process=False,
                should_delete_channel=False,
                reason=f"external team message (user_team={user_team} != {team})",
            )

        return ProcessingDecision(should_process=True, should_delete_channel=False, reason=None)

    async def _handle_slack_event(
        self,
        job_id: str,
        event: dict[str, Any],
        db_pool: asyncpg.Pool,
        tenant_id: str,
        trigger_indexing: TriggerIndexingCallback | None = None,
    ) -> list[BaseIngestArtifact]:
        """Route Slack events to appropriate handlers."""
        event_type = event.get("type", "")
        subtype = event.get("subtype", "")

        if event_type == "message":
            if subtype == "message_changed":
                return await self._handle_message_changed_event(job_id, event, tenant_id)
            elif subtype == "message_deleted":
                return await self._handle_message_deleted_event(
                    event, db_pool, tenant_id, trigger_indexing
                )
            else:
                return await self._handle_message_event(job_id, event, tenant_id)
        elif event_type == "channel_deleted":
            return await self._handle_channel_deleted_event(event, db_pool, tenant_id)
        else:
            logger.info(f"Ignoring unsupported Slack event type: {event_type}")
            return []

    async def _handle_message_event(
        self, job_id: str, event: dict[str, Any], tenant_id: str
    ) -> list[BaseIngestArtifact]:
        """Convert a message event to SlackMessageArtifact."""
        channel = event.get("channel", "")
        text = event.get("text", "")
        ts = event.get("ts", "")

        if not channel or not ts:
            logger.warning("Incomplete message event data")
            return []

        files = event.get("files", [])
        attachments = event.get("attachments", [])
        if not text and not files and not attachments:
            logger.info("Skipping message with no text, files, or attachments")
            return []

        # Rate limit bot messages
        if is_bot_message(event):
            bot_id = extract_bot_id(event)
            if bot_id:
                allowed = await should_allow_slack_bot_message(tenant_id, bot_id)
                if not allowed:
                    logger.info(
                        f"Dropping Slack bot message due to rate limit: "
                        f"tenant={tenant_id} bot={bot_id} subtype={event.get('subtype')}"
                    )
                    return []
            else:
                logger.warning(
                    f"Bot message without bot_id for tenant={tenant_id}, allowing through"
                )

        logger.info(f"Processing message event in channel {channel}")

        try:
            artifact = create_slack_message_artifact(event, job_id, channel)
            return [artifact]

        except Exception as e:
            logger.error(f"Error processing message event: {e}")
            return []

    async def _handle_message_changed_event(
        self, job_id: str, event: dict[str, Any], tenant_id: str
    ) -> list[BaseIngestArtifact]:
        """Handle message edit events."""
        message = event.get("message", {})
        channel = event.get("channel", "")

        if not message or not channel:
            return []

        logger.info(f"Processing message edit event in channel {channel}")

        message["channel"] = channel
        return await self._handle_message_event(job_id, message, tenant_id)

    async def _handle_message_deleted_event(
        self,
        event: dict[str, Any],
        db_pool: asyncpg.Pool,
        tenant_id: str,
        trigger_indexing: TriggerIndexingCallback | None = None,
    ) -> list[BaseIngestArtifact]:
        """Handle message deletion events using SlackPruner."""
        channel = event.get("channel", "")
        deleted_ts = event.get("deleted_ts", "")
        previous_message = event.get("previous_message", {})
        client_msg_id = previous_message.get("client_msg_id", "") if previous_message else ""

        if not channel or not deleted_ts:
            logger.warning("Incomplete message deletion event data")
            return []

        logger.info(
            f"Message deleted in channel {channel}, ts: {deleted_ts}, client_msg_id: {client_msg_id}"
        )

        success, entity_id_for_reindex = await slack_pruner.delete_message(
            channel=channel,
            deleted_ts=deleted_ts,
            tenant_id=tenant_id,
            db_pool=db_pool,
            client_msg_id=client_msg_id,
        )

        if success:
            logger.info(
                f"Successfully processed message deletion for {client_msg_id or deleted_ts}"
            )
            # Trigger re-indexing for the channel-day if there are remaining messages
            if entity_id_for_reindex and trigger_indexing and tenant_id:
                await trigger_indexing([entity_id_for_reindex], DocumentSource.SLACK, tenant_id)
                logger.info(f"Triggered re-indexing for entity {entity_id_for_reindex}")
        else:
            logger.error(f"Failed to process message deletion for {client_msg_id or deleted_ts}")

        return []

    async def _handle_channel_deleted_event(
        self,
        event: dict[str, Any],
        db_pool: asyncpg.Pool,
        tenant_id: str,
    ) -> list[BaseIngestArtifact]:
        """Handle channel deletion events using SlackPruner."""
        channel_id = event.get("channel", "")

        if not channel_id:
            logger.warning("Incomplete channel deletion event data: missing channel ID")
            return []

        logger.info(f"Channel deleted: {channel_id}")

        success = await slack_pruner.delete_channel(
            channel_id=channel_id,
            tenant_id=tenant_id,
            db_pool=db_pool,
        )

        if success:
            logger.info(f"Successfully processed channel deletion for {channel_id}")
        else:
            logger.error(f"Failed to process channel deletion for {channel_id}")

        # Channel deletion doesn't produce new artifacts, just removes existing ones
        return []

    async def _handle_non_public_channel_deletion(
        self,
        job_id: str,
        event: dict[str, Any],
        db_pool: asyncpg.Pool,
        tenant_id: str,
    ) -> None:
        """Handle deletion of channel data when receiving webhooks from non-public channels."""
        channel_id = event.get("channel", "")
        channel_type = event.get("channel_type", "")

        if not channel_id:
            logger.warning(f"Cannot delete non-public channel: missing channel ID in job {job_id}")
            return

        logger.info(
            f"Deleting channel data for non-public channel {channel_id} "
            f"(type: {channel_type}) from job {job_id}"
        )

        try:
            from connectors.slack.slack_pruner import slack_pruner

            success = await slack_pruner.delete_channel(
                channel_id=channel_id,
                tenant_id=tenant_id,
                db_pool=db_pool,
            )

            if success:
                logger.info(
                    f"Successfully deleted non-public channel {channel_id} data from job {job_id}"
                )
            else:
                logger.error(
                    f"Failed to delete non-public channel {channel_id} data from job {job_id}"
                )

        except Exception as e:
            logger.error(f"Error deleting non-public channel {channel_id} from job {job_id}: {e}")
