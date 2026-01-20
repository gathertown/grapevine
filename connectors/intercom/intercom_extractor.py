import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

import asyncpg
from pydantic import BaseModel

if TYPE_CHECKING:
    from connectors.intercom.intercom_models import IntercomApiConversationsBackfillConfig

from connectors.base import BaseExtractor, TriggerIndexingCallback
from connectors.intercom.intercom_api_types import IntercomConversationData
from connectors.intercom.intercom_artifacts import (
    IntercomConversationArtifact,
    IntercomConversationArtifactContent,
    IntercomConversationArtifactMetadata,
)
from connectors.intercom.intercom_utils import normalize_timestamp
from src.clients.intercom import IntercomClient, get_intercom_client_for_tenant
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient

logger = logging.getLogger(__name__)

IntercomConfigType = TypeVar("IntercomConfigType", bound=BaseModel)


class IntercomExtractor(BaseExtractor[IntercomConfigType], ABC):
    """Abstract base class for Intercom-based extractors."""

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient | None = None):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client

    async def get_intercom_client(self, tenant_id: str, db_pool: asyncpg.Pool) -> IntercomClient:
        """Get Intercom client for the specified tenant.

        This method uses the factory to automatically handle OAuth token retrieval.

        Args:
            tenant_id: Tenant ID
            db_pool: Database pool (for future token refresh support)

        Returns:
            IntercomClient instance
        """
        try:
            return await get_intercom_client_for_tenant(tenant_id, self.ssm_client)
        except ValueError:
            raise ValueError(f"No Intercom OAuth authentication configured for tenant {tenant_id}")

    async def get_workspace_id(self, intercom_client: IntercomClient) -> str | None:
        """Get the workspace ID (app_id) for the Intercom app.

        The workspace_id is needed for constructing citation URLs. It's not returned
        in individual object responses, so we need to fetch it from the /me endpoint.

        Args:
            intercom_client: Authenticated Intercom client

        Returns:
            The workspace ID (app_id), or None if not available
        """
        try:
            me_response = intercom_client.get_me()
            # The /me endpoint returns app info with id being the workspace_id
            app_info = me_response.get("app", {})
            workspace_id = app_info.get("id_code") or app_info.get("id")
            if workspace_id:
                logger.debug(f"Fetched workspace_id from /me endpoint: {workspace_id}")
            return workspace_id
        except Exception as e:
            logger.warning(f"Failed to fetch workspace_id from /me endpoint: {e}")
            return None

    @abstractmethod
    async def process_job(
        self,
        job_id: str,
        config: IntercomConfigType,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        """Process an ingest job - must be implemented by subclasses."""
        pass

    async def process_conversation(
        self,
        job_id: str,
        conversation_data: dict[str, Any],
        tenant_id: str,
        db_pool: asyncpg.Pool,
        workspace_id: str | None = None,
    ) -> IntercomConversationArtifact:
        """
        Process a single conversation and create an artifact.

        Args:
            job_id: The ingest job ID
            conversation_data: Raw, fresh conversation data from Intercom API. This should have been freshly pulled from API.
            tenant_id: The tenant ID
            db_pool: Database pool for token expiry management
            workspace_id: The Intercom workspace ID (app_id) for citation URLs
        """
        if not isinstance(conversation_data, dict):
            raise ValueError(
                f"Conversation data must be a dict, got {type(conversation_data)}: {conversation_data}"
            )

        conversation_id = conversation_data.get("id")
        if not conversation_id:
            available_keys = list(conversation_data.keys())[:10]  # First 10 keys for debugging
            raise ValueError(
                f"Conversation ID not found in conversation data. Available keys: {available_keys}. "
                f"Full data: {conversation_data}"
            )

        # State is optional in some cases, use empty string as default
        state = conversation_data.get("state") or conversation_data.get("status") or ""

        created_at_raw = conversation_data.get("created_at") or conversation_data.get("created")
        created_at_str, created_at_dt = normalize_timestamp(created_at_raw)

        updated_at_raw = conversation_data.get("updated_at") or conversation_data.get("updated")
        updated_at_str, updated_at_dt = normalize_timestamp(updated_at_raw or created_at_raw)

        # Use passed workspace_id, or try to get from conversation data (unlikely to be present)
        effective_workspace_id = workspace_id or conversation_data.get("workspace_id")

        metadata = IntercomConversationArtifactMetadata(
            conversation_id=str(conversation_id),
            state=str(state),
            created_at=created_at_str,
            updated_at=updated_at_str,
            workspace_id=effective_workspace_id,
        )

        # Convert raw dict to typed Pydantic model, injecting workspace_id if available
        conversation_data_with_workspace = {**conversation_data}
        if effective_workspace_id:
            conversation_data_with_workspace["workspace_id"] = effective_workspace_id
        typed_conversation_data = IntercomConversationData.model_validate(
            conversation_data_with_workspace
        )

        content = IntercomConversationArtifactContent(
            conversation_data=typed_conversation_data,
        )

        artifact = IntercomConversationArtifact(
            entity_id=str(conversation_id),
            ingest_job_id=UUID(job_id),
            content=content,
            metadata=metadata,
            # Use Intercom's updated_at timestamp so re-runs only upsert when data changes
            source_updated_at=updated_at_dt,
        )

        return artifact

    async def send_backfill_child_job_message(
        self,
        config: "IntercomApiConversationsBackfillConfig",
        description: str = "job",
    ) -> None:
        """
        Send an Intercom backfill job message.

        Args:
            config: The backfill job configuration to send
            description: Description for logging (e.g., "child job batch 0")
        """
        if self.sqs_client is None:
            raise RuntimeError("SQS client not configured - cannot send child job messages")

        try:
            await self.sqs_client.send_backfill_ingest_message(
                backfill_config=config,
            )

            # Log the message sending
            conversation_count = len(config.conversation_ids or [])
            log_message = (
                f"Sent {description} for tenant {config.tenant_id} "
                f"with {conversation_count} conversations"
            )
            logger.info(log_message)

        except Exception as e:
            logger.error(f"Failed to send {description}: {e}")
            raise
