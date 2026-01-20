"""Trello webhook extractor for processing critical admin lifecycle events.

With the introduction of incremental sync, webhooks are now only used for
critical admin lifecycle events that require immediate attention:
- makeNormalMemberOfOrganization: Admin demoted to normal member
- removeMemberFromOrganization: Admin removed from organization

All other events (card updates, deletions, board discovery) are now handled
by the periodic incremental sync job (TrelloIncrementalSyncExtractor).
"""

import logging
from typing import Any

import asyncpg

from connectors.base import TriggerIndexingCallback
from connectors.trello.trello_action_router import TrelloActionHandler, TrelloActionRouter
from connectors.trello.trello_base import TrelloExtractor
from connectors.trello.trello_models import TrelloWebhookConfig
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


class TrelloWebhookExtractor(TrelloExtractor[TrelloWebhookConfig]):
    """Extractor for processing critical Trello webhook events.

    With incremental sync handling card updates, deletions, and board discovery,
    webhooks are now only used for admin lifecycle events that require immediate
    attention (admin demotion/removal from organization).
    """

    source_name = "trello_webhook"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__(ssm_client, sqs_client)

    async def process_job(
        self,
        job_id: str,
        config: TrelloWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process a Trello webhook ingest job.

        Only processes ADMIN_LIFECYCLE events. All other events are logged
        and skipped since they're handled by incremental sync.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to Trello webhooks
            db_pool: Database connection pool (unused, kept for interface compatibility)
            trigger_indexing: Function to trigger indexing (unused, kept for interface compatibility)

        Raises:
            Exception: If processing fails
        """
        payload = config.body
        action = payload.get("action", {})
        action_type = action.get("type", "")

        logger.info(
            f"Processing Trello webhook job {job_id} for tenant {config.tenant_id} "
            f"(event: {action_type})"
        )

        handler_type = TrelloActionRouter.get_handler(action_type)

        try:
            if handler_type == TrelloActionHandler.ADMIN_LIFECYCLE:
                # Critical event - process immediately
                await self._handle_admin_lifecycle(action, action_type, config.tenant_id)
                logger.info(
                    f"Successfully processed Trello webhook job {job_id} [{handler_type.value}]"
                )
            else:
                # All other events are handled by incremental sync
                logger.debug(
                    f"Skipping webhook event {action_type} [{handler_type.value}] - "
                    f"handled by incremental sync"
                )

        except Exception as e:
            logger.error(f"Trello webhook job {job_id} failed: {e}")
            raise

    async def _handle_admin_lifecycle(
        self,
        action: dict[str, Any],
        action_type: str,
        tenant_id: str,
    ) -> None:
        """Handle CRITICAL admin lifecycle events.

        When admin is demoted or removed from organization, this is the LAST admin-privileged
        action we'll receive. The member webhook will stop receiving events from private boards
        in that organization after this.

        Actions:
        - makeNormalMemberOfOrganization: Admin demoted to normal member
        - removeMemberFromOrganization: Admin removed from organization

        Args:
            action: Trello action data
            action_type: Type of action
            tenant_id: Tenant ID
        """
        try:
            org_data = action.get("data", {}).get("organization", {})
            org_name = org_data.get("name", "Unknown")
            org_id = org_data.get("id", "Unknown")

            member_data = action.get("data", {}).get("member", {})
            member_username = member_data.get("username", "Unknown")

            # Log as critical - this affects data coverage
            logger.critical(
                f"TRELLO ADMIN ACCESS LOST for tenant {tenant_id}: "
                f"Member '{member_username}' lost admin privileges in organization '{org_name}' ({org_id}). "
                f"Event: {action_type}. "
                f"Private boards in this organization may no longer be fully indexed. "
                f"Customer should re-authenticate with an organization admin token to restore full coverage."
            )

            # TODO: Consider sending an alert/notification to the customer
            # This could be done via:
            # - Email notification
            # - Slack notification (if configured)
            # - Admin dashboard alert

        except Exception as e:
            logger.error(f"Failed to handle admin lifecycle event {action_type}: {e}")
