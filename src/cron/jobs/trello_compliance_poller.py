"""Trello GDPR Compliance Poller.

This module polls Trello's compliance API to retrieve user deletion and profile
update records. It must run at least once every 14 days to maintain GDPR compliance.

When user deletions are detected, it anonymizes/removes user data from our system.

https://developer.atlassian.com/cloud/trello/guides/compliance/personal-data-storage-gdpr/
"""

from __future__ import annotations

from datetime import UTC, datetime

import asyncpg

from connectors.trello.trello_models import TrelloApiBackfillRootConfig
from src.clients.sqs import SQSClient
from src.clients.tenant_db import tenant_db_manager
from src.clients.trello import TrelloClient
from src.cron import cron
from src.utils.config import (
    get_trello_power_up_api_key,
    get_trello_power_up_id,
    get_trello_power_up_secret,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Trello GDPR compliance polling configuration
# Per Trello documentation, must poll at least every 14 days
TRELLO_COMPLIANCE_MAX_DAYS = 14  # Maximum days allowed by Trello before non-compliance
TRELLO_COMPLIANCE_POLL_DAYS = (
    TRELLO_COMPLIANCE_MAX_DAYS - 2
)  # Poll every 12 days (2-day safety buffer)
TRELLO_COMPLIANCE_API_LIMIT = 1000  # Maximum records per API call


class TrelloCompliancePoller:
    """Polls Trello compliance API and handles user deletion requests."""

    def __init__(self):
        """Initialize the compliance poller."""
        self.plugin_id = get_trello_power_up_id()
        self.api_key = get_trello_power_up_api_key()
        self.api_secret = get_trello_power_up_secret()

    async def should_poll(self, control_pool: asyncpg.Pool) -> bool:
        """Check if we need to poll the compliance API.

        We should poll if:
        1. We've never polled before
        2. It's been more than 14 days since the last poll
        3. Or as a safety margin, more than 12 days (gives us 2 days buffer)

        Args:
            control_pool: Control database connection pool

        Returns:
            True if we should poll, False otherwise
        """
        async with control_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT last_poll_at
                FROM trello_compliance_tracking
                ORDER BY last_poll_at DESC
                LIMIT 1
                """
            )

            if not row:
                logger.info("No previous Trello compliance poll found, will poll now")
                return True

            last_poll = row["last_poll_at"]
            days_since_poll = (datetime.now(UTC) - last_poll).days

            # Poll every TRELLO_COMPLIANCE_POLL_DAYS (with safety buffer before deadline)
            should_poll = days_since_poll >= TRELLO_COMPLIANCE_POLL_DAYS

            logger.info(
                f"Last Trello compliance poll was {days_since_poll} days ago. "
                f"Should poll: {should_poll} (threshold: {TRELLO_COMPLIANCE_POLL_DAYS} days)"
            )

            return should_poll

    async def get_last_processed_date(self, control_pool: asyncpg.Pool) -> str | None:
        """Get the date of the last processed compliance record.

        Args:
            control_pool: Control database connection pool

        Returns:
            ISO 8601 timestamp string or None if no records processed yet
        """
        async with control_pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT last_processed_record_date
                FROM trello_compliance_tracking
                ORDER BY last_poll_at DESC
                LIMIT 1
                """
            )

            if not row or not row["last_processed_record_date"]:
                return None

            # Convert to ISO 8601 format that Trello expects
            dt = row["last_processed_record_date"]
            return dt.strftime("%Y-%m-%d %H:%M:%SZ")

    async def mark_record_processed(
        self, control_pool: asyncpg.Pool, member_id: str, record_type: str, record_date: datetime
    ) -> None:
        """Mark a compliance record as processed.

        Args:
            control_pool: Control database connection pool
            member_id: Trello member ID
            record_type: Type of record ('memberDelete' or 'memberProfileUpdate')
            record_date: Date of the record
        """
        async with control_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO trello_compliance_records (member_id, record_type, record_date)
                VALUES ($1, $2, $3)
                ON CONFLICT (member_id, record_type, record_date) DO NOTHING
                """,
                member_id,
                record_type,
                record_date,
            )

    async def update_tracking(
        self, control_pool: asyncpg.Pool, records_processed: int, last_record_date: datetime | None
    ) -> None:
        """Update the compliance tracking table after polling.

        Args:
            control_pool: Control database connection pool
            records_processed: Number of records processed in this poll
            last_record_date: Date of the most recent record processed
        """
        async with control_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO trello_compliance_tracking
                    (last_poll_at, last_processed_record_date, records_processed, updated_at)
                VALUES ($1, $2, $3, $4)
                """,
                datetime.now(UTC),
                last_record_date,
                records_processed,
                datetime.now(UTC),
            )

    async def _anonymize_member_personal_data(
        self, member_id: str, tenant_id: str, conn: asyncpg.Connection
    ) -> int:
        """Anonymize all personal data for a member in a single tenant.

        This is a comprehensive cleanup that removes:
        - Member IDs from card assignments (metadata->id_members)
        - Personal data from card_data->members (username, fullName, etc.)
        - Member references in comments (author data + formatted content)
        - Member's specific email from board and card artifacts
        - Any other traces of the member's personal information

        Args:
            member_id: Trello member ID to anonymize
            tenant_id: Tenant ID being processed
            conn: Database connection

        Returns:
            Number of artifacts affected
        """
        total_affected = 0

        # First, extract the member's email from existing artifacts
        # We need this to surgically remove only their email from permission arrays
        member_email_row = await conn.fetchrow(
            """
            SELECT DISTINCT member->>'email' as email
            FROM ingest_artifact,
                 jsonb_array_elements(content->'card_data'->'members') AS member
            WHERE entity = 'trello_card'
            AND member->>'id' = $1
            AND member->>'email' IS NOT NULL
            LIMIT 1
            """,
            member_id,
        )
        member_email = member_email_row["email"] if member_email_row else None

        if member_email:
            logger.debug(
                f"[tenant_id={tenant_id}] Found email {member_email} for member {member_id}"
            )
        else:
            logger.debug(
                f"[tenant_id={tenant_id}] No email found for member {member_id}, "
                f"will skip email removal from permission arrays"
            )

        # 1. Remove member ID from card metadata->id_members array
        result = await conn.execute(
            """
            UPDATE ingest_artifact
            SET
                metadata = jsonb_set(
                    metadata,
                    '{id_members}',
                    COALESCE(
                        (
                            SELECT jsonb_agg(elem)
                            FROM jsonb_array_elements_text(metadata->'id_members') AS elem
                            WHERE elem != $1
                        ),
                        '[]'::jsonb
                    )
                )
            WHERE entity = 'trello_card'
            AND metadata->'id_members' ? $1
            """,
            member_id,
        )
        affected = int(result.split()[-1]) if result else 0
        total_affected += affected
        logger.debug(
            f"[tenant_id={tenant_id}] Removed {member_id} from {affected} card metadata->id_members"
        )

        # 2. Anonymize personal data in content->card_data->members array
        # This removes username, fullName, initials, avatarUrl, etc.
        result = await conn.execute(
            """
            UPDATE ingest_artifact
            SET
                content = jsonb_set(
                    content,
                    '{card_data,members}',
                    COALESCE(
                        (
                            SELECT jsonb_agg(
                                CASE
                                    WHEN member->>'id' = $1
                                    THEN jsonb_build_object(
                                        'id', member->'id',
                                        'username', '[deleted]',
                                        'fullName', '[Deleted User]'
                                    )
                                    ELSE member
                                END
                            )
                            FROM jsonb_array_elements(content->'card_data'->'members') AS member
                        ),
                        '[]'::jsonb
                    )
                )
            WHERE entity = 'trello_card'
            AND content->'card_data'->'members' IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM jsonb_array_elements(content->'card_data'->'members') AS member
                WHERE member->>'id' = $1
            )
            """,
            member_id,
        )
        affected = int(result.split()[-1]) if result else 0
        total_affected += affected
        logger.debug(
            f"[tenant_id={tenant_id}] Anonymized {member_id} in {affected} card_data->members"
        )

        # 3. Anonymize comment author data
        # This handles both the memberCreator object and the formatted content string
        result = await conn.execute(
            """
            UPDATE ingest_artifact
            SET
                content = jsonb_set(
                    content,
                    '{comments}',
                    COALESCE(
                        (
                            SELECT jsonb_agg(
                                CASE
                                    WHEN comment->'memberCreator'->>'id' = $1
                                    THEN comment
                                        || jsonb_build_object(
                                            'memberCreator',
                                            jsonb_build_object(
                                                'id', comment->'memberCreator'->'id',
                                                'username', '[deleted]',
                                                'fullName', '[Deleted User]'
                                            )
                                        )
                                    ELSE comment
                                END
                            )
                            FROM jsonb_array_elements(content->'comments') AS comment
                        ),
                        '[]'::jsonb
                    )
                )
            WHERE entity = 'trello_card'
            AND content->'comments' IS NOT NULL
            AND EXISTS (
                SELECT 1
                FROM jsonb_array_elements(content->'comments') AS comment
                WHERE comment->'memberCreator'->>'id' = $1
            )
            """,
            member_id,
        )
        affected = int(result.split()[-1]) if result else 0
        total_affected += affected
        logger.debug(
            f"[tenant_id={tenant_id}] Anonymized {member_id} in {affected} comment authors"
        )

        # 4. Remove member's specific email from board artifacts
        # Only process if we found the member's email
        if member_email:
            result = await conn.execute(
                """
                UPDATE ingest_artifact
                SET
                    metadata = jsonb_set(
                        metadata,
                        '{member_emails}',
                        COALESCE(
                            (
                                SELECT jsonb_agg(elem)
                                FROM jsonb_array_elements_text(metadata->'member_emails') AS elem
                                WHERE elem != $1
                            ),
                            '[]'::jsonb
                        )
                    )
                WHERE entity = 'trello_board'
                AND metadata->'member_emails' ? $1
                """,
                member_email,
            )
            affected = int(result.split()[-1]) if result else 0
            total_affected += affected
            logger.debug(
                f"[tenant_id={tenant_id}] Removed {member_email} from {affected} board member_emails"
            )

        # 5. Remove member's specific email from card artifacts
        # Cards store board member emails for permission resolution
        if member_email:
            result = await conn.execute(
                """
                UPDATE ingest_artifact
                SET
                    metadata = jsonb_set(
                        metadata,
                        '{board_member_emails}',
                        COALESCE(
                            (
                                SELECT jsonb_agg(elem)
                                FROM jsonb_array_elements_text(metadata->'board_member_emails') AS elem
                                WHERE elem != $1
                            ),
                            '[]'::jsonb
                        )
                    )
                WHERE entity = 'trello_card'
                AND metadata->'board_member_emails' ? $1
                """,
                member_email,
            )
            affected = int(result.split()[-1]) if result else 0
            total_affected += affected
            logger.debug(
                f"[tenant_id={tenant_id}] Removed {member_email} from {affected} card board_member_emails"
            )

        return total_affected

    async def _cleanup_member_data(
        self, member_id: str, record_date: datetime, reason: str
    ) -> None:
        """Cleanup all personal data for a member in the specific tenant(s) where they exist.

        This is used for accountDeleted, tokenRevoked, and tokenExpired events,
        which all require complete removal of the member's personal data.

        Uses the connector_installations table to efficiently target only the tenant(s)
        where this member is connected, instead of checking all tenants.

        Args:
            member_id: Trello member ID to clean up
            record_date: Date of the cleanup request
            reason: Reason for cleanup (e.g., "accountDeleted", "tokenRevoked")
        """
        logger.info(
            f"Processing member data cleanup for Trello member {member_id} "
            f"(reason: {reason}, date: {record_date})"
        )

        # Look up which tenant(s) this member belongs to
        control_pool = await tenant_db_manager.get_control_db()
        async with control_pool.acquire() as conn:
            installation_row = await conn.fetchrow(
                """
                SELECT tenant_id, external_metadata->>'member_username' as member_username, id
                FROM connector_installations
                WHERE type = 'trello' AND external_id = $1 AND status != 'disconnected'
                """,
                member_id,
            )

        if not installation_row:
            logger.warning(
                f"No Trello installation found for member {member_id}. "
                f"Member may not be connected to any tenant, or installation tracking was not in place. "
                f"Skipping cleanup."
            )
            return

        tenant_id = installation_row["tenant_id"]
        member_username = installation_row["member_username"]
        connector_id = installation_row["id"]

        logger.info(
            f"Found Trello installation: member {member_username} ({member_id}) -> tenant {tenant_id}"
        )

        total_affected = 0

        # Process only the specific tenant where this member is connected
        try:
            async with tenant_db_manager.acquire_pool(tenant_id) as tenant_pool:
                async with tenant_pool.acquire() as conn:
                    affected = await self._anonymize_member_personal_data(
                        member_id, tenant_id, conn
                    )
                    total_affected += affected

                logger.info(
                    f"[tenant_id={tenant_id}] Anonymized member {member_id} data "
                    f"({affected} artifacts affected)"
                )

            # Mark the connector as disconnected after successful cleanup
            async with control_pool.acquire() as conn:
                await conn.execute(
                    """UPDATE connector_installations
                       SET status = 'disconnected', updated_at = NOW()
                       WHERE id = $1""",
                    connector_id,
                )
                logger.info(
                    f"Marked Trello connector as disconnected for member {member_id} in control DB"
                )

        except Exception as e:
            logger.error(
                f"[tenant_id={tenant_id}] Error anonymizing member {member_id}: {e}",
                exc_info=True,
            )
            # Re-raise to prevent marking the compliance record as processed
            # This ensures failed GDPR deletion requests will be retried
            raise

        logger.info(
            f"Member cleanup completed for {member_id} (reason: {reason}). "
            f"Anonymized {total_affected} artifacts in tenant {tenant_id}."
        )

    async def handle_member_profile_update(self, member_id: str, record_date: datetime) -> None:
        """Handle a member profile update (GDPR compliance).

        Per GDPR Article 5(1)(d), personal data must be kept accurate and up-to-date.
        When a member updates their profile (username, fullName, avatar), we need to
        refresh all stored data to reflect the changes.

        This triggers a full Trello backfill for the tenant to fetch fresh data from Trello API
        and update all member information.

        Args:
            member_id: Trello member ID
            record_date: Date of the profile update
        """
        logger.info(
            f"Member profile update for Trello member {member_id} (date: {record_date}). "
            f"Triggering full Trello backfill to refresh stale personal data (GDPR compliance)."
        )

        # Look up which tenant(s) this member belongs to
        control_pool = await tenant_db_manager.get_control_db()
        async with control_pool.acquire() as conn:
            installation_row = await conn.fetchrow(
                """
                SELECT tenant_id, external_metadata->>'member_username' as member_username
                FROM connector_installations
                WHERE type = 'trello' AND external_id = $1 AND status != 'disconnected'
                """,
                member_id,
            )

        if not installation_row:
            logger.warning(
                f"No Trello installation found for member {member_id}. "
                f"Cannot trigger backfill for profile update."
            )
            return

        tenant_id = installation_row["tenant_id"]
        member_username = installation_row["member_username"]

        logger.info(
            f"Found Trello installation: member {member_username} ({member_id}) -> tenant {tenant_id}"
        )

        # Trigger full Trello backfill to fetch fresh member data from API
        # This ensures we get the latest profile information (username, fullName, avatar)
        # Force update artifacts even if source_updated_at hasn't changed, since member
        # profile updates don't change card timestamps but we need to refresh member data
        backfill_message = TrelloApiBackfillRootConfig(
            tenant_id=tenant_id,
            suppress_notification=True,
            force_update=True,
        )

        sqs_client = SQSClient()
        message_id = await sqs_client.send_backfill_ingest_message(backfill_message)

        if message_id:
            logger.info(
                f"Successfully triggered Trello backfill for tenant {tenant_id} "
                f"due to member profile update for {member_username} ({member_id}) "
                f"(Message ID: {message_id})"
            )
        else:
            # CRITICAL: Raise exception to prevent marking compliance record as processed
            # This ensures failed GDPR profile updates are retried on next poll
            error_msg = (
                f"Failed to trigger Trello backfill for tenant {tenant_id} "
                f"due to member profile update for {member_username} ({member_id}). "
                f"This violates GDPR Article 5(1)(d) data accuracy requirements."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    async def poll_compliance_api(self) -> None:
        """Poll the Trello compliance API and process records."""
        if not self.plugin_id or not self.api_key or not self.api_secret:
            logger.warning(
                "Trello Power-Up credentials not configured. Skipping compliance polling. "
                "Please set TRELLO_POWER_UP_ID, TRELLO_POWER_UP_API_KEY, and "
                "TRELLO_POWER_UP_API_SECRET environment variables."
            )
            return

        control_pool = await tenant_db_manager.get_control_db()

        # Check if we should poll
        if not await self.should_poll(control_pool):
            logger.info("Trello compliance polling not needed at this time")
            return

        logger.info("Starting Trello GDPR compliance polling")

        # Create a client for compliance API call
        # Compliance API only requires api_key + secret, not token
        client = TrelloClient(api_key=self.api_key)

        # Get the last processed date to avoid reprocessing
        since = await self.get_last_processed_date(control_pool)

        try:
            # Poll the compliance API
            records = client.get_compliance_member_privacy(
                plugin_id=self.plugin_id,
                api_secret=self.api_secret,
                since=since,
                limit=TRELLO_COMPLIANCE_API_LIMIT,
            )

            logger.info(f"Retrieved {len(records)} compliance records from Trello")

            if not records:
                # No new records, but update tracking
                await self.update_tracking(control_pool, 0, None)
                return

            # Process each record
            last_record_date = None
            for record in records:
                member_id = record.get("id")
                record_type = record.get("event")
                date_str = record.get("date")

                if not member_id or not record_type or not date_str:
                    logger.warning(f"Invalid compliance record: {record}")
                    continue

                # Parse the date
                record_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

                # Track the most recent date
                if last_record_date is None or record_date > last_record_date:
                    last_record_date = record_date

                # Check if we've already processed this record
                async with control_pool.acquire() as conn:
                    existing = await conn.fetchrow(
                        """
                        SELECT id FROM trello_compliance_records
                        WHERE member_id = $1 AND record_type = $2 AND record_date = $3
                        """,
                        member_id,
                        record_type,
                        record_date,
                    )

                if existing:
                    logger.debug(
                        f"Skipping already processed record: {member_id} {record_type} {record_date}"
                    )
                    continue

                # Handle the record based on type
                # Per Trello GDPR documentation, we need to handle 4 event types:
                # - accountDeleted: User account was deleted
                # - tokenRevoked: Token was revoked (treat same as deletion)
                # - tokenExpired: Token expired (treat same as deletion)
                # - accountUpdated: User profile was updated
                try:
                    if record_type in (
                        "accountDeleted",
                        "tokenRevoked",
                        "tokenExpired",
                    ):
                        # All these events require complete removal of personal data
                        await self._cleanup_member_data(member_id, record_date, reason=record_type)
                    elif record_type == "accountUpdated":
                        # Profile updates - trigger re-index to refresh stale data
                        await self.handle_member_profile_update(member_id, record_date)
                    else:
                        logger.warning(
                            f"Unknown Trello compliance record type: {record_type}. "
                            f"Known types: accountDeleted, tokenRevoked, tokenExpired, accountUpdated"
                        )

                    # Mark as processed only if handling succeeded
                    await self.mark_record_processed(
                        control_pool, member_id, record_type, record_date
                    )

                except Exception as e:
                    logger.error(
                        f"Failed to process compliance record for member {member_id} "
                        f"(type: {record_type}, date: {record_date}): {e}",
                        exc_info=True,
                    )
                    # Do NOT mark as processed - this record will be retried on next poll
                    logger.warning(
                        f"Compliance record for member {member_id} will be retried on next poll"
                    )
                    continue

            # Update tracking
            await self.update_tracking(control_pool, len(records), last_record_date)

            logger.info(
                f"Trello compliance polling completed successfully. "
                f"Processed {len(records)} records."
            )

        except Exception as e:
            logger.error(f"Error during Trello compliance polling: {e}", exc_info=True)
            raise


# Run every day at 3am UTC to check if we need to poll
# The job will only actually poll if it's been 12+ days since the last poll
@cron(
    id="trello_compliance_poller",
    crontab="0 3 * * *",
    tags=["trello", "compliance", "gdpr"],
)
async def trello_compliance_poller() -> None:
    """Poll Trello compliance API for user deletion requests.

    This job runs daily but only polls Trello if it's been 12+ days since
    the last poll, maintaining a 2-day safety margin before the 14-day deadline.
    """
    logger.info("Running Trello GDPR compliance poller")
    poller = TrelloCompliancePoller()
    await poller.poll_compliance_api()
