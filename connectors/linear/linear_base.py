"""
Base extractor class for Linear-based extractors.
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import UUID

import asyncpg
from pydantic import BaseModel

from connectors.base import BaseExtractor, TriggerIndexingCallback, get_linear_issue_entity_id
from connectors.linear.linear_artifacts import (
    LinearIssueArtifact,
    LinearIssueArtifactContent,
    LinearIssueArtifactMetadata,
)
from connectors.linear.linear_models import LinearApiBackfillConfig
from src.clients.linear import LinearClient
from src.clients.linear_factory import get_linear_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

LinearConfigType = TypeVar("LinearConfigType", bound=BaseModel)


class LinearExtractor(BaseExtractor[LinearConfigType], ABC):
    """Abstract base class for Linear-based extractors."""

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def get_linear_client(self, tenant_id: str, db_pool: asyncpg.Pool) -> LinearClient:
        """Get Linear client for the specified tenant.

        This method uses the factory to automatically handle OAuth token refresh
        when needed. Falls back to legacy API key if OAuth is not configured.

        Args:
            tenant_id: Tenant ID
            db_pool: Database pool for token expiry management

        Returns:
            LinearClient instance
        """
        try:
            return await get_linear_client_for_tenant(tenant_id, self.ssm_client, db_pool)
        except ValueError:
            logger.info(f"[tenant_id={tenant_id}] No OAuth configured, trying legacy API key")
            api_key = await self.ssm_client.get_api_key(tenant_id, "LINEAR_API_KEY")
            if not api_key:
                raise ValueError(f"No Linear authentication configured for tenant {tenant_id}")
            return LinearClient(token=api_key)

    @abstractmethod
    async def process_job(
        self,
        job_id: str,
        config: LinearConfigType,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process an ingest job - must be implemented by subclasses."""
        pass

    async def _process_issue(
        self, job_id: str, issue_data: dict[str, Any], tenant_id: str, db_pool: asyncpg.Pool
    ) -> LinearIssueArtifact:
        """
        Process a single issue and create an artifact.

        Args:
            job_id: The ingest job ID
            issue_data: Raw, fresh issue data from Linear API. This should have been freshly pulled from API.
            tenant_id: The tenant ID
            db_pool: Database pool for token expiry management
        """
        issue_id = issue_data.get("id")
        if not issue_id:
            raise ValueError(f"Issue ID not found in issue data: {issue_data}")

        # Fetch comments for this issue
        linear_client = await self.get_linear_client(tenant_id, db_pool)
        comments = linear_client.get_all_issue_comments(issue_id) or []

        # Extract team info
        team_data = issue_data.get("team") or {}
        team_id = team_data.get("id", "") if team_data else ""
        team_name = team_data.get("name", "") if team_data else ""

        # Extract issue metadata
        assignee_data = issue_data.get("assignee") or {}
        assignee_name = (
            assignee_data.get("displayName") or assignee_data.get("name", "")
            if assignee_data
            else None
        )

        labels = []
        labels_data = issue_data.get("labels") or []
        for label in labels_data:
            if isinstance(label, dict) and "name" in label:
                labels.append(label["name"])

        artifact = LinearIssueArtifact(
            entity_id=get_linear_issue_entity_id(issue_id=issue_id),
            ingest_job_id=UUID(job_id),
            content=LinearIssueArtifactContent(issue_data=issue_data, comments=comments),
            metadata=LinearIssueArtifactMetadata(
                issue_id=issue_id,
                issue_identifier=issue_data.get("identifier", ""),
                issue_title=issue_data.get("title", ""),
                team_id=team_id,
                team_name=team_name,
                status=(issue_data.get("state") or {}).get("name", "")
                if issue_data.get("state")
                else None,
                priority=str(issue_data.get("priority", ""))
                if issue_data.get("priority")
                else None,
                assignee=assignee_name,
                labels=labels,
            ),
            # We always pull Linear issues fresh from the API regardless of backfill vs webhook,
            # so we can set source_updated_at to now() since we can assume we just pulled this from API
            source_updated_at=datetime.now(tz=UTC),
        )

        return artifact

    async def send_backfill_child_job_message(
        self,
        config: LinearApiBackfillConfig,
        description: str = "job",
    ) -> None:
        """
        Send a Linear backfill job message with optional delay.

        Args:
            config: The backfill job configuration to send
            delay_timestamp: Optional timestamp when the job should start (for rate limiting)
            description: Description for logging (e.g., "child job batch 0", "re-queued job")
        """
        try:
            await self.sqs_client.send_backfill_ingest_message(
                backfill_config=config,
            )

            # Log the message sending
            log_message = f"Sent {description} for tenant {config.tenant_id} with {len(config.issue_ids)} issues"
            if config.start_timestamp:
                log_message += f". Was scheduled to start at {config.start_timestamp.isoformat()}"
            logger.info(log_message)

        except Exception as e:
            logger.error(f"Failed to send {description}: {e}")
            raise
