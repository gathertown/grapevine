import logging
from typing import Any

import asyncpg
from pydantic import BaseModel

from connectors.base import BaseIngestArtifact, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.linear.linear_base import LinearExtractor
from connectors.linear.linear_helpers import get_user_display_name, is_system_activity
from connectors.linear.linear_pruner import linear_pruner

logger = logging.getLogger(__name__)


class LinearWebhookConfig(BaseModel):
    body: dict[str, Any]
    tenant_id: str


class LinearWebhookExtractor(LinearExtractor[LinearWebhookConfig]):
    """Extractor for processing Linear webhook events."""

    source_name = "linear_webhook"

    async def process_job(
        self,
        job_id: str,
        config: LinearWebhookConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a Linear webhook ingest job.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to Linear webhooks
            db_pool: Database connection pool

        Raises:
            Exception: If processing fails
        """
        payload = config.body

        action = payload.get("action", "")
        event_type = payload.get("type", "")
        logger.info(
            f"Processing Linear webhook job {job_id} for tenant {config.tenant_id} "
            f"(event: {event_type} - {action})"
        )

        artifacts: list[BaseIngestArtifact] = []

        if event_type == "Issue":
            artifacts = await self._handle_issue_event(
                payload, action, job_id, db_pool, config.tenant_id
            )
        elif event_type == "Comment":
            artifacts = await self._handle_comment_event(
                payload, action, job_id, db_pool, config.tenant_id
            )
        elif event_type == "IssueLabel":
            artifacts = await self._handle_issue_label_event(
                payload, action, job_id, db_pool, config.tenant_id
            )
        else:
            logger.info(f"Ignoring unsupported Linear event type: {event_type}")

        # Store all artifacts
        if artifacts:
            await self.store_artifacts_batch(db_pool, artifacts)

            # Trigger indexing for all affected issues
            issue_ids = [artifact.entity_id for artifact in artifacts]
            await trigger_indexing(issue_ids, DocumentSource.LINEAR, config.tenant_id)

        logger.info(
            f"Successfully processed Linear webhook job {job_id}, created {len(artifacts)} artifacts"
        )

    async def _handle_issue_event(
        self,
        payload: dict[str, Any],
        action: str,
        job_id: str,
        db_pool: asyncpg.Pool,
        tenant_id: str,
    ) -> list[BaseIngestArtifact]:
        """Handle Linear issue events (created, updated, etc.)."""
        data = payload.get("data", {})
        if not data:
            return []

        issue_id = data.get("id", "")
        if not issue_id:
            return []

        # Handle issue removals via pruner
        if action == "remove":
            try:
                logger.info(f"Pruning Linear issue {issue_id}")
                await linear_pruner.delete_issue(issue_id, tenant_id, db_pool)
            except Exception as e:
                logger.error(f"Failed pruning Linear issue {issue_id}: {e}")
            # No artifacts to return on deletion
            return []

        logger.info(f"Processing Linear issue {action} event for issue {issue_id}")

        linear_client = await self.get_linear_client(tenant_id, db_pool)
        issue_data = linear_client.get_issue_by_id(issue_id)
        if not issue_data:
            logger.warning(f"Could not fetch issue data for issue {issue_id}")
            return []

        team_data = issue_data.get("team", {})
        if team_data and team_data.get("private", False):
            logger.info(
                f"Skipping issue {issue_id} from private team {team_data.get('name', 'Unknown')}"
            )
            return []

        # Process the issue using shared base class method
        artifact = await self._process_issue(job_id, issue_data, tenant_id, db_pool)
        return [artifact]

    async def _handle_comment_event(
        self,
        payload: dict[str, Any],
        action: str,
        job_id: str,
        db_pool: asyncpg.Pool,
        tenant_id: str,
    ) -> list[BaseIngestArtifact]:
        """Handle Linear comment events."""
        data = payload.get("data", {})
        if not data:
            return []

        issue_id = data.get("issueId")
        if not issue_id and "issue" in data:
            issue_id = data["issue"].get("id")

        if not issue_id:
            logger.warning(f"No issue ID found in comment event data: {data}")
            return []

        logger.info(f"Processing Linear comment {action} event for issue {issue_id}")

        # Filter out system comments
        user = data.get("user", {})
        user_name = get_user_display_name(user)
        user_id = user.get("id", "")

        if is_system_activity(user_name, user_id):
            logger.debug(f"Filtering out system comment from {user_name}")
            return []

        # Fetch fresh issue data from API to get complete current state
        linear_client = await self.get_linear_client(tenant_id, db_pool)
        issue_data = linear_client.get_issue_by_id(issue_id)
        if not issue_data:
            logger.warning(f"Could not fetch issue data for issue {issue_id}")
            return []

        # Check if the issue belongs to a private team
        team_data = issue_data.get("team", {})
        if team_data and team_data.get("private", False):
            logger.info(
                f"Skipping comment on issue {issue_id} from private team {team_data.get('name', 'Unknown')}"
            )
            return []

        # Process the issue using shared base class method
        artifact = await self._process_issue(job_id, issue_data, tenant_id, db_pool)
        return [artifact]

    async def _handle_issue_label_event(
        self,
        payload: dict[str, Any],
        action: str,
        job_id: str,
        db_pool: asyncpg.Pool,
        tenant_id: str,
    ) -> list[BaseIngestArtifact]:
        """Handle Linear issue label events."""
        data = payload.get("data", {})
        if not data:
            return []

        issue_id = data.get("issueId") or data.get("issue", {}).get("id")

        if not issue_id:
            return []

        logger.info(f"Processing Linear label {action} event for issue {issue_id}")

        # Delegate to issue handler since labels affect the issue
        # Always use `update` actions for label changes, since they don't map to issue creates or deletes
        mock_payload = {"data": {"id": issue_id}, "action": "update", "type": "Issue"}
        return await self._handle_issue_event(mock_payload, action, job_id, db_pool, tenant_id)
