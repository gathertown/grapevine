"""
Base extractor class for Jira-based extractors.
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import uuid4

import asyncpg
from pydantic import BaseModel

from connectors.base import BaseExtractor, TriggerIndexingCallback, get_jira_issue_entity_id
from connectors.jira.jira_artifacts import (
    JiraIssueArtifact,
    JiraIssueArtifactContent,
    JiraIssueArtifactMetadata,
)
from connectors.jira.jira_models import JiraApiBackfillConfig
from src.clients.jira import JiraClient
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)


ConfigT = TypeVar("ConfigT", bound=BaseModel)


class JiraExtractor(BaseExtractor[ConfigT], ABC):
    """Base class for Jira extractors with common functionality."""

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def get_jira_client(self, tenant_id: str) -> JiraClient:
        """Get a Jira client for the given tenant."""
        forge_oauth_token = await self.ssm_client.get_jira_system_oauth_token(tenant_id)
        if not forge_oauth_token:
            raise ValueError(f"No Jira system OAuth token configured for tenant {tenant_id}")

        cloud_id = await self.get_tenant_config_value("JIRA_CLOUD_ID", tenant_id)

        if cloud_id:
            return JiraClient(forge_oauth_token=forge_oauth_token, cloud_id=cloud_id)
        else:
            raise ValueError(f"No Jira site URL or cloud ID configured for tenant {tenant_id}")

    async def get_tenant_config_value(self, key: str, tenant_id: str) -> str | None:
        """
        Get a configuration value for a tenant.
        """
        from src.utils.tenant_config import get_tenant_config_value

        return await get_tenant_config_value(key, tenant_id)

    async def send_backfill_child_job_message(
        self,
        config: JiraApiBackfillConfig,
        _description: str = "job",
    ) -> None:
        """
        Send a Jira backfill job message.

        Args:
            config: The backfill job configuration to send
            description: Description for logging (for API compatibility)
        """
        try:
            await self.sqs_client.send_backfill_ingest_message(backfill_config=config)
        except Exception as e:
            logger.error(f"Failed to send Jira backfill message: {e}")
            raise

    async def _process_issue(
        self, _job_id: str, issue_data: dict[str, Any], tenant_id: str
    ) -> list[JiraIssueArtifact]:
        """
        Process a single Jira issue and create issue artifact.

        Args:
            job_id: The job ID processing this issue
            issue_data: Raw Jira issue data from API
            tenant_id: The tenant ID

        Returns:
            List of artifacts ready for storage (issue only)
        """
        try:
            artifacts: list[JiraIssueArtifact] = []

            # Extract basic issue information
            issue_key = issue_data.get("key", "")
            issue_id = issue_data.get("id", "")

            fields = issue_data.get("fields", {})
            summary = fields.get("summary", "")

            # Extract project information
            project = fields.get("project", {})
            project_key = project.get("key", "")
            project_id = project.get("id", "")
            project_name = project.get("name", "")

            # Extract status, priority, assignee, etc.
            status_obj = fields.get("status")
            status = status_obj.get("name") if status_obj else None

            priority_obj = fields.get("priority")
            priority = priority_obj.get("name") if priority_obj else None

            assignee_obj = fields.get("assignee")
            assignee = assignee_obj.get("displayName") if assignee_obj else None
            assignee_id = assignee_obj.get("accountId") if assignee_obj else None

            reporter_obj = fields.get("reporter")
            reporter = reporter_obj.get("displayName") if reporter_obj else None
            reporter_id = reporter_obj.get("accountId") if reporter_obj else None

            # Extract labels
            labels = list(fields.get("labels", []))

            # Extract issue type
            issue_type_obj = fields.get("issuetype")
            issue_type = issue_type_obj.get("name") if issue_type_obj else None

            # Extract parent issue for sub-tasks
            parent_obj = fields.get("parent")
            parent_issue_key = parent_obj.get("key") if parent_obj else None

            jira_client = await self.get_jira_client(tenant_id)
            site_domain = await jira_client.get_site_domain(tenant_id, self)

            # Extract comments
            comments = []
            comment_data = issue_data.get("fields", {}).get("comment", {}).get("comments", [])
            if comment_data:
                comments = comment_data

            # Create issue metadata with project_id reference
            issue_metadata = JiraIssueArtifactMetadata(
                issue_key=issue_key,
                issue_id=issue_id,
                issue_title=summary,
                project_key=project_key,
                project_id=project_id,  # This is the reference to the project artifact
                project_name=project_name,
                status=status,
                priority=priority,
                assignee=assignee,
                assignee_id=assignee_id,
                reporter=reporter,
                reporter_id=reporter_id,
                labels=labels,
                issue_type=issue_type,
                parent_issue_key=parent_issue_key,
                site_domain=site_domain,
            )

            # Create issue content
            issue_content = JiraIssueArtifactContent(issue_data=issue_data, comments=comments)

            # Generate entity ID for issue
            issue_entity_id = get_jira_issue_entity_id(issue_id=issue_id)

            # Create issue artifact
            issue_artifact = JiraIssueArtifact(
                entity_id=issue_entity_id,
                ingest_job_id=uuid4(),
                content=issue_content,
                metadata=issue_metadata,
                source_updated_at=datetime.now(UTC),
            )
            artifacts.append(issue_artifact)

            logger.debug(f"Created issue artifact for Jira issue {issue_key}")
            return artifacts

        except Exception as e:
            logger.error(f"Failed to process Jira issue {issue_data.get('key', 'unknown')}: {e}")
            raise

    @abstractmethod
    async def process_job(
        self,
        job_id: str,
        config: ConfigT,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process the extraction job - to be implemented by subclasses."""
        pass
