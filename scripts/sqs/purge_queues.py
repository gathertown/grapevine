#!/usr/bin/env python3
"""
Script to purge SQS queues (LOCAL DEVELOPMENT ONLY).

This script is designed to only work with local LocalStack environments
to prevent accidental purging of production/staging queues.

Usage:
    # Show queue information (message counts, etc.)
    python scripts/sqs/purge_queues.py --info

    # Purge specific queue
    python scripts/sqs/purge_queues.py --queue ingest
    python scripts/sqs/purge_queues.py --queue index
    python scripts/sqs/purge_queues.py --queue slack

    # Purge all queues
    python scripts/sqs/purge_queues.py --all

    # Dry run (see what would be purged)
    python scripts/sqs/purge_queues.py --all --dry-run
"""

import argparse
import sys
from pathlib import Path
from typing import Any

# Add project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import boto3

from src.utils.config import get_config_value


def is_local_environment() -> tuple[bool, str]:
    """
    Check if we're in a local development environment.

    Returns:
        tuple: (is_local, reason)
    """
    # Check for LocalStack endpoint
    endpoint_url = get_config_value("AWS_ENDPOINT_URL") or get_config_value("AWS_SQS_ENDPOINT_URL")

    if endpoint_url and (
        "localhost" in endpoint_url
        or "127.0.0.1" in endpoint_url
        or "localstack" in endpoint_url.lower()
    ):
        return True, f"Using local endpoint: {endpoint_url}"

    # Check AWS profile - if it's not set or is explicitly "local", consider it local
    aws_profile = get_config_value("AWS_PROFILE")
    if not aws_profile or aws_profile == "local" or aws_profile == "default":
        # If no endpoint is set and profile suggests non-local, warn
        if not endpoint_url:
            return False, "No AWS endpoint configured - this might target real AWS!"
        return True, "Using default/local profile"

    # If a specific profile is set (like platform-team), consider it non-local
    return False, f"AWS_PROFILE is set to '{aws_profile}' - this appears to be a remote environment"


def get_queue_arns() -> dict[str, str]:
    """Get configured queue ARNs."""
    return {
        "ingest": get_config_value("INGEST_JOBS_QUEUE_ARN") or "corporate-context-ingest-jobs",
        "index": get_config_value("INDEX_JOBS_QUEUE_ARN") or "corporate-context-index-jobs",
        "slack": get_config_value("SLACK_JOBS_QUEUE_ARN") or "corporate-context-slack-jobs",
    }


def arn_to_url(arn: str) -> str:
    """Convert ARN to queue URL."""
    if arn.startswith("https://"):
        return arn

    # ARN format: arn:aws:sqs:<region>:<account-id>:<queue-name>
    parts = arn.split(":")
    if len(parts) >= 6:
        region = parts[3]
        account_id = parts[4]
        queue_name = parts[5]
        return f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"

    # Assume it's just a queue name
    region = get_config_value("AWS_REGION") or "us-east-1"
    account_id = "000000000000"  # LocalStack default
    return f"https://sqs.{region}.amazonaws.com/{account_id}/{arn}"


def get_queue_info(queue_name: str, queue_arn: str) -> dict[str, Any] | None:
    """Get information about a queue."""
    try:
        queue_url = arn_to_url(queue_arn)

        # Create SQS client
        region = get_config_value("AWS_REGION") or "us-east-1"
        endpoint_url = (
            get_config_value("AWS_ENDPOINT_URL")
            or get_config_value("AWS_SQS_ENDPOINT_URL")
            or "http://localhost:4566"  # Default to LocalStack
        )

        sqs_client = boto3.client(
            "sqs",
            region_name=region,
            endpoint_url=endpoint_url,
        )

        # Get queue attributes
        attrs = sqs_client.get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateNumberOfMessagesDelayed",
                "CreatedTimestamp",
                "LastModifiedTimestamp",
                "QueueArn",
                "VisibilityTimeout",
                "MessageRetentionPeriod",
            ],
        )

        return {
            "name": queue_name,
            "url": queue_url,
            "arn": queue_arn,
            "attributes": attrs.get("Attributes", {}),
        }

    except Exception as e:
        print(f"  ✗ Error getting info for {queue_name} queue: {e}")
        return None


