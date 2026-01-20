import logging
from typing import Any

import asyncpg

from connectors.base import BaseIngestArtifact, TriggerIndexingCallback
from connectors.base.document_source import DocumentSource
from connectors.jira.jira_base import JiraExtractor
from connectors.jira.jira_models import JiraWebhookConfig
from connectors.jira.jira_pruner import jira_pruner
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


class JiraWebhookExtractor(JiraExtractor[JiraWebhookConfig]):
    """Extractor for processing Jira webhook events from Atlassian Forge."""

    source_name = "jira_webhook"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__(ssm_client, sqs_client)

    async def process_job(
        self,
        job_id: str,
        config,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """
        Process a Jira webhook ingest job.

        Args:
            job_id: The ingest job ID
            config: Job configuration specific to Jira webhooks
            db_pool: Database connection pool
            trigger_indexing: Function to trigger indexing

        Raises:
            Exception: If processing fails
        """

        payload = config.body
        event_type = payload.get("eventType")

        logger.info(
            f"Processing Jira webhook job {job_id} for tenant {config.tenant_id} "
            f"(event: {event_type})"
        )

        artifacts: list[BaseIngestArtifact] = []

        try:
            if event_type == "avi:jira:created:issue":
                artifacts = await self._handle_issue_created(payload, job_id, config.tenant_id)
            elif event_type == "avi:jira:updated:issue":
                artifacts = await self._handle_issue_updated(payload, job_id, config.tenant_id)
            elif event_type == "avi:jira:deleted:issue":
                await self._handle_issue_deleted(payload, job_id, config.tenant_id, db_pool)
            elif event_type == "avi:jira:commented:issue":
                artifacts = await self._handle_issue_commented(payload, job_id, config.tenant_id)
            elif event_type == "avi:jira:deleted:comment":
                artifacts = await self._handle_comment_deleted(payload, job_id, config.tenant_id)
            else:
                logger.info(f"Ignoring unsupported Jira event type: {event_type}")

            # Store all artifacts
            if artifacts:
                await self.store_artifacts_batch(db_pool, artifacts)

                issue_keys = [
                    artifact.entity_id for artifact in artifacts if artifact.entity == "jira_issue"
                ]
                if issue_keys:
                    await trigger_indexing(issue_keys, DocumentSource.JIRA, config.tenant_id)

            logger.info(
                f"Successfully processed Jira webhook job {job_id}, created {len(artifacts)} artifacts"
            )

        except Exception as e:
            logger.error(f"Jira webhook job {job_id} failed: {e}")
            raise

    async def _handle_issue_created(
        self,
        payload: dict[str, Any],
        job_id: str,
        tenant_id: str,
    ) -> list[BaseIngestArtifact]:
        """Handle avi:jira:created:issue events."""
        return await self._handle_issue_event(payload, "created", job_id, tenant_id)

    async def _handle_issue_updated(
        self,
        payload: dict[str, Any],
        job_id: str,
        tenant_id: str,
    ) -> list[BaseIngestArtifact]:
        """Handle avi:jira:updated:issue events."""
        return await self._handle_issue_event(payload, "updated", job_id, tenant_id)

    async def _handle_issue_event(
        self,
        payload: dict[str, Any],
        action: str,
        job_id: str,
        tenant_id: str,
    ) -> list[BaseIngestArtifact]:
        """Handle Jira issue events (created, updated)."""
        try:
            issue_obj = payload.get("issue", {})
            issue_key = issue_obj.get("key")
            issue_id = issue_obj.get("id")

            if not issue_key or not issue_id:
                logger.warning(f"Missing issue key or ID in {action} event payload")
                return []

            logger.info(
                f"Processing Jira issue {action} event for issue {issue_key} (ID: {issue_id})"
            )

            jira_client = await self.get_jira_client(tenant_id)
            issue_data = jira_client.get_issue(issue_key)
            if not issue_data:
                logger.warning(f"Could not fetch issue data for issue {issue_key}")
                return []

            artifacts = await self._process_issue(job_id, issue_data, tenant_id)
            return list(artifacts)

        except Exception as e:
            logger.error(f"Failed to handle Jira issue {action} event: {e}")
            return []

    async def _handle_issue_deleted(
        self,
        payload: dict[str, Any],
        job_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
    ) -> None:
        """Handle avi:jira:deleted:issue events."""
        try:
            # Extract issue key and ID from webhook payload
            issue_obj = payload.get("issue", {})
            issue_key = issue_obj.get("key")
            issue_id = issue_obj.get("id")

            if not issue_key or not issue_id:
                logger.warning("Missing issue key or ID in delete event payload")
                return

            logger.info(f"Processing Jira issue deletion for issue {issue_key} (ID: {issue_id})")

            # Use the pruner to delete the issue from all data stores
            success = await jira_pruner.delete_issue(issue_id, tenant_id, db_pool)
            if success:
                logger.info(f"Successfully deleted Jira issue {issue_key}")
            else:
                logger.warning(f"Failed to delete Jira issue {issue_key}")

        except Exception as e:
            logger.error(f"Failed to handle Jira issue deletion: {e}")
            raise

    async def _handle_issue_commented(
        self,
        payload: dict[str, Any],
        job_id: str,
        tenant_id: str,
    ) -> list[BaseIngestArtifact]:
        """Handle avi:jira:commented:issue events."""
        try:
            # Extract issue key and ID from webhook payload
            issue_obj = payload.get("issue", {})
            issue_key = issue_obj.get("key")
            issue_id = issue_obj.get("id")

            if not issue_key or not issue_id:
                logger.warning("Missing issue key or ID in comment event payload")
                return []

            logger.info(f"Processing Jira comment event for issue {issue_key} (ID: {issue_id})")

            # Fetch fresh issue data from API to get complete current state with new comment
            jira_client = await self.get_jira_client(tenant_id)
            issue_data = jira_client.get_issue(issue_key)
            if not issue_data:
                logger.warning(f"Could not fetch issue data for issue {issue_key}")
                return []

            # Process the issue using shared base class method
            # This will capture the new comment in the issue's comment history
            artifacts = await self._process_issue(job_id, issue_data, tenant_id)
            return artifacts  # type: ignore[return-value] # All Jira artifacts are part of IngestArtifact union

        except Exception as e:
            logger.error(f"Failed to handle Jira comment event: {e}")
            return []

    async def _handle_comment_deleted(
        self,
        payload: dict[str, Any],
        job_id: str,
        tenant_id: str,
    ) -> list[BaseIngestArtifact]:
        """Handle avi:jira:deleted:comment events."""
        try:
            # Extract issue key and ID from webhook payload
            issue_obj = payload.get("issue", {})
            issue_key = issue_obj.get("key")
            issue_id = issue_obj.get("id")

            if not issue_key or not issue_id:
                logger.warning("Missing issue key or ID in comment delete event payload")
                return []

            logger.info(f"Processing Jira comment deletion for issue {issue_key} (ID: {issue_id})")

            # Fetch fresh issue data from API to get current state without deleted comment
            jira_client = await self.get_jira_client(tenant_id)
            issue_data = jira_client.get_issue(issue_key)
            if not issue_data:
                logger.warning(f"Could not fetch issue data for issue {issue_key}")
                return []

            # Process the issue using shared base class method
            # This will capture the current comment state (without the deleted comment)
            artifacts = await self._process_issue(job_id, issue_data, tenant_id)
            return artifacts  # type: ignore[return-value] # All Jira artifacts are part of IngestArtifact union

        except Exception as e:
            logger.error(f"Failed to handle Jira comment deletion: {e}")
            return []
