#!/usr/bin/env python
"""
Script to redrive messages from the ingest jobs DLQ back to the main queue.

This script receives messages from the dead-letter queue and republishes them
to the main ingest jobs queue, preserving all original message attributes and
handling FIFO queue requirements.

Usage:
    # Dry run to see what would be redriven
    uv run python -m scripts.sqs.redrive_ingest_dlq --dry-run

    # Redrive up to 100 messages
    uv run python -m scripts.sqs.redrive_ingest_dlq --max-messages 100

    # Redrive all messages in batches of 5
    uv run python -m scripts.sqs.redrive_ingest_dlq --batch-size 5

Environment Variables:
    INGEST_JOBS_QUEUE_ARN - Main ingest jobs queue ARN
    INGEST_JOBS_DLQ_ARN   - Ingest jobs dead-letter queue ARN
    AWS_REGION            - AWS region (optional, extracted from ARNs)
    AWS_ENDPOINT_URL      - LocalStack endpoint (optional)
"""

import argparse
import asyncio
import hashlib
import json
import sys

from src.clients.sqs import SQSClient
from src.utils.config import get_config_value
from src.utils.logging import get_logger

logger = get_logger(__name__)


def get_ingest_jobs_queue_arn() -> str:
    """Get the main ingest jobs queue ARN from configuration."""
    arn = get_config_value("INGEST_JOBS_QUEUE_ARN")
    if not arn:
        raise ValueError("INGEST_JOBS_QUEUE_ARN environment variable is required")
    return arn


def get_ingest_jobs_dlq_arn() -> str:
    """Get the ingest jobs DLQ ARN from configuration."""
    arn = get_config_value("INGEST_JOBS_DLQ_ARN")
    if not arn:
        raise ValueError("INGEST_JOBS_DLQ_ARN environment variable is required")
    return arn


async def redrive_messages(
    dry_run: bool = False,
    max_messages: int | None = None,
    batch_size: int = 10,
) -> tuple[int, int]:
    """Redrive messages from DLQ to main queue.

    Args:
        dry_run: If True, only show what would be redriven without actually moving messages
        max_messages: Maximum number of messages to process (None = all)
        batch_size: Number of messages to receive per batch (1-10)

    Returns:
        Tuple of (messages_processed, messages_succeeded)
    """
    main_queue_arn = get_ingest_jobs_queue_arn()
    dlq_arn = get_ingest_jobs_dlq_arn()

    logger.info(
        f"Starting DLQ redrive {'(DRY RUN)' if dry_run else ''}",
        dlq_arn=dlq_arn,
        main_queue_arn=main_queue_arn,
        max_messages=max_messages,
        batch_size=batch_size,
    )

    sqs_client = SQSClient(use_session_token=True)
    messages_processed = 0
    messages_succeeded = 0

    while True:
        # Check if we've hit the max_messages limit
        if max_messages is not None and messages_processed >= max_messages:
            logger.info(f"Reached max_messages limit of {max_messages}")
            break

        # Calculate how many messages to receive in this batch
        remaining = None
        if max_messages is not None:
            remaining = max_messages - messages_processed
            batch_size = min(batch_size, remaining)

        # Receive messages from DLQ
        messages = await sqs_client.receive_messages(
            queue_arn=dlq_arn,
            max_messages=batch_size,
            wait_time_seconds=5,  # Short poll to avoid long waits on empty queue
        )

        if not messages:
            logger.info("No more messages in DLQ")
            break

        logger.info(f"Received {len(messages)} messages from DLQ")

        # Process each message
        for message in messages:
            messages_processed += 1
            receipt_handle = message["ReceiptHandle"]
            body = message["Body"]
            attributes = message.get("Attributes", {})
            message_attributes = message.get("MessageAttributes", {})

            # Extract original MessageGroupId if available
            message_group_id = attributes.get("MessageGroupId")

            try:
                # Parse message body to extract tenant_id for logging
                parsed_body = json.loads(body)
                tenant_id = parsed_body.get("tenant_id", "unknown")
                message_type = parsed_body.get("message_type", "unknown")
                source = parsed_body.get("source_type") or parsed_body.get("source", "unknown")

                logger.info(
                    f"Processing message {messages_processed}",
                    tenant_id=tenant_id,
                    message_type=message_type,
                    source=source,
                    message_group_id=message_group_id,
                )

                if dry_run:
                    logger.info(
                        "[DRY RUN] Would redrive message",
                        tenant_id=tenant_id,
                        message_type=message_type,
                        source=source,
                    )
                    messages_succeeded += 1
                    continue

                # Generate deduplication ID from message body hash for idempotency
                # This ensures redriving the same message multiple times won't cause duplicates
                dedup_id = hashlib.sha256(body.encode()).hexdigest()

                # Send message to main queue
                message_id = await sqs_client.send_message(
                    queue_arn=main_queue_arn,
                    message_body=body,
                    message_group_id=message_group_id or "redrive_default",
                    message_attributes=message_attributes,
                    message_deduplication_id=dedup_id,
                )

                if message_id:
                    # Successfully sent to main queue, delete from DLQ
                    deleted = await sqs_client.delete_message(dlq_arn, receipt_handle)
                    if deleted:
                        messages_succeeded += 1
                        logger.info(
                            f"Successfully redriven message {messages_processed}",
                            message_id=message_id,
                            tenant_id=tenant_id,
                        )
                    else:
                        logger.error(
                            f"Failed to delete message {messages_processed} from DLQ after successful send",
                            tenant_id=tenant_id,
                        )
                else:
                    logger.error(
                        f"Failed to send message {messages_processed} to main queue",
                        tenant_id=tenant_id,
                    )

            except json.JSONDecodeError:
                logger.error(f"Failed to parse message {messages_processed} body as JSON")
            except Exception as e:
                logger.error(
                    f"Error processing message {messages_processed}",
                    error=str(e),
                    exc_info=True,
                )

    return messages_processed, messages_succeeded


async def main() -> int:
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description="Redrive messages from ingest jobs DLQ to main queue",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be redriven without actually moving messages",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=None,
        help="Maximum number of messages to process (default: all)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of messages to receive per batch (1-10, default: 10)",
    )

    args = parser.parse_args()

    # Validate batch_size
    if not 1 <= args.batch_size <= 10:
        logger.error("batch-size must be between 1 and 10")
        return 1

    try:
        # Check required environment variables
        get_ingest_jobs_queue_arn()
        get_ingest_jobs_dlq_arn()

        messages_processed, messages_succeeded = await redrive_messages(
            dry_run=args.dry_run,
            max_messages=args.max_messages,
            batch_size=args.batch_size,
        )

        logger.info(
            f"Redrive complete {'(DRY RUN)' if args.dry_run else ''}",
            messages_processed=messages_processed,
            messages_succeeded=messages_succeeded,
            messages_failed=messages_processed - messages_succeeded,
        )

        return 0 if messages_succeeded == messages_processed else 1

    except ValueError as e:
        logger.error(str(e))
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 130
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
