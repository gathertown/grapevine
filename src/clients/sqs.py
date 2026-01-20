"""AWS SQS client for queue operations and message publishing."""

import asyncio
import json
import uuid
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import Any

import sqs_extended_client  # noqa: F401 # Required for monkey-patching boto3 SQS client
from botocore.client import BaseClient

from connectors.base.external_source import ExternalSource
from connectors.base.models import BackfillIngestConfig
from src.clients.aws_base import AWSBaseClient
from src.jobs.lanes import get_delete_lane, get_index_lane, get_ingest_lane, get_slackbot_lane
from src.jobs.models import (
    DeleteJobMessage,
    IndexJobMessage,
    SlackBotControlMessage,
    WebhookIngestJobMessage,
)
from src.utils.config import (
    get_config_value,
    get_sqs_extended_enabled,
    get_sqs_extended_s3_bucket,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

INDEX_JOBS_QUEUE_ARN = get_config_value("INDEX_JOBS_QUEUE_ARN")
INGEST_JOBS_QUEUE_ARN = get_config_value("INGEST_JOBS_QUEUE_ARN")
SLACK_JOBS_QUEUE_ARN = get_config_value("SLACK_JOBS_QUEUE_ARN")

MAX_SQS_VISIBILITY_TIMEOUT_SECONDS = 12 * 60 * 60  # 12 hours in seconds

INGEST_JOBS_LARGE_PAYLOAD_SIZE = 256 * 1024  # 256 KB


def cap_sqs_visibility_timeout(delay_seconds: int) -> int:
    """Cap delay to SQS maximum visibility timeout with logging.

    Returns:
        The capped delay seconds, guaranteed to be <= MAX_SQS_VISIBILITY_TIMEOUT_SECONDS
    """
    if delay_seconds > MAX_SQS_VISIBILITY_TIMEOUT_SECONDS:
        logger.warning(
            f"Requested delay of {delay_seconds}s exceeds SQS maximum of "
            f"{MAX_SQS_VISIBILITY_TIMEOUT_SECONDS}s. Using maximum timeout."
        )
        return MAX_SQS_VISIBILITY_TIMEOUT_SECONDS
    return delay_seconds


def run_in_executor[T](func: Callable[..., T]) -> Callable[..., asyncio.Future[T]]:
    """Decorator to run boto3 calls in a thread pool to avoid blocking the event loop.

    This is critical for long-running operations like SQS long polling.
    """

    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        loop = asyncio.get_event_loop()
        # Create a partial function with self bound
        return await loop.run_in_executor(None, lambda: func(self, *args, **kwargs))

    return wrapper


class SQSClient(AWSBaseClient):
    """Client for AWS SQS (Simple Queue Service) operations."""

    def __init__(self, region_name: str | None = None):
        """Initialize SQS client.

        Args:
            region_name: AWS region name, defaults to config value
        """
        super().__init__("sqs", region_name)
        self._extended_client = None
        self._extended_client_enabled = False
        self._extended_client_s3_bucket: str | None = None

    def _convert_arn_to_url(self, queue_arn: str) -> str:
        """Convert SQS queue ARN to URL format required by boto3.

        Args:
            queue_arn: SQS queue ARN (e.g., arn:aws:sqs:us-east-1:123456789012:my-queue)

        Returns:
            Queue URL (e.g., https://sqs.us-east-1.amazonaws.com/123456789012/my-queue)

        Raises:
            ValueError: If ARN format is invalid
        """
        # If it's already a URL (starts with https://), return as-is
        if queue_arn.startswith("https://"):
            return queue_arn

        # Parse ARN format: arn:aws:sqs:region:account-id:queue-name
        try:
            arn_parts = queue_arn.split(":")
            if len(arn_parts) != 6 or arn_parts[0] != "arn" or arn_parts[2] != "sqs":
                raise ValueError(f"Invalid SQS ARN format: {queue_arn}")

            region = arn_parts[3]
            account_id = arn_parts[4]
            queue_name = arn_parts[5]

            # Construct the queue URL
            queue_url = f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"
            logger.debug(f"Converted ARN {queue_arn} to URL {queue_url}")
            return queue_url

        except (IndexError, ValueError) as e:
            raise ValueError(f"Failed to parse SQS ARN {queue_arn}: {e}")

    def _configure_extended_client(self) -> None:
        """Initialize extended client configuration if available."""
        if self._extended_client_enabled:
            return  # Already initialized

        enabled = get_sqs_extended_enabled()
        self._extended_client_enabled = enabled
        if not enabled:
            return
        self._extended_client_s3_bucket = get_sqs_extended_s3_bucket()

        if not self._extended_client_s3_bucket:
            logger.warning("SQS Extended Client enabled but no S3 bucket configured")
            self._extended_client_enabled = False

    def _create_extended_client(self) -> BaseClient:
        """Create the AWS SQS Extended Client using the existing session."""
        try:
            # Use the existing session - automatically handles credentials, endpoint URL, region, etc.
            extended_client = self.session.client("sqs")

            # Configure extended client settings
            extended_client.large_payload_support = self._extended_client_s3_bucket
            extended_client.use_legacy_attribute = False  # Use current format
            extended_client.delete_payload_from_s3 = True  # Cleanup S3 objects

            logger.info(
                f"Created extended SQS client with bucket: {self._extended_client_s3_bucket}"
            )
            return extended_client

        except Exception as e:
            logger.error(f"Failed to create extended SQS client: {e}")
            raise

    def _get_extended_client(self) -> BaseClient | None:
        """Get or create the extended SQS client for ingest operations."""
        self._configure_extended_client()

        if not self._extended_client_enabled:
            return None

        if self._extended_client is None:
            self._extended_client = self._create_extended_client()
        return self._extended_client

    def _should_use_extended_client(self, queue_url: str) -> bool:
        """Check if extended client should be used for this queue URL.

        Args:
            queue_url: SQS queue URL

        Returns:
            True if extended client should be used, False otherwise
        """
        ingest_queue_url = self._convert_arn_to_url(INGEST_JOBS_QUEUE_ARN)
        return queue_url == ingest_queue_url and self._get_extended_client() is not None

    def _get_client_for_queue_url(self, queue_url: str) -> BaseClient:
        """Get appropriate client (extended or standard) based on queue URL.

        Args:
            queue_url: SQS queue URL (e.g., https://sqs.us-east-1.amazonaws.com/123456789012/my-queue)

        Returns:
            Extended client for ingest queue, standard client for others
        """
        if self._should_use_extended_client(queue_url):
            return self._get_extended_client()
        return self.client

    @run_in_executor
    def _send_message_sync(self, queue_url: str, send_params: dict[str, Any]) -> dict[str, Any]:
        """Synchronous helper for sending SQS messages."""
        client = self._get_client_for_queue_url(queue_url)
        return client.send_message(**send_params)

    async def send_message(
        self,
        queue_arn: str,
        message_body: str | dict[str, Any],
        message_group_id: str,
        message_attributes: dict[str, Any] | None = None,
        message_deduplication_id: str | None = None,
    ) -> str | None:
        """Send message to SQS queue.

        Args:
            queue_arn: SQS queue ARN
            message_body: Message body (string or dict that will be JSON-encoded)
            message_group_id: Required since all our queues are FIFO
            message_attributes: Optional message attributes
            message_deduplication_id: Optional for FIFO queues - prevents duplicate messages

        Returns:
            Message ID if successful, None otherwise
        """
        try:
            # Convert ARN to URL format required by boto3
            queue_url = self._convert_arn_to_url(queue_arn)

            # Convert dict to JSON string if needed
            body = json.dumps(message_body) if isinstance(message_body, dict) else message_body

            # temporarily log large messages going to s3
            if (
                self._should_use_extended_client(queue_url)
                and len(body) > INGEST_JOBS_LARGE_PAYLOAD_SIZE
            ):
                logger.info(
                    f"Large ingest message ({len(body)} bytes) will be stored in S3",
                    payload_size=len(body),
                    s3_bucket=self._extended_client_s3_bucket,
                )

            send_params: dict[str, Any] = {
                "QueueUrl": queue_url,
                "MessageBody": body,
                "MessageGroupId": message_group_id,
            }

            if message_attributes:
                send_params["MessageAttributes"] = message_attributes

            # Add deduplication ID - generate one if not provided
            send_params["MessageDeduplicationId"] = message_deduplication_id or str(uuid.uuid4())

            response = await self._send_message_sync(queue_url, send_params)
            message_id = response["MessageId"]

            return message_id

        except Exception as e:
            self.handle_aws_error(e, f"send_message to {queue_arn}")
            return None

    async def send_ingest_webhook_message(
        self,
        webhook_body: str,
        webhook_headers: dict[str, str],
        tenant_id: str,
        source_type: ExternalSource,
        message_group_id: str | None = None,
        message_deduplication_id: str | None = None,
    ) -> str | None:
        """Send webhook message with metadata to the ingest jobs SQS queue.

        Internally, uses extended client for automatic S3 storage of large payloads.

        Args:
            webhook_body: Original webhook body
            webhook_headers: Original webhook headers
            tenant_id: Tenant identifier
            source_type: Source type (github, slack, linear, notion)
            message_group_id: Optional message group ID - ignore to use default lanes settings
            message_deduplication_id: Optional deduplication ID for FIFO queues
        Returns:
            Message ID if successful, None otherwise
        """
        webhook_message = WebhookIngestJobMessage(
            webhook_body=webhook_body,
            webhook_headers=webhook_headers,
            tenant_id=tenant_id,
            source_type=source_type,
            timestamp=str(datetime.utcnow().isoformat()),
        )

        message_attributes = {
            "tenant_id": {"StringValue": tenant_id, "DataType": "String"},
            "source_type": {"StringValue": source_type, "DataType": "String"},
        }

        message_id = await self.send_message(
            queue_arn=INGEST_JOBS_QUEUE_ARN,
            message_body=webhook_message.model_dump_json(),
            message_group_id=message_group_id or get_ingest_lane(webhook_message),
            message_attributes=message_attributes,
            message_deduplication_id=message_deduplication_id,
        )

        if not message_id:
            logger.error(
                "Failed to send ingest webhook message",
                tenant_id=tenant_id,
                source_type=source_type,
            )

        return message_id

    async def send_slackbot_webhook_message(
        self,
        webhook_body: str,
        webhook_headers: dict[str, str],
        tenant_id: str,
        message_deduplication_id: str | None = None,
    ) -> str | None:
        """Send webhook message with metadata to the Slack bot SQS queue.

        Args:
            webhook_body: Original webhook body
            webhook_headers: Original webhook headers
            tenant_id: Tenant identifier
            message_deduplication_id: Optional deduplication ID for FIFO queues (e.g., Slack event_id)

        Returns:
            Message ID if successful, None otherwise
        """
        webhook_message = WebhookIngestJobMessage(
            webhook_body=webhook_body,
            webhook_headers=webhook_headers,
            tenant_id=tenant_id,
            source_type="slack",
            timestamp=str(datetime.utcnow().isoformat()),
        )

        message_attributes = {
            "tenant_id": {"StringValue": tenant_id, "DataType": "String"},
            "source_type": {"StringValue": "slack", "DataType": "String"},
        }

        return await self.send_message(
            queue_arn=SLACK_JOBS_QUEUE_ARN,
            message_body=webhook_message.model_dump_json(),
            message_attributes=message_attributes,
            message_group_id=get_slackbot_lane(webhook_message),
            message_deduplication_id=message_deduplication_id,
        )

    async def send_backfill_ingest_message(
        self,
        backfill_config: BackfillIngestConfig,
        message_deduplication_id: str | None = None,
    ) -> str | None:
        """Send backfill job message to the ingest jobs SQS queue.

        This is the central method for sending backfill jobs to the ingest queue.
        It provides consistent logging and a single point of control for all backfill messages.

        Internally, uses extended client for automatic S3 storage of large payloads.

        Args:
            backfill_config: The backfill configuration message
            message_deduplication_id: Optional deduplication ID for FIFO queues.
                If provided, SQS will deduplicate messages with the same ID within
                a 5-minute window. Useful for cron jobs that may be triggered by
                multiple scheduler instances.

        Returns:
            Message ID if successful, None otherwise
        """
        # Extract source and tenant_id for logging
        source = getattr(backfill_config, "source", "unknown")
        tenant_id = getattr(backfill_config, "tenant_id", "unknown")

        logger.info(
            "Sending backfill job to ingest queue.",
            source=source,
            tenant_id=tenant_id,
        )

        message_attributes = {
            "tenant_id": {"StringValue": str(tenant_id), "DataType": "String"},
            "source": {"StringValue": str(source), "DataType": "String"},
            "message_type": {"StringValue": "backfill", "DataType": "String"},
        }

        message_id = await self.send_message(
            queue_arn=INGEST_JOBS_QUEUE_ARN,
            message_body=backfill_config.model_dump_json(),
            message_group_id=get_ingest_lane(backfill_config),
            message_attributes=message_attributes,
            message_deduplication_id=message_deduplication_id,
        )

        if message_id:
            logger.info(
                f"Successfully queued backfill job "
                f"tenant: {tenant_id}, source: {source}, message_id: {message_id}",
                message_id=message_id,
            )
        else:
            logger.error(
                "Failed to queue backfill job",
                source=source,
                tenant_id=tenant_id,
            )

        return message_id

    async def send_index_message(
        self,
        index_message: IndexJobMessage,
    ) -> str | None:
        """Send index job message to the index jobs SQS queue."""
        return await self.send_message(
            INDEX_JOBS_QUEUE_ARN,
            index_message.model_dump_json(),
            get_index_lane(index_message),
        )

    async def send_delete_message(
        self,
        tenant_id: str,
        document_ids: list[str],
    ) -> str | None:
        """Send delete job message to remove documents from the search index.

        Args:
            tenant_id: Tenant identifier
            document_ids: List of document IDs to delete

        Returns:
            Message ID if successful, None otherwise
        """
        delete_message = DeleteJobMessage(
            tenant_id=tenant_id,
            document_ids=document_ids,
        )

        logger.info(
            "Sending delete job to index queue",
            tenant_id=tenant_id,
            document_count=len(document_ids),
        )

        return await self.send_message(
            INDEX_JOBS_QUEUE_ARN,
            delete_message.model_dump_json(),
            get_delete_lane(delete_message),
        )

    async def send_slack_control_message(
        self,
        tenant_id: str,
        control_type: str = "join_all_channels",
    ) -> str | None:
        """Send control message to the Slack bot SQS queue.

        Args:
            tenant_id: Tenant identifier
            control_type: Type of control operation (default: "join_all_channels")

        Returns:
            Message ID if successful, None otherwise
        """
        control_message = SlackBotControlMessage(
            tenant_id=tenant_id,
            control_type=control_type,  # type: ignore
            timestamp=str(datetime.utcnow().isoformat()),
        )

        message_attributes = {
            "tenant_id": {"StringValue": tenant_id, "DataType": "String"},
            "source_type": {"StringValue": "control", "DataType": "String"},
        }

        return await self.send_message(
            queue_arn=SLACK_JOBS_QUEUE_ARN,
            message_body=control_message.model_dump_json(),
            message_attributes=message_attributes,
            message_group_id=get_slackbot_lane(control_message),
        )

    @run_in_executor
    def _receive_messages_sync(
        self, queue_url: str, receive_params: dict[str, Any]
    ) -> dict[str, Any]:
        """Synchronous helper for receiving SQS messages."""
        client = self._get_client_for_queue_url(queue_url)
        return client.receive_message(**receive_params)

    async def receive_messages(
        self,
        queue_arn: str,
        max_messages: int = 1,
        wait_time_seconds: int = 0,
        visibility_timeout_seconds: int | None = None,
    ) -> list[dict[str, Any]]:
        """Receive messages from SQS queue.

        For ingest queue, uses extended client to automatically retrieve S3 payloads.

        Args:
            queue_arn: SQS queue ARN
            max_messages: Maximum number of messages to receive (1-10)
            wait_time_seconds: Long polling wait time (0-20 seconds)
            visibility_timeout_seconds: How long message is hidden from other consumers

        Returns:
            List of received messages with S3 payloads automatically fetched
        """
        try:
            # Convert ARN to URL format required by boto3
            queue_url = self._convert_arn_to_url(queue_arn)

            receive_params = {
                "QueueUrl": queue_url,
                "MaxNumberOfMessages": min(max(max_messages, 1), 10),
                "WaitTimeSeconds": max(min(wait_time_seconds, 20), 0),
                "MessageAttributeNames": ["All"],
                "AttributeNames": ["MessageGroupId"],
            }

            if visibility_timeout_seconds is not None:
                receive_params["VisibilityTimeout"] = visibility_timeout_seconds

            response = await self._receive_messages_sync(queue_url, receive_params)

            messages = response.get("Messages", [])

            logger.debug(f"Received {len(messages)} messages from queue {queue_arn}")
            return messages

        except Exception as e:
            self.handle_aws_error(e, f"receive_messages from {queue_arn}")
            return []

    @run_in_executor
    def _delete_message_sync(self, queue_url: str, receipt_handle: str) -> None:
        """Synchronous helper for deleting SQS messages."""
        client = self._get_client_for_queue_url(queue_url)
        client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)

    async def delete_message(self, queue_arn: str, receipt_handle: str) -> bool:
        """Delete message from SQS queue.

        For extended client queues, this will also delete the s3 payload object

        Args:
            queue_arn: SQS queue ARN
            receipt_handle: Receipt handle of the message to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert ARN to URL format required by boto3
            queue_url = self._convert_arn_to_url(queue_arn)

            await self._delete_message_sync(queue_url, receipt_handle)

            logger.debug(f"Successfully deleted message from queue {queue_arn}")
            return True

        except Exception as e:
            self.handle_aws_error(e, f"delete_message from {queue_arn}")
            return False

    @run_in_executor
    def _change_message_visibility_sync(
        self, queue_url: str, receipt_handle: str, visibility_timeout: int
    ) -> None:
        """Synchronous helper for changing message visibility."""
        client = self._get_client_for_queue_url(queue_url)
        client.change_message_visibility(
            QueueUrl=queue_url, ReceiptHandle=receipt_handle, VisibilityTimeout=visibility_timeout
        )

    async def change_message_visibility(
        self, queue_arn: str, receipt_handle: str, visibility_timeout: int
    ) -> bool:
        """Change the visibility timeout of a message.

        Args:
            queue_arn: SQS queue ARN
            receipt_handle: Receipt handle of the message
            visibility_timeout: New visibility timeout in seconds (0 to release immediately)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert ARN to URL format required by boto3
            queue_url = self._convert_arn_to_url(queue_arn)

            await self._change_message_visibility_sync(
                queue_url, receipt_handle, visibility_timeout
            )

            logger.debug(
                f"Changed visibility timeout to {visibility_timeout}s for message in queue {queue_arn}"
            )
            return True

        except Exception as e:
            self.handle_aws_error(e, f"change_message_visibility for {queue_arn}")
            return False

    @run_in_executor
    def _get_queue_attributes_sync(
        self, queue_url: str, attribute_names: list[str]
    ) -> dict[str, Any]:
        """Synchronous helper for getting queue attributes."""
        client = self._get_client_for_queue_url(queue_url)
        return client.get_queue_attributes(QueueUrl=queue_url, AttributeNames=attribute_names)

    async def get_queue_attributes(self, queue_arn: str) -> dict[str, Any] | None:
        """Get queue attributes for health checking.

        Args:
            queue_arn: SQS queue ARN

        Returns:
            Queue attributes dict if successful, None otherwise
        """
        try:
            # Convert ARN to URL format required by boto3
            queue_url = self._convert_arn_to_url(queue_arn)

            response = await self._get_queue_attributes_sync(
                queue_url, ["QueueArn", "ApproximateNumberOfMessages"]
            )

            attributes = response.get("Attributes", {})
            logger.debug(f"Retrieved attributes for queue {queue_arn}: {attributes}")
            return attributes

        except Exception as e:
            self.handle_aws_error(e, f"get_queue_attributes for {queue_arn}")
            return None