def purge_queue(queue_name: str, queue_arn: str, dry_run: bool = False) -> bool:
    """Purge a single queue."""
    try:
        queue_url = arn_to_url(queue_arn)
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Purging {queue_name} queue...")
        print(f"  Queue ARN: {queue_arn}")
        print(f"  Queue URL: {queue_url}")

        if dry_run:
            print("  Would purge queue (dry run mode)")
            return True

        # Create SQS client
        region = get_config_value("AWS_REGION") or "us-east-1"
        endpoint_url = (
            get_config_value("AWS_ENDPOINT_URL")
            or get_config_value("AWS_SQS_ENDPOINT_URL")
            or "http://localhost:4566"  # Default to LocalStack
        )

        sqs_client = boto3.client(
            "sqs",
            region_name=region,
            endpoint_url=endpoint_url,
        )

        # Get queue attributes first to show current message count
        try:
            attrs = sqs_client.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=[
                    "ApproximateNumberOfMessages",
                    "ApproximateNumberOfMessagesNotVisible",
                ],
            )
            visible = attrs["Attributes"].get("ApproximateNumberOfMessages", "0")
            in_flight = attrs["Attributes"].get("ApproximateNumberOfMessagesNotVisible", "0")
            print(f"  Current messages: {visible} visible, {in_flight} in-flight")
        except Exception as e:
            print(f"  Warning: Could not get queue attributes: {e}")

        # Purge the queue
        response = input("  Are you sure you want to purge this queue? [y/N]: ")
        if response.lower() != "y":
            print("  Skipped.")
            return False

        sqs_client.purge_queue(QueueUrl=queue_url)
        print(f"  ✓ Successfully purged {queue_name} queue")
        return True

    except Exception as e:
        print(f"  ✗ Error purging {queue_name} queue: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Purge SQS queues (LOCAL DEVELOPMENT ONLY)",
        epilog="This script only works with local LocalStack to prevent accidental production purges.",
    )
    parser.add_argument(
        "--queue",
        choices=["ingest", "index", "slack"],
        help="Specific queue to purge",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Purge all queues",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be purged without actually purging",
    )
    parser.add_argument(
        "--force-remote",
        action="store_true",
        help="DANGEROUS: Allow running against non-local environments (requires explicit flag)",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Show queue information (message counts, attributes) without purging",
    )

    args = parser.parse_args()

    if not args.queue and not args.all and not args.info:
        parser.error("Must specify either --queue, --all, or --info")

    # Safety check: ensure we're in a local environment
    is_local, reason = is_local_environment()

    print("=" * 60)
    print("SQS Queue Purge Utility - LOCAL DEVELOPMENT ONLY")
    print("=" * 60)
    print(f"\nEnvironment check: {reason}")

    if not is_local:
        print("\n" + "!" * 60)
        print("⚠️  ERROR: This does not appear to be a local environment!")
        print("!" * 60)
        print("\nThis script is designed for LOCAL DEVELOPMENT ONLY.")
        print("It will NOT run against staging or production to prevent")
        print("accidental data loss.")
        print("\nIf you need to purge remote queues:")
        print("  1. Use the AWS CLI directly:")
        print("     aws sqs purge-queue --queue-url <URL> --profile <profile>")
        print("  2. Or use the --force-remote flag (DANGEROUS):")
        print("     python scripts/sqs/purge_queues.py --all --force-remote")
        print("\n")
        sys.exit(1)

    if not is_local and not args.force_remote:
        sys.exit(1)

    if args.force_remote and not is_local:
        print("\n⚠️⚠️⚠️  WARNING: Running against NON-LOCAL environment! ⚠️⚠️⚠️")
        response = input("Type 'I UNDERSTAND THE RISKS' to continue: ")
        if response != "I UNDERSTAND THE RISKS":
            print("Aborted.")
            sys.exit(1)

    queue_arns = get_queue_arns()

    print("\n✓ Running against LOCAL environment (safe)")
    print("=" * 60)

    # Handle --info flag
    if args.info:
        print("\n📊 Queue Information\n")
        for queue_name, queue_arn in queue_arns.items():
            info = get_queue_info(queue_name, queue_arn)
            if info:
                attrs = info["attributes"]
                visible = int(attrs.get("ApproximateNumberOfMessages", 0))
                in_flight = int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
                delayed = int(attrs.get("ApproximateNumberOfMessagesDelayed", 0))
                total_messages = visible + in_flight + delayed

                print(f"\n{queue_name.upper()} Queue:")
                print(f"  Queue ARN: {queue_arn}")
                print(f"  Queue URL: {info['url']}")
                print("  ")
                print("  📨 Messages:")
                print(f"    • Visible (ready):     {visible:,}")
                print(f"    • In-flight (locked):  {in_flight:,}")
                print(f"    • Delayed:             {delayed:,}")
                print(f"    • TOTAL:               {total_messages:,}")
                print("  ")
                print("  ⚙️  Settings:")
                print(f"    • Visibility Timeout:  {attrs.get('VisibilityTimeout', 'N/A')}s")
                print(
                    f"    • Retention Period:    {int(attrs.get('MessageRetentionPeriod', 0)) // 86400} days"
                )

        print("\n" + "=" * 60)
        print("💡 Tip: Use --queue <name> or --all to purge messages")
        print("=" * 60)
        return

    if args.dry_run:
        print("\n⚠️  DRY RUN MODE - No queues will be purged\n")

    success_count = 0
    total_count = 0

    if args.all:
        for queue_name, queue_arn in queue_arns.items():
            total_count += 1
            if purge_queue(queue_name, queue_arn, args.dry_run):
                success_count += 1
    else:
        queue_arn = queue_arns.get(args.queue)
        if queue_arn:
            total_count = 1
            if purge_queue(args.queue, queue_arn, args.dry_run):
                success_count += 1
        else:
            print(f"Error: Queue '{args.queue}' not found in configuration")
            sys.exit(1)

    print("\n" + "=" * 60)
    print(f"Summary: {success_count}/{total_count} queue{'s' if total_count != 1 else ''} purged")
    print("=" * 60)

    if not args.dry_run and success_count > 0:
        print("\n⚠️  Note: Purged messages cannot be recovered!")


if __name__ == "__main__":
    main()
