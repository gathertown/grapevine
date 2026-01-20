import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

import asyncpg

from connectors.base import BaseExtractor, get_google_email_message_entity_id
from connectors.base.document_source import DocumentSource
from connectors.gmail.gmail_models import GoogleEmailUserConfig
from connectors.gmail.google_email_artifacts import (
    GoogleEmailMessageArtifact,
    GoogleEmailMessageContent,
    GoogleEmailMessageMetadata,
)
from src.clients.google_email import GoogleEmailClient, parse_email_addresses
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE

logger = logging.getLogger(__name__)


class GoogleEmailUserExtractor(BaseExtractor[GoogleEmailUserConfig]):
    source_name = "google_email_user"

    def __init__(self):
        super().__init__()
        self.ssm_client = SSMClient()

    async def process_job(
        self,
        job_id: str,
        config: GoogleEmailUserConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: Callable[[list[str], DocumentSource, str], Awaitable[None]],
    ) -> None:
        start_time = time.time()
        try:
            admin_email = await self.ssm_client.get_google_email_admin_email(config.tenant_id)
            if not admin_email:
                raise ValueError(f"No admin email found for tenant {config.tenant_id}")

            email_client = GoogleEmailClient(
                tenant_id=config.tenant_id,
                admin_email=config.user_email,
                ssm_client=self.ssm_client,
            )

            logger.info(f"Processing emails for user {config.user_email} (job {job_id})")

            await self._process_user_emails(
                email_client,
                config.user_email,
                config.user_id,
                job_id,
                config.tenant_id,
                db_pool,
                trigger_indexing,
            )

            duration = time.time() - start_time
            logger.info(
                f"Successfully completed processing emails for {config.user_email} in {duration:.2f} seconds"
            )

        except Exception as e:
            logger.error(f"Job {job_id} failed for user {config.user_email}: {e}")
            raise

    async def _process_user_emails(
        self,
        email_client: GoogleEmailClient,
        user_email: str,
        user_id: str,
        job_id: str,
        tenant_id: str,
        db_pool: asyncpg.Pool,
        trigger_indexing: Callable[[list[str], DocumentSource, str], Awaitable[None]],
    ) -> None:
        message_ids_batch = []
        total_processed = 0
        page_token = None

        parallel_batch_size = 10

        while True:
            result = await email_client.list_user_emails(
                user_id="me", query="{in:inbox in:sent} newer_than:90d", page_token=page_token
            )

            messages = result.get("messages", [])
            message_ids = [msg["id"] for msg in messages]

            for i in range(0, len(message_ids), parallel_batch_size):
                batch = message_ids[i : i + parallel_batch_size]
                batch_results = await email_client.get_emails_batch(
                    user_id="me", message_ids=batch, format="full"
                )

                for msg_id, message_data_or_error in zip(batch, batch_results, strict=False):
                    if isinstance(message_data_or_error, Exception):
                        logger.error(f"Failed to fetch message {msg_id}: {message_data_or_error}")
                        continue

                    artifact = await create_email_artifact(
                        email_client, user_id, msg_id, job_id, user_email, message_data_or_error
                    )
                    if artifact:
                        await self.store_artifact(db_pool, artifact)
                        message_ids_batch.append(msg_id)
                        total_processed += 1
                        if len(message_ids_batch) >= DEFAULT_INDEX_BATCH_SIZE:
                            await trigger_indexing(
                                message_ids_batch, DocumentSource.GOOGLE_EMAIL, tenant_id
                            )
                            message_ids_batch = []
                            logger.info(
                                f"Indexed batch of {DEFAULT_INDEX_BATCH_SIZE} emails for {user_email}"
                            )

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        if message_ids_batch:
            await trigger_indexing(message_ids_batch, DocumentSource.GOOGLE_EMAIL, tenant_id)
            logger.info(f"Indexed final batch of {len(message_ids_batch)} emails for {user_email}")

        logger.info(
            f"Finished processing emails for {user_email}. "
            f"Total domain-accessible emails: {total_processed}"
        )


async def create_email_artifact(
    email_client: GoogleEmailClient,
    user_id: str,
    message_id: str,
    job_id: str,
    user_email: str,
    message_data: dict | None = None,
) -> GoogleEmailMessageArtifact | None:
    """Create email artifact from message data.
    Args:
        email_client: Google email client
        user_id: User ID
        message_id: Message ID
        job_id: Job ID
        user_email: User email
        message_data: Optional pre-fetched message data. If None, will fetch from API.
    """
    try:
        if not message_data:
            message_data = await email_client.get_email(
                user_id="me", message_id=message_id, format="full"
            )

        # TODO: add attachments
        return GoogleEmailMessageArtifact(
            entity_id=get_google_email_message_entity_id(message_id=message_id),
            ingest_job_id=UUID(job_id),
            source_updated_at=datetime.fromtimestamp(
                int(message_data["internal_date"]) / 1000, tz=UTC
            ),
            content=GoogleEmailMessageContent(
                message_id=message_id,
                thread_id=message_data["thread_id"],
                subject=message_data["subject"],
                body=message_data["text"],
                date=message_data["date"],
                source_created_at=datetime.fromtimestamp(
                    int(message_data["internal_date"]) / 1000, tz=UTC
                ).isoformat(),
                user_id=user_id,
                user_email=user_email,
                from_address=parse_email_addresses(message_data["from"])[0],
                to_addresses=parse_email_addresses(message_data["to"]),
                cc_addresses=parse_email_addresses(message_data["cc"]),
                bcc_addresses=parse_email_addresses(message_data["bcc"]),
            ),
            metadata=GoogleEmailMessageMetadata(
                size_estimate=message_data["size_estimate"],
                internal_date=message_data["internal_date"],
                labels=message_data["labels"],
            ),
        )

    except Exception as e:
        logger.error(f"Failed to create email artifact: {e}")
        return None
