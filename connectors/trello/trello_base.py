"""Base extractor class for Trello-based extractors."""

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any, TypeVar
from uuid import uuid4

import asyncpg
from pydantic import BaseModel

from connectors.base import BaseExtractor, TriggerIndexingCallback, get_trello_card_entity_id
from connectors.trello.trello_artifacts import (
    TrelloCardArtifact,
    TrelloCardArtifactContent,
    TrelloCardArtifactMetadata,
)
from connectors.trello.trello_models import TrelloApiBackfillConfig
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.clients.trello import TrelloClient
from src.utils.config import get_trello_power_up_api_key

logger = logging.getLogger(__name__)


ConfigT = TypeVar("ConfigT", bound=BaseModel)


class TrelloExtractor(BaseExtractor[ConfigT], ABC):
    """Base class for Trello extractors with common functionality."""

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        """Initialize Trello extractor.

        Args:
            ssm_client: SSM client for retrieving tenant credentials
            sqs_client: SQS client for sending job messages
        """
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def get_trello_client(self, tenant_id: str) -> TrelloClient:
        """Get a Trello client for the given tenant.

        Args:
            tenant_id: The tenant ID

        Returns:
            Configured TrelloClient instance

        Raises:
            ValueError: If credentials are not configured
        """
        api_key = get_trello_power_up_api_key()
        if not api_key:
            raise ValueError("No Trello Power-Up API key configured in environment")

        api_token = await self.ssm_client.get_trello_token(tenant_id)
        if not api_token:
            raise ValueError(f"No Trello access token configured for tenant {tenant_id}")

        return TrelloClient(api_key=api_key, api_token=api_token)

    async def get_tenant_config_value(self, key: str, tenant_id: str) -> str | None:
        """Get a configuration value for a tenant.

        Args:
            key: Configuration key name
            tenant_id: The tenant ID

        Returns:
            Configuration value or None if not found
        """
        from src.utils.tenant_config import get_tenant_config_value

        return await get_tenant_config_value(key, tenant_id)

    async def send_backfill_child_job_message(
        self,
        config: TrelloApiBackfillConfig,
        _description: str = "job",
    ) -> None:
        """Send a Trello backfill job message.

        Args:
            config: The backfill job configuration to send
            _description: Description for logging (for API compatibility)

        Raises:
            Exception: If message sending fails
        """
        try:
            await self.sqs_client.send_backfill_ingest_message(backfill_config=config)
        except Exception as e:
            logger.error(f"Failed to send Trello backfill message: {e}")
            raise

    async def _process_card(
        self,
        _job_id: str,
        card_data: dict[str, Any],
        tenant_id: str,
        board_name: str | None = None,
        list_name: str | None = None,
        board_permission_level: str | None = None,
        board_member_emails: list[str] | None = None,
    ) -> list[TrelloCardArtifact]:
        """Process a single Trello card and create card artifact.

        This method transforms raw Trello API card data into a TrelloCardArtifact.
        The card_data should come from the Trello API with the following parameters:
        - fields=all
        - members=true
        - checklists=all
        - attachments=true

        Args:
            _job_id: The job ID processing this card (unused but kept for consistency)
            card_data: Raw Trello card data from API
            tenant_id: The tenant ID
            board_name: Board name (passed from parent context)
            list_name: List name (passed from parent context)
            board_permission_level: Board permission level ("private", "org", "public")
            board_member_emails: List of board member emails for permission resolution

        Returns:
            List containing single TrelloCardArtifact

        Raises:
            Exception: If processing fails
        """
        try:
            artifacts: list[TrelloCardArtifact] = []

            # Extract basic card information
            card_id = card_data.get("id", "")
            card_name = card_data.get("name", "")

            metadata = TrelloCardArtifactMetadata(
                card_id=card_id,
                card_name=card_name,
                desc=card_data.get("desc"),
                id_list=card_data.get("idList", ""),
                list_name=list_name,  # Passed from parent context
                id_board=card_data.get("idBoard", ""),
                board_name=board_name,  # Passed from parent context
                id_members=card_data.get("idMembers", []),
                labels=card_data.get("labels", []),
                closed=card_data.get("closed", False),
                due=card_data.get("due"),
                due_complete=card_data.get("dueComplete", False),
                start=card_data.get("start"),
                pos=card_data.get("pos"),
                short_url=card_data.get("shortUrl"),
                url=card_data.get("url"),
                date_last_activity=card_data.get("dateLastActivity"),
                id_short=card_data.get("idShort"),
                subscribed=card_data.get("subscribed", False),
                # Add permission fields
                board_permission_level=board_permission_level,
                board_member_emails=board_member_emails or [],
            )

            # Fetch comments separately (not included in card response by default)
            trello_client = await self.get_trello_client(tenant_id)
            comments = trello_client.get_card_actions(card_id=card_id, filter_types="commentCard")

            # Create card content with full API response + comments
            # Checklists are already included in card_data from API
            card_content = TrelloCardArtifactContent(
                card_data=card_data,
                comments=comments,
                checklists=card_data.get("checklists", []),
            )

            # Generate entity ID for card
            card_entity_id = get_trello_card_entity_id(card_id=card_id)

            # Parse source_updated_at from dateLastActivity or use current time
            source_updated_at = datetime.now(UTC)
            if date_last_activity := card_data.get("dateLastActivity"):
                try:
                    # Trello returns ISO format: "2024-01-15T10:30:45.123Z"
                    source_updated_at = datetime.fromisoformat(
                        date_last_activity.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    logger.warning(
                        f"Could not parse dateLastActivity '{date_last_activity}' for card {card_id}"
                    )

            # Create card artifact
            card_artifact = TrelloCardArtifact(
                entity_id=card_entity_id,
                ingest_job_id=uuid4(),
                content=card_content,
                metadata=metadata,
                source_updated_at=source_updated_at,
            )
            artifacts.append(card_artifact)

            logger.debug(f"Created card artifact for Trello card {card_id} ({card_name})")
            return artifacts

        except Exception as e:
            logger.error(
                f"Failed to process Trello card {card_data.get('id', 'unknown')}: {e}",
                exc_info=True,
            )
            raise

    @abstractmethod
    async def process_job(
        self,
        job_id: str,
        config: ConfigT,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process the extraction job - to be implemented by subclasses.

        Args:
            job_id: The job ID
            config: Job configuration
            db_pool: Database connection pool
            trigger_indexing: Callback to trigger indexing after artifacts are stored
        """
        pass
