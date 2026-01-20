"""Slack citation resolver."""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.slack.slack_artifacts import SlackMessageArtifact
from connectors.slack.slack_channel_document import SlackChannelDocumentMetadata
from src.utils.logging import get_logger
from src.utils.pacific_time import format_pacific_time

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class SlackCitationResolver(BaseCitationResolver[SlackChannelDocumentMetadata]):
    """Resolver for Slack message citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[SlackChannelDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        logger.info(f"Slack resolver: doc_id={document.id}, has_metadata={bool(document.metadata)}")

        # Extract typed metadata
        channel_id = document.metadata["channel_id"]
        team_domain = document.metadata["team_domain"]

        unix_timestamp = None
        thread_ts = None

        slack_message, confidence = await self._find_slack_message(document, excerpt, resolver)

        if slack_message:
            logger.info(f"Found Slack message ({confidence}% confidence)")
            unix_timestamp = slack_message.content.ts
            # Check if thread_ts exists in the content (may be in extra fields due to allow config)
            thread_ts = getattr(slack_message.content, "thread_ts", None)
        else:
            logger.warning(
                f"Didn't find a message-level citation, using page-level for doc_id={document.id}"
            )

        url = f"https://{team_domain}.slack.com/archives/{channel_id}"
        if unix_timestamp:
            # Convert timestamp format for Slack permalink (remove decimal point)
            permalink_ts = unix_timestamp.replace(".", "")
            url += f"/p{permalink_ts}"
        if thread_ts:
            url += f"?thread_ts={thread_ts}&cid={channel_id}"

        return url

    def _extract_timestamp_from_line(
        self, document_content: str, excerpt_start_pos: int
    ) -> str | None:
        """Extract timestamp from the line containing the excerpt position.

        Args:
            document_content: Full document content
            excerpt_start_pos: Position where the excerpt starts in the document

        Returns:
            Formatted time string if found, None otherwise
        """
        # Find the start of the line containing the excerpt
        line_start = document_content.rfind("\n", 0, excerpt_start_pos)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1  # Skip the newline character

        # Find the end of the line
        line_end = document_content.find("\n", excerpt_start_pos)
        if line_end == -1:
            line_end = len(document_content)

        line_content = document_content[line_start:line_end]

        # Handle thread replies (indented lines starting with "|--")
        if line_content.strip().startswith("|--"):
            line_content = line_content.strip()[3:].strip()

        # Extract timestamp from formatted time at the beginning of the line
        # Expected format: "2025-01-15 14:30:00 PST <@USER_ID|@username> : message"
        # We need to convert this back to Unix timestamp

        # Match the timestamp format at the start of the line
        timestamp_pattern = r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (?:PST|PDT))"
        match = re.match(timestamp_pattern, line_content)

        if not match:
            logger.warning("Could not extract timestamp from line")
            return None

        formatted_time = match.group(1)

        return formatted_time

    async def _find_slack_message(
        self,
        document: DocumentWithSourceAndMetadata[SlackChannelDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> tuple[SlackMessageArtifact | None, float]:
        """Find the Slack message that contains the excerpt using exact substring matching."""
        try:
            # Get the full document content
            document_content = await resolver._get_document_contents(document.id)
            logger.info(
                f"Retrieved document content for {document.id}, length: {len(document_content)}"
            )

            # Strip quotes from excerpt if present (excerpts are sometimes wrapped in quotes)
            search_excerpt = excerpt.strip('"').strip("'")
            logger.info("Searching for excerpt in document content")

            # Find the exact position of the excerpt in the document
            excerpt_pos = document_content.find(search_excerpt)
            if excerpt_pos == -1:
                logger.warning("Excerpt not found in document content")
                return (None, 0.0)

            logger.info(f"Found excerpt at position {excerpt_pos}")

            # Extract the timestamp from the line containing the excerpt
            timestamp = self._extract_timestamp_from_line(document_content, excerpt_pos)
            if not timestamp:
                logger.warning("Could not extract timestamp from excerpt position")
                return (None, 0.0)

            logger.info(f"Extracted timestamp: {timestamp}")

            # Find the message with matching timestamp
            messages = await self._get_slack_messages_for_channel_day(document.metadata, resolver)
            logger.info(f"Searching through {len(messages)} messages for timestamp {timestamp}")

            for message in messages:
                message_ts = message.content.ts

                # Convert message_ts to formatted time using the same logic as Slack transformer
                try:
                    message_formatted_time = format_pacific_time(message_ts)
                    # there's an edge case here where if there's multiple messages in the same second, we won't be able to distinguish them. This is fine for now, but we could improve by:
                    # - collecting all of the matching messages
                    # - iterating through their contents and returning the one that contains a string closest to the excerpt (note: this would be a similarity search because the excerpt has different formatting)

                    # Compare formatted timestamps
                    if message_formatted_time == timestamp:
                        return (message, 1.0)
                except Exception as e:
                    logger.warning(f"Error formatting message timestamp {message_ts}: {e}")
                    continue

            logger.warning(f"No message found with timestamp {timestamp}")
            return (None, 0.0)

        except Exception as e:
            logger.error(f"Error in _find_slack_message: {e}")
            return (None, 0.0)

    async def _get_slack_messages_for_channel_day(
        self, metadata: SlackChannelDocumentMetadata, resolver: CitationResolver
    ) -> list[SlackMessageArtifact]:
        """Find the Slack messages for a given channel and date."""

        channel_id = metadata["channel_id"]
        date_str = metadata["date"]

        logger.info(f"Finding Slack messages for channel {channel_id} on {date_str}")

        # Parse the date string to a datetime.date object for proper type handling
        if not date_str:
            logger.warning("No date provided in metadata")
            return []
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

        async with resolver.db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM ingest_artifact
                WHERE entity='slack_message'
                  AND metadata->>'channel_id'=$1
                  AND source_updated_at >= $2::date
                  AND source_updated_at < ($2::date + interval '1 day')
                """,
                channel_id,
                date_obj,
            )

        return [SlackMessageArtifact(**row) for row in rows]
