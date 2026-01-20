"""
Base extractor class for Confluence-based extractors.
"""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import uuid4

import asyncpg
from pydantic import BaseModel

from connectors.base import (
    BaseExtractor,
    TriggerIndexingCallback,
    get_confluence_page_entity_id,
)
from connectors.confluence.confluence_artifacts import (
    ConfluencePageArtifact,
    ConfluencePageArtifactContent,
    ConfluencePageArtifactMetadata,
)
from connectors.confluence.confluence_models import ConfluenceApiBackfillConfig
from src.clients.confluence import ConfluenceClient
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.utils.tenant_config import get_tenant_config_value

logger = logging.getLogger(__name__)


ConfigT = TypeVar("ConfigT", bound=BaseModel)


class ConfluenceExtractor(BaseExtractor[ConfigT], ABC):
    """Base class for Confluence extractors with common functionality."""

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        # Cache for current job's space information
        self._current_space: dict[str, str] | None = None

    async def get_confluence_client(self, tenant_id: str) -> ConfluenceClient:
        """Get a Confluence client for the given tenant."""
        forge_oauth_token = await self.ssm_client.get_confluence_system_oauth_token(tenant_id)
        if not forge_oauth_token:
            raise ValueError(f"No Confluence system OAuth token configured for tenant {tenant_id}")

        cloud_id = await get_tenant_config_value("CONFLUENCE_CLOUD_ID", tenant_id)

        if cloud_id:
            return ConfluenceClient(forge_oauth_token=forge_oauth_token, cloud_id=cloud_id)
        else:
            raise ValueError(
                f"No Confluence site URL or cloud ID configured for tenant {tenant_id}"
            )

    async def send_backfill_child_job_message(
        self,
        config: ConfluenceApiBackfillConfig,
        _description: str = "job",
    ) -> None:
        """
        Send a Confluence backfill job message.

        Args:
            config: The backfill job configuration to send
            description: Description for logging (for API compatibility)
        """
        try:
            await self.sqs_client.send_backfill_ingest_message(backfill_config=config)
        except Exception as e:
            logger.error(f"Failed to send Confluence backfill message: {e}")
            raise

    async def _load_space_info(self, space_id: str, tenant_id: str) -> None:
        """Load single space info and cache it for the current job."""
        if not space_id:
            logger.warning("No space_id provided to load_space_info")
            return

        try:
            confluence_client = await self.get_confluence_client(tenant_id)
            space_data = confluence_client.get_space(space_id)

            if space_data:
                self._current_space = {
                    "space_id": space_data.get("id", ""),
                    "space_key": space_data.get("key", ""),
                    "space_name": space_data.get("name", ""),
                }
                logger.info(
                    f"Cached space info: {self._current_space['space_name']} ({self._current_space['space_key']})"
                )
            else:
                logger.warning(f"Could not load space data for space_id: {space_id}")
                self._current_space = None

        except Exception as e:
            logger.error(f"Failed to load space info for {space_id}: {e}")
            self._current_space = None

    async def _process_page(
        self, _job_id: str, page_data: dict[str, Any], tenant_id: str
    ) -> list[ConfluencePageArtifact]:
        """
        Process a single Confluence page and create page artifact only.

        Note: Space and user artifacts are created in the root job following Google Drive pattern.

        Args:
            job_id: The job ID processing this page
            page_data: Raw Confluence page data from API
            tenant_id: The tenant ID

        Returns:
            List containing only the page artifact
        """
        try:
            artifacts: list[ConfluencePageArtifact] = []

            # Extract basic page information
            page_id = page_data.get("id", "")
            page_title = page_data.get("title", "")

            # Extract version information for timestamps
            version = page_data.get("version", {})
            version_when = version.get("when")

            # Extract author information from version
            version_by = version.get("by", {})
            author_name = version_by.get("displayName", "")
            author_id = version_by.get("accountId", "")

            # Build participants dict - start with author
            participants: dict[str, str] = {}
            if author_id and author_name:
                participants[author_id] = author_name

            # Extract space information from cached space info
            if not self._current_space:
                raise ValueError("Space info not loaded - call _load_space_info first")

            space_id = self._current_space["space_id"]
            space_key = self._current_space["space_key"]

            # Extract parent page if exists
            parent_id = None
            if "parentId" in page_data:
                parent_id = page_data["parentId"]

            # Get site URL to construct page URL
            site_url = await get_tenant_config_value("CONFLUENCE_SITE_URL", tenant_id)

            # Construct page URL
            page_url = f"{site_url}/wiki/spaces/{space_key}/pages/{page_id}"

            # Create page metadata
            page_metadata = ConfluencePageArtifactMetadata(
                page_id=page_id,
                page_title=page_title,
                page_url=page_url,
                space_id=space_id,
                participants=participants,
                parent_page_id=parent_id,
                source_created_at=page_data.get("createdAt", version_when or ""),
                source_updated_at=version_when or "",
            )

            # Create page content
            page_content = ConfluencePageArtifactContent(
                page_data=page_data,
            )

            # Generate entity ID for page
            page_entity_id = get_confluence_page_entity_id(page_id=page_id)

            # Create page artifact
            page_artifact = ConfluencePageArtifact(
                entity_id=page_entity_id,
                ingest_job_id=uuid4(),
                content=page_content,
                metadata=page_metadata,
                source_updated_at=datetime.now(UTC),
            )
            artifacts.append(page_artifact)

            logger.debug(
                f"Created {len(artifacts)} artifacts for Confluence page {page_title} "
                f"(1 page only - users and space created in root job)"
            )
            return artifacts

        except Exception as e:
            logger.error(f"Failed to process Confluence page {page_data.get('id', 'unknown')}: {e}")
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
