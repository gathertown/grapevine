#!/usr/bin/env python
"""
Script to send full reindex jobs for all tenant-source combinations.

Connects to the control database, looks up all provisioned tenants, and sends
ReindexJobMessage to the ingest queue for each tenant-source combination.

Example usage:

    # Dry run sending reindex messages to production (CAREFUL!)
    uv run python -m scripts.send_full_reindex_all_tenants --dry-run
"""

import argparse
import asyncio
import logging
import sys

from connectors.base.document_source import DocumentSource
from src.clients.sqs import INGEST_JOBS_QUEUE_ARN, SQSClient
from src.clients.tenant_db import tenant_db_manager
from src.jobs.lanes import get_ingest_lane
from src.jobs.models import ReindexJobMessage

# ------------------- CONFIG -------------------
# Sources that have configured entity types (from FullReindexExtractor)
ACTIVE_SOURCES = [
    DocumentSource.SLACK,
    DocumentSource.GITHUB_PRS,
    DocumentSource.GITHUB_CODE,
    DocumentSource.NOTION,
    DocumentSource.LINEAR,
    DocumentSource.GOOGLE_DRIVE,
    DocumentSource.HUBSPOT_DEAL,
    DocumentSource.HUBSPOT_COMPANY,
]

# Should we _only_ reindex turbopuffer?
TURBOPUFFER_ONLY = True
# ------------------- END CONFIG -------------------


async def get_provisioned_tenants() -> list[str]:
    """Get all provisioned tenant IDs from the control database."""
    print("Fetching provisioned tenants from control database")

    control_pool = await tenant_db_manager.get_control_db()
    async with control_pool.acquire() as conn:
        rows = await conn.fetch("SELECT id FROM public.tenants WHERE state = 'provisioned'")
        tenant_ids = [row["id"] for row in rows]

    print(f"Found {len(tenant_ids)} provisioned tenants")
    return tenant_ids


async def send_reindex_messages(tenant_ids: list[str], dry_run: bool = False) -> None:
    """Send reindex messages for all tenant-source combinations."""
    if not tenant_ids:
        print("No tenants found, nothing to do")
        return

    print(f"Using ingest jobs queue ARN: {INGEST_JOBS_QUEUE_ARN}")

    sqs_client = SQSClient(use_session_token=True)
    total_messages = len(tenant_ids) * len(ACTIVE_SOURCES)
    sent_count = 0
    failed_count = 0

    print(
        f"{'[DRY RUN] ' if dry_run else ''}Sending reindex messages (turbopuffer_only={TURBOPUFFER_ONLY}) for {total_messages} tenant-source combinations"
    )
    print(f"Tenants: {len(tenant_ids)}")
    print(f"Active sources: {[source.value for source in ACTIVE_SOURCES]}")

    for tenant_id in tenant_ids:
        print(f"Processing tenant: {tenant_id}")

        for source in ACTIVE_SOURCES:
            if dry_run:
                print(f"  [DRY RUN] Would send reindex message for {tenant_id} - {source.value}")
                sent_count += 1
                continue

            # Create reindex job message
            reindex_message = ReindexJobMessage(
                tenant_id=tenant_id,
                source=source,
                turbopuffer_only=TURBOPUFFER_ONLY,
            )

            # Send to ingest queue via SQS client's send_message method
            try:
                message_id = await sqs_client.send_message(
                    queue_arn=INGEST_JOBS_QUEUE_ARN,
                    message_body=reindex_message.model_dump_json(),
                    message_group_id=get_ingest_lane(reindex_message),
                    message_attributes={
                        "tenant_id": {"StringValue": tenant_id, "DataType": "String"},
                        "source": {"StringValue": source.value, "DataType": "String"},
                        "message_type": {"StringValue": "reindex", "DataType": "String"},
                    },
                )

                if message_id:
                    print(
                        f"  ✅ Sent reindex message for {tenant_id} - {source.value} (Message ID: {message_id})"
                    )
                    sent_count += 1
                else:
                    print(f"  ❌ Failed to send reindex message for {tenant_id} - {source.value}")
                    failed_count += 1

            except Exception as e:
                print(f"  ❌ Error sending reindex message for {tenant_id} - {source.value}: {e}")
                failed_count += 1

    # Summary
    print(f"{'[DRY RUN] ' if dry_run else ''}Reindex job summary:")
    print(f"  Total tenant-source combinations: {total_messages}")
    print(f"  {'Would send' if dry_run else 'Successfully sent'}: {sent_count}")
    if not dry_run and failed_count > 0:
        print(f"  Failed: {failed_count}")

    if not dry_run and failed_count > 0:
        sys.exit(1)


def check_environment() -> None:
    """Check that required environment variables are set."""
    import os

    required_vars = [
        "CONTROL_DATABASE_URL",
        "INGEST_JOBS_QUEUE_ARN",
    ]

    missing_vars = []
    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)

    if missing_vars:
        print("Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        sys.exit(1)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Send full reindex jobs for all tenant-source combinations",
        epilog="""
Environment Variables Required:
  CONTROL_DATABASE_URL    - PostgreSQL URL for control database
  INGEST_JOBS_QUEUE_ARN   - SQS queue ARN for ingest jobs

AWS credentials also required (via AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or IAM role)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview actions without sending messages"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Check environment
    check_environment()

    try:
        # Get all provisioned tenants
        tenant_ids = await get_provisioned_tenants()

        # Send reindex messages
        await send_reindex_messages(tenant_ids, dry_run=args.dry_run)

        if args.dry_run:
            print("Dry run completed successfully")
        else:
            print("All reindex messages sent successfully")

    except KeyboardInterrupt:
        print("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"Script failed: {e}")
        sys.exit(1)
    finally:
        # Clean up database connections
        await tenant_db_manager.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
