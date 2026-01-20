"""
Shared SQS job processing framework.

Provides a generic processor that polls SQS queues and executes provided processing functions.
"""

import asyncio
import json
import logging
import random
import signal
import traceback
from collections.abc import Awaitable, Callable
from typing import Any, TypedDict, cast

import newrelic.agent

from src.clients.sqs import SQSClient
from src.jobs.exceptions import ExtendVisibilityException
from src.utils.error_handling import extract_first_exception

logger = logging.getLogger(__name__)


class SQSMessageMetadata(TypedDict):
    """Metadata extracted from SQS messages."""

    message_id: str | None
    receipt_handle: str | None
    approximate_receive_count: str | None


class SQSJobProcessor:
    """Generic SQS job processor that handles polling and message processing."""

    def __init__(
        self,
        queue_arn: str,
        process_function: Callable[[dict[str, Any], SQSMessageMetadata], Awaitable[None]],
        max_messages: int = 1,
        wait_time_seconds: int = 20,
        visibility_timeout_seconds: int = 300,
        sqs_client: SQSClient | None = None,
    ):
        """Initialize SQS job processor.

        Args:
            queue_arn: ARN of the SQS queue to poll
            process_function: Async function to process each message (message_data, sqs_metadata)
            max_messages: Maximum messages to receive per poll (1-10)
            wait_time_seconds: Long polling wait time (0-20 seconds)
            visibility_timeout_seconds: How long message is hidden from other consumers
            sqs_client: Optional SQS client to use. If None, creates a new one.
        """
        self.queue_arn = queue_arn
        self.process_function = process_function
        self.max_messages = max_messages
        self.wait_time_seconds = wait_time_seconds
        self.visibility_timeout_seconds = visibility_timeout_seconds

        self.sqs_client = sqs_client or SQSClient()
        self.running = False
        self.shutdown_event = asyncio.Event()
        # Track messages currently being processed: receipt_handle -> message
        self.in_progress_messages: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum: int, _frame: Any) -> None:
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    async def process_message(self, message: dict[str, Any]) -> bool:
        """Process a single SQS message.

        Args:
            message: SQS message dictionary

        Returns:
            True if the message should be deleted, False otherwise
        """
        receipt_handle = message.get("ReceiptHandle")
        if not receipt_handle:
            logger.warning("Message missing ReceiptHandle")
            return False

        # Parse message body
        body = message.get("Body", "")
        if not body:
            logger.warning("Received empty message body")
            return False

        # Parse JSON body
        try:
            message_data = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message body as JSON: {e}")
            return True  # delete this malformed message

        # Create SQS metadata for processing
        sqs_metadata: SQSMessageMetadata = {
            "message_id": message.get("MessageId"),
            "receipt_handle": receipt_handle,
            "approximate_receive_count": message.get("Attributes", {}).get(
                "ApproximateReceiveCount"
            ),
        }

        try:
            # Process the message with separate metadata argument
            await self.process_function(message_data, sqs_metadata)
            return True  # message should be deleted on success

        except* ExtendVisibilityException as e_group:
            # If triggers there gonna be an ExtendVisibilityException, cast the None away
            ext_viz_exception = extract_first_exception(e_group, ExtendVisibilityException)
            ext_viz_exception = cast(ExtendVisibilityException, ext_viz_exception)
            visibility_timeout_seconds = ext_viz_exception.visibility_timeout_seconds

            # Extend the visibility timeout as requested
            logger.info(
                f"Extending message visibility timeout by {visibility_timeout_seconds} seconds: {ext_viz_exception}"
            )

            visibility_extended = await self.sqs_client.change_message_visibility(
                self.queue_arn, receipt_handle, visibility_timeout_seconds
            )

            if visibility_extended:
                logger.info(
                    f"Successfully extended visibility timeout to {visibility_timeout_seconds} seconds"
                )
            else:
                logger.error("Failed to extend message visibility timeout")

        except* Exception:
            # Record the error in New Relic
            newrelic.agent.record_exception()
            error_message = traceback.format_exc()
            logger.error(f"Error processing message: {error_message}")

        # Return False regardless to prevent msg deletion
        return False

    async def poll_and_process(self) -> None:
        """Main polling loop that receives and processes messages."""
        logger.info(f"Starting SQS job processor for queue: {self.queue_arn}")
        self.running = True

        # Local cache for short-polled messages within this loop
        short_polled_messages: list[dict[str, Any]] = []

        while self.running and not self.shutdown_event.is_set():
            try:
                # Use cached messages from previous short poll if available
                if short_polled_messages:
                    # Note: these messages are already tracked in in_progress_messages from when we cached them
                    messages = short_polled_messages
                    short_polled_messages = []
                else:
                    # Apply short random jitter before next poll to smooth out recvs across the worker fleet over time
                    # This can help avoid group locality (repeatedly receiving messages from the same group)
                    await asyncio.sleep(random.uniform(0, 0.15))

                    # Long poll queue for messages
                    messages = await self.receive_and_track_messages()

                logger.info(
                    f"Received {len(messages)} messages from queue {self.queue_arn} with groupIds: {', '.join([message.get('Attributes', {}).get('MessageGroupId', 'N/A') for message in messages])}"
                )

                if not messages:
                    continue

                # Process each message
                for message in messages:
                    receipt_handle: str | None = message.get("ReceiptHandle")
                    if not receipt_handle:
                        logger.warning("Message missing ReceiptHandle, skipping")
                        continue

                    # Check if we should stop processing new messages
                    if self.shutdown_event.is_set():
                        logger.info("Shutdown in progress, not processing new messages")
                        break

                    try:
                        should_delete = await self.process_message(message)

                        if should_delete:
                            # Short poll to pre-fetch next batch before deleting current message
                            # to guarantee we don't get the same messageGroupId again if there are
                            # other group IDs available. This helps with ingest lane fairness, see AIVP-347
                            if not short_polled_messages and not self.shutdown_event.is_set():
                                try:
                                    short_polled_messages = await self.receive_and_track_messages(
                                        wait_time_seconds=1,  # Short poll
                                    )
                                    logger.info(
                                        f"Pre-fetched {len(short_polled_messages)} message(s) via short poll"
                                    )
                                except Exception as e:
                                    logger.error(
                                        f"Short poll failed, will continue with regular polling: {e}"
                                    )

                            # Delete message from queue on successful processing
                            deleted = await self.sqs_client.delete_message(
                                self.queue_arn, receipt_handle
                            )
                            if not deleted:
                                logger.error("Failed to delete processed message")

                    except* asyncio.CancelledError:
                        logger.info(
                            f"Message processing cancelled for receipt handle: {receipt_handle[:20]}..."
                        )
                        # Re-raise to properly handle cancellation
                        raise
                    except* Exception:
                        error_message = traceback.format_exc()
                        logger.error(f"Error processing message polling: {error_message}")
                    finally:
                        # Remove from in-progress tracking
                        async with self._lock:
                            self.in_progress_messages.pop(receipt_handle, None)

            except* Exception:
                error_message = traceback.format_exc()
                logger.error(f"Error in polling loop: {error_message}")

        logger.info("SQS job processor stopped")

    async def start(self) -> None:
        """Start the job processor with signal handling."""
        self.setup_signal_handlers()

        try:
            await self.poll_and_process()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            await self.shutdown()

    async def receive_and_track_messages(
        self, wait_time_seconds: int | None = None
    ) -> list[dict[str, Any]]:
        """Receive messages and track them as in-progress."""
        # We technically have a race condition risk here where the recv could succeed but the track fails,
        # but it should be very rare in practice
        messages = await self.sqs_client.receive_messages(
            queue_arn=self.queue_arn,
            max_messages=self.max_messages,
            wait_time_seconds=wait_time_seconds
            if wait_time_seconds is not None
            else self.wait_time_seconds,
            visibility_timeout_seconds=self.visibility_timeout_seconds,
        )
        await self._track_in_progress_messages(messages)
        return messages

    async def _track_in_progress_messages(self, messages: list[dict[str, Any]]) -> None:
        async with self._lock:
            for message in messages:
                handle = message.get("ReceiptHandle")
                if handle:
                    self.in_progress_messages[handle] = message
                else:
                    logger.warning(f"Message missing ReceiptHandle, skipping: {message}")

    async def release_in_progress_messages(self) -> None:
        """Release all in-progress messages back to the queue."""
        async with self._lock:
            if not self.in_progress_messages:
                logger.info("No in-progress messages to release")
                return

            logger.info(
                f"Releasing {len(self.in_progress_messages)} in-progress messages back to queue"
            )

            # Release messages back to queue by setting visibility timeout to 0
            for receipt_handle in list(self.in_progress_messages.keys()):
                try:
                    released = await self.sqs_client.change_message_visibility(
                        self.queue_arn, receipt_handle, visibility_timeout=0
                    )
                    if released:
                        logger.info(
                            f"Released message with receipt handle: {receipt_handle[:20]}..."
                        )
                    else:
                        logger.warning(
                            f"Failed to release message with receipt handle: {receipt_handle[:20]}..."
                        )
                except Exception as e:
                    logger.error(f"Error releasing message: {e}")

            # Clear the tracking dict
            self.in_progress_messages.clear()

    async def shutdown(self) -> None:
        """Gracefully shutdown the processor."""
        logger.info("Shutting down SQS job processor...")
        self.running = False
        self.shutdown_event.set()

        # Release all in-progress messages back to the queue
        await self.release_in_progress_messages()
