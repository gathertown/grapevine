"""Google Drive citation resolver."""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.gmail.google_email_artifacts import GoogleEmailMessageArtifact
from connectors.gmail.google_email_message_document import GoogleEmailMessageDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class GoogleEmailCitationResolver(BaseCitationResolver[GoogleEmailMessageDocumentMetadata]):
    """Resolver for Google Email document citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[GoogleEmailMessageDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        if not resolver.permission_principal_token:
            logger.warning(f"No permission principal token found in resolver: {resolver}")
            return ""

        user_permission_token_email = resolver.permission_principal_token.split(":")[1]

        user_email = document.metadata.get("user_email")
        if not user_email:
            logger.warning(f"No user email found in document metadata: {document.metadata}")
            return ""

        thread_id = document.metadata.get("thread_id")
        if not thread_id:
            logger.warning(f"No thread id found in document metadata: {document.metadata}")
            return ""

        if user_email != user_permission_token_email:
            logger.warning(
                f"User email {user_email} does not match permission principal token email {user_permission_token_email}"
            )
            try:
                async with resolver.db_pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM ingest_artifact
                        WHERE entity='google_email_message'
                        AND content->>'user_email'=$1
                        AND content->>'subject'=$2
                        AND content->>'source_created_at'=$3
                        """,
                        user_permission_token_email,
                        document.metadata.get("subject"),
                        document.metadata.get("source_created_at"),
                    )
                    google_email_message_artifact = [
                        GoogleEmailMessageArtifact(**row) for row in rows
                    ]
                    if len(google_email_message_artifact) > 0:
                        first_artifact = google_email_message_artifact[0]
                        if first_artifact.content.user_email == user_permission_token_email:
                            return self._create_google_email_message_url_by_thread_id(
                                user_permission_token_email, first_artifact.content.thread_id
                            )

                    logger.warning(
                        f"No Google Email message found for user {user_permission_token_email} and subject {document.metadata.get('subject')} and source created at {document.metadata.get('source_created_at')}"
                    )
                    return self._create_google_email_message_url_by_search(
                        user_permission_token_email, document.metadata.get("subject") or ""
                    )

            except Exception as e:
                logger.error(
                    f"Error retrieving Google Email message for tenant {resolver.tenant_id}: {e}"
                )
                return ""

        return self._create_google_email_message_url_by_thread_id(user_email, thread_id)

    def _create_google_email_message_url_by_thread_id(self, user_email: str, thread_id: str) -> str:
        return "https://mail.google.com/mail/?authuser=" + user_email + "#all/" + thread_id

    def _create_google_email_message_url_by_search(self, user_email: str, subject: str) -> str:
        return (
            "https://mail.google.com/mail/?authuser="
            + user_email
            + "#search/"
            + urllib.parse.quote_plus(subject)
        )
