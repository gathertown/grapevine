#!/usr/bin/env python
"""
Script to reindex a single document by entity ID.

Sends an IndexJobMessage to the ingest queue for the specified entity.

Example usage:

    # Reindex a specific Gather meeting
    mise reindex --tenant-id abc123 --source gather --entity-id gather_meeting_abc123

    # Reindex a GitHub PR
    mise reindex --tenant-id abc123 --source github_prs --entity-id github_pr_123

    # Dry run (preview what would be sent)
    mise reindex --tenant-id abc123 --source gather --entity-id gather_meeting_abc123 --dry-run

    # Reindex multiple documents at once
    mise reindex --tenant-id abc123 --source slack --entity-id msg1 --entity-id msg2 --entity-id msg3
"""

import argparse
import asyncio
import logging
import sys

from connectors.base.document_source import DocumentSource
from src.clients.sqs import INDEX_JOBS_QUEUE_ARN, SQSClient
from src.jobs.models import IndexJobMessage

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def reindex_document(
    tenant_id: str,
    source: str,
    entity_ids: list[str],
    force_reindex: bool = True,
    turbopuffer_only: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Send an index job message for the specified entity IDs.

    Args:
        tenant_id: Tenant ID
        source: Document source (e.g., 'gather', 'github_prs', 'slack')
        entity_ids: List of entity IDs to reindex
        force_reindex: Force reindexing even if already indexed
        turbopuffer_only: Only reindex in Turbopuffer (skip PostgreSQL/OpenSearch)
        dry_run: If True, print what would be sent without actually sending
    """
    try:
        doc_source = DocumentSource(source)
    except ValueError:
        logger.error(f"Invalid source: {source}")
        logger.info(f"Valid sources: {[s.value for s in DocumentSource]}")
        sys.exit(1)

    logger.info(f"Tenant ID: {tenant_id}")
    logger.info(f"Source: {doc_source.value}")
    logger.info(f"Entity IDs: {entity_ids}")
    logger.info(f"Force reindex: {force_reindex}")
    logger.info(f"Turbopuffer only: {turbopuffer_only}")
    logger.info(f"SQS Queue ARN: {INDEX_JOBS_QUEUE_ARN}")

    message = IndexJobMessage(
        entity_ids=entity_ids,
        source=doc_source,
        tenant_id=tenant_id,
        force_reindex=force_reindex,
        turbopuffer_only=turbopuffer_only,
    )

    if dry_run:
        logger.info("\n[DRY RUN] Would send the following message:")
        logger.info(f"{message.model_dump_json(indent=2)}")
        logger.info("\n[DRY RUN] No message was actually sent.")
        return

    logger.info("\nSending index job message...")
    sqs_client = SQSClient()

    await sqs_client.send_index_message(index_message=message)

    logger.info(f"✅ Successfully sent reindex job for {len(entity_ids)} entity ID(s)")
    logger.info("The document(s) will be reindexed by the index worker.")


def main():
    parser = argparse.ArgumentParser(
        description="Reindex a single document or multiple documents by entity ID",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--tenant-id", required=True, help="Tenant ID")
    parser.add_argument(
        "--source",
        required=True,
        help="Document source (e.g., gather, github_prs, slack, linear, notion)",
    )
    parser.add_argument(
        "--entity-id",
        required=True,
        action="append",
        dest="entity_ids",
        help="Entity ID to reindex (can be specified multiple times)",
    )
    parser.add_argument(
        "--no-force",
        action="store_true",
        help="Don't force reindex (only index if not already indexed)",
    )
    parser.add_argument(
        "--turbopuffer-only",
        action="store_true",
        help="Only reindex in Turbopuffer (skip PostgreSQL/OpenSearch)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the message without actually sending it",
    )

    args = parser.parse_args()

    asyncio.run(
        reindex_document(
            tenant_id=args.tenant_id,
            source=args.source,
            entity_ids=args.entity_ids,
            force_reindex=not args.no_force,
            turbopuffer_only=args.turbopuffer_only,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
