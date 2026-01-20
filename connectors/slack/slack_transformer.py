"""Transformer for Slack channel-day artifacts to SlackChannelDocuments."""

import asyncio
import html
import re
from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from typing import Any

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_slack_doc_id
from connectors.base.document_source import DocumentSource
from connectors.slack.slack_channel_document import SlackChannelDocument
from connectors.slack.slack_message_utils import deduplicate_messages
from connectors.slack.slack_thread_utils import (
    resolve_thread_relationships_with_placeholders,
    sort_messages_for_display,
)
from src.permissions.models import PermissionPolicy
from src.permissions.utils import make_email_permission_token
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore
from src.utils.logging import get_logger
from src.utils.pacific_time import format_pacific_time

logger = get_logger(__name__)


class SlackTransformer(BaseTransformer[SlackChannelDocument]):
    """Transform Slack channel-day batches into SlackChannelDocuments."""

    # Pre-compiled regex patterns for better performance
    MENTION_PATTERN = re.compile(r"<@(U[A-Z0-9]+)>")
    CHANNEL_PATTERN = re.compile(r"<#(C[A-Z0-9]+)(?:\|([^>]+))?>")

    def __init__(self):
        """Initialize the transformer."""
        super().__init__(DocumentSource.SLACK)
        self._channels_metadata = {}
        self._users_metadata = {}
        self._user_map = {}
        self._channel_map = {}
        self._team_metadata = {}
        self._dm_participants_map = {}  # Map DM ID to list of participant user IDs

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[SlackChannelDocument]:
        """Transform Slack artifacts identified by entity_ids into SlackChannelDocuments.

        This method bridges the standard index pipeline to Slack's channel-day based processing.
        It extracts unique channel-day combinations from the given entity_ids and processes them.

        Args:
            entity_ids: List of entity IDs (e.g., message IDs, channel IDs, user IDs)
            readonly_db_pool: Database connection pool

        Returns:
            List of SlackChannelDocument instances
        """
        if not entity_ids:
            logger.warning("No entity_ids provided to transform_artifacts")
            return []

        logger.info(f"Processing {len(entity_ids)} entity IDs for Slack transformation")

        # Query database to find unique channel-day combinations from these entity_ids
        async with readonly_db_pool.acquire() as conn:
            # Get all artifacts for these entity_ids to determine what needs processing
            artifacts = await conn.fetch(
                """
                SELECT entity, entity_id, metadata, content
                FROM ingest_artifact
                WHERE entity_id = ANY($1)
                """,
                entity_ids,
            )

            if not artifacts:
                logger.warning(f"No artifacts found for {len(entity_ids)} entity IDs")
                return []

            # Extract unique channel-day combinations
            channel_days_set = set()

            for artifact in artifacts:
                entity_type = artifact["entity"]
                entity_id = artifact["entity_id"]
                metadata = artifact.get("metadata", {})
                content = artifact.get("content", {})

                if entity_type == "slack_message":
                    # Extract channel and date from message artifacts
                    channel_id = metadata.get("channel_id") or content.get("channel")
                    ts = content.get("ts")

                    if channel_id and ts:
                        try:
                            # Convert timestamp to date
                            dt = datetime.fromtimestamp(float(ts), tz=UTC)
                            date_str = dt.strftime("%Y-%m-%d")
                            channel_days_set.add((channel_id, date_str))
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Invalid timestamp {ts} for entity {entity_id}: {e}")
                            continue

                elif entity_type == "slack_channel":
                    # For channel artifacts, we need to process all days with messages
                    # This will be handled by finding all messages for this channel
                    channel_id = entity_id

                    # Query for all unique days with messages in this channel
                    channel_days = await conn.fetch(
                        """
                        SELECT DISTINCT DATE(to_timestamp((content->>'ts')::float)) as date
                        FROM ingest_artifact
                        WHERE entity = 'slack_message'
                          AND metadata->>'channel_id' = $1
                        ORDER BY date
                        """,
                        channel_id,
                    )

                    for row in channel_days:
                        if row["date"]:
                            date_str = row["date"].strftime("%Y-%m-%d")
                            channel_days_set.add((channel_id, date_str))

                # Skip user and team artifacts as they don't map to channel-days

        if not channel_days_set:
            logger.warning("No channel-day combinations found from entity_ids")
            return []

        # Convert to list of dicts for transform_channel_days
        channel_days = [
            {"channel_id": channel_id, "date": date} for channel_id, date in channel_days_set
        ]

        logger.info(f"Found {len(channel_days)} unique channel-day combinations to process")

        # Use the existing transform_channel_days implementation
        return await self.transform_channel_days(channel_days, readonly_db_pool)

    async def transform_channel_days(
        self, channel_days: list[dict[str, str]], readonly_db_pool: asyncpg.Pool
    ) -> list[SlackChannelDocument]:
        """Transform channel-day batches into SlackChannelDocuments.

        Args:
            channel_days: List of dicts with 'channel_id' and 'date' keys
            readonly_db_pool: Database connection pool

        Returns:
            List of SlackChannelDocument instances
        """
        if not channel_days:
            logger.warning("No channel-days to process")
            return []

        # First, load all metadata (users, channels, teams)
        await self._load_all_metadata(readonly_db_pool)

        logger.info(f"Processing {len(channel_days)} channel-day combinations")

        # Create semaphore to limit concurrency to 40
        semaphore = asyncio.Semaphore(40)

        async def build_document_with_semaphore(channel_day):
            async with semaphore:
                try:
                    doc = await self._build_channel_day_document(
                        channel_day["channel_id"], channel_day["date"], readonly_db_pool
                    )
                    if doc:
                        logger.info(
                            f"✅ Created document for {channel_day['channel_id']} on {channel_day['date']}"
                        )
                    return {"success": True, "doc": doc, "channel_day": channel_day}
                except Exception as e:
                    logger.error(
                        f"Failed to process {channel_day['channel_id']} on {channel_day['date']}: {e}",
                        exc_info=True,
                    )
                    return {"success": False, "error": e, "channel_day": channel_day}

        # Process all channel-days in parallel with limited concurrency
        results = await asyncio.gather(
            *[build_document_with_semaphore(channel_day) for channel_day in channel_days],
            return_exceptions=False,
        )

        # Separate successful documents from errors
        documents = []
        errors = []

        for result in results:
            if result["success"]:
                if result["doc"] is not None:
                    documents.append(result["doc"])
            else:
                errors.append(result)

        # If any errors occurred, raise an exception with details
        if errors:
            error_details = []
            for error_result in errors:
                channel_day = error_result["channel_day"]
                error_details.append(
                    f"{channel_day['channel_id']} on {channel_day['date']}: {error_result['error']}"
                )

            logger.error(
                "Failed to process channel-day(s)",
                n_errors=len(errors),
                error_details=error_details,
            )
            raise RuntimeError("Failed to process channel-day(s)")

        logger.info(f"Successfully created {len(documents)} documents")
        return documents

    async def _load_all_metadata(self, readonly_db_pool: asyncpg.Pool) -> None:
        """Load all metadata (users, channels, teams) using a single database query."""

        # Use single connection and query for better database efficiency
        # This is still really inefficient, especially for large tenants, but it's a start.
        # Using bigger index batch sizes will help mitigate this as well, as would properly filtering
        # to only the entities we need (harder).
        async with readonly_db_pool.acquire() as conn:
            artifacts = await conn.fetch(
                "SELECT * FROM ingest_artifact WHERE entity IN ('slack_user', 'slack_channel', 'slack_team')"
            )

        # Process all artifacts in a single pass
        metadata_counter: ErrorCounter = {}
        for artifact in artifacts:
            with record_exception_and_ignore(
                logger,
                f"Failed to process {artifact.get('entity', 'unknown')} artifact loaded from DB",
                metadata_counter,
            ):
                entity_type = artifact["entity"]
                content = artifact.get("content", {})
                if not content:
                    continue

                entity_id = content.get("id", artifact["entity_id"])

                if entity_type == "slack_user":
                    self._users_metadata[entity_id] = content
                elif entity_type == "slack_channel":
                    self._channels_metadata[entity_id] = content
                elif entity_type == "slack_team":
                    self._team_metadata[entity_id] = content

        # Build lookup maps
        self._build_user_map()
        self._build_channel_map()
        self._build_dm_map()

        metadata_successful = metadata_counter.get("successful", 0)
        metadata_failed = metadata_counter.get("failed", 0)

        logger.info(
            f"Loaded metadata: {len(self._users_metadata)} users, "
            f"{len(self._channels_metadata)} channels, {len(self._team_metadata)} teams "
            f"({metadata_successful} successful, {metadata_failed} failed)"
        )

    def _build_user_map(self) -> None:
        """Build user ID to username mapping."""
        for user_id, user_data in self._users_metadata.items():
            profile = user_data.get("profile", {})
            username = (
                profile.get("display_name")
                or profile.get("real_name")
                or user_data.get("real_name")
                or user_data.get("name")
                or user_id
            )
            self._user_map[user_id] = username

    def _build_channel_map(self) -> None:
        """Build channel ID to channel name mapping."""
        for channel_id, channel_data in self._channels_metadata.items():
            channel_name = channel_data.get("name", channel_id)
            self._channel_map[channel_id] = channel_name

    def _build_dm_map(self) -> None:
        """Build DM ID to participants mapping."""
        for channel_id, channel_data in self._channels_metadata.items():
            # Check if this is a DM (direct message) by looking for is_im flag
            if channel_data.get("is_im", False):
                members = channel_data.get("members", [])
                self._dm_participants_map[channel_id] = members
                logger.debug(f"Loaded DM {channel_id} with {len(members)} participants: {members}")

    async def _build_channel_day_document(
        self,
        channel_id: str,
        date: str,
        readonly_db_pool: asyncpg.Pool,
    ) -> SlackChannelDocument | None:
        """Build a document for a specific channel-day.

        Args:
            channel_id: The Slack channel ID
            date: The date in YYYY-MM-DD format
            readonly_db_pool: Database connection pool

        Returns:
            SlackChannelDocument or None if no messages found
        """
        channel_name = self._channel_map.get(channel_id, channel_id)

        # Convert date string to datetime.date object
        date_obj = date_type.fromisoformat(date)

        # Calculate timestamp bounds for efficient index usage
        start_of_day = datetime.combine(date_obj, datetime.min.time(), tzinfo=UTC)
        # Use start of next day to avoid floating-point precision issues with datetime.max.time()
        next_day = date_obj + timedelta(days=1)
        start_of_next_day = datetime.combine(next_day, datetime.min.time(), tzinfo=UTC)
        start_timestamp = start_of_day.timestamp()
        end_timestamp = start_of_next_day.timestamp()
        logger.info(
            f"Building document for {channel_name} ({channel_id}) on {date} (start_timestamp: {start_timestamp}, end_timestamp: {end_timestamp})"
        )

        async with readonly_db_pool.acquire() as conn:
            # Step 1: Get all messages for this channel-day
            day_messages = await conn.fetch(
                # IMPORTANT: we use `ts` bounds here (as opposed to something like `DATE(to_timestamp((content->>'ts')::float))`)
                # to ensure we use the `idx_slack_message_ts` index
                """
                SELECT * FROM ingest_artifact
                WHERE entity = 'slack_message'
                  AND metadata->>'channel_id' = $1
                  AND (content->>'ts')::float >= $2
                  AND (content->>'ts')::float < $3
                ORDER BY (content->>'ts')::float
                """,
                channel_id,
                start_timestamp,
                end_timestamp,
            )

            if not day_messages:
                logger.debug(f"No messages found for {channel_name} on {date}")
                return None

            # Step 2: Find thread roots that start on this day
            thread_roots = set()
            for msg in day_messages:
                content = msg.get("content", {})
                msg_ts = content.get("ts")
                thread_ts = content.get("thread_ts")

                # This is a thread root if it has no thread_ts or thread_ts equals ts
                if msg_ts and (not thread_ts or thread_ts == msg_ts):
                    thread_roots.add(msg_ts)

            # Step 3: Fetch ALL messages from threads that start on this day
            thread_messages = []
            if thread_roots:
                thread_messages = await conn.fetch(
                    """
                    SELECT * FROM ingest_artifact
                    WHERE entity = 'slack_message'
                      AND content->>'thread_ts' = ANY($1::text[])
                      AND content->>'ts' != content->>'thread_ts'
                    ORDER BY (content->>'ts')::float
                    """,
                    list(thread_roots),
                )
                logger.info(
                    f"Found {len(thread_messages)} thread replies for {len(thread_roots)} threads"
                )

            # Step 4: Process all messages
            all_message_artifacts = day_messages + thread_messages
            processed_messages = []

            # Find the latest source_updated_at from all artifacts
            latest_source_updated_at = None
            for artifact in all_message_artifacts:
                artifact_updated_at = artifact.get("source_updated_at")
                if artifact_updated_at and (
                    latest_source_updated_at is None
                    or artifact_updated_at > latest_source_updated_at
                ):
                    latest_source_updated_at = artifact_updated_at

            message_counter: ErrorCounter = {}
            for artifact in all_message_artifacts:
                with record_exception_and_ignore(
                    logger, "Failed to process message", message_counter
                ):
                    message = artifact.get("content", {})
                    if message:
                        message["channel_id"] = channel_id
                        processed_msg = self._process_message(message, channel_id)
                        if processed_msg:
                            processed_messages.append(processed_msg)

            # Log message processing results
            message_successful = message_counter.get("successful", 0)
            message_failed = message_counter.get("failed", 0)
            logger.debug(
                f"Message processing for {channel_name} on {date}: {message_successful} successful, {message_failed} failed, {len(processed_messages)} final messages"
            )

            # Deduplicate (in case some thread messages were already in day_messages)
            processed_messages = deduplicate_messages(processed_messages)

            # Add thread relationship placeholders if needed
            processed_messages = resolve_thread_relationships_with_placeholders(
                processed_messages, channel_id, channel_name
            )

            # Sort messages for display
            processed_messages = sort_messages_for_display(processed_messages)

            # Create document
            document_id = get_slack_doc_id(channel_id, date)

            # Get team info if available
            team_id = None
            team_domain = None
            if self._team_metadata:
                team_id, team_data = next(iter(self._team_metadata.items()))
                team_domain = team_data.get("domain", "")

            document_data = {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "date": date,
                "messages": processed_messages,
            }

            if team_id:
                document_data["team_id"] = team_id
            if team_domain:
                document_data["team_domain"] = team_domain

            # Use the latest source_updated_at, or fall back to the current time if none available
            source_updated_at = latest_source_updated_at or datetime.now(UTC)

            # Determine permissions based on whether this is a DM or public channel
            permission_policy: PermissionPolicy | None = None
            permission_allowed_tokens = None

            if channel_id.startswith("D"):
                permission_policy = "private"
                permission_allowed_tokens = self._get_dm_permission_tokens(channel_id)
                logger.info(
                    f"Set private permissions for DM {channel_id} with {len(permission_allowed_tokens) if permission_allowed_tokens else 0} participants"
                )
            else:
                permission_policy = "tenant"
                logger.debug(f"Set tenant permissions for public channel {channel_id}")

            return SlackChannelDocument(
                id=document_id,
                raw_data=document_data,
                source_updated_at=source_updated_at,
                permission_policy=permission_policy,
                permission_allowed_tokens=permission_allowed_tokens,
            )

    def _extract_text_from_blocks(self, blocks: list[dict[str, Any]] | None) -> str:
        """Extract text content from Slack blocks.

        Args:
            blocks: Slack blocks array

        Returns:
            Concatenated text from all section blocks
        """
        if not blocks:
            return ""

        texts = []
        for block in blocks:
            if block.get("type") == "section":
                block_text = block.get("text", {})
                if isinstance(block_text, dict) and block_text.get("text"):
                    texts.append(block_text["text"])

        return "\n".join(texts)

    def _process_message(self, message: dict[str, Any], channel_id: str) -> dict[str, Any] | None:
        """Process a single message."""
        try:
            user_id = message.get("user", "")
            text = message.get("text", "")
            blocks = message.get("blocks")
            ts = message.get("ts", "")

            if not ts:
                return None

            username = self._get_username(user_id)
            channel_name = self._channel_map.get(channel_id, channel_id)

            try:
                dt = datetime.fromtimestamp(float(ts), tz=UTC)
                formatted_time = format_pacific_time(ts)
                timestamp_iso = dt.isoformat()
                date = dt.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                logger.warning(f"Invalid timestamp: {ts}")
                return None

            # Extract text from blocks if available, otherwise use text field
            block_text = self._extract_text_from_blocks(blocks)
            message_text = block_text if block_text else text

            # Process message text
            cleaned_text = self._clean_slack_text(message_text)

            # Handle files
            files = message.get("files", [])
            if files:
                for file_info in files:
                    file_name = file_info.get("name", "Unknown file")
                    file_url = file_info.get("url_private", file_info.get("permalink", ""))
                    file_type = file_info.get("mimetype", file_info.get("filetype", "file"))

                    if file_info.get("mimetype", "").startswith("image/"):
                        cleaned_text += f" [Image: {file_name}]({file_url})"
                    else:
                        cleaned_text += f" [File: {file_name} ({file_type})]({file_url})"

            # Handle attachments
            attachments = message.get("attachments", [])
            if attachments:
                for attachment in attachments:
                    title = attachment.get("title", "")
                    title_link = attachment.get("title_link", "")
                    text_content = attachment.get("text", "")

                    if title and title_link:
                        cleaned_text += f" [{title}]({title_link})"
                    elif title:
                        cleaned_text += f" [Attachment: {title}]"
                    elif text_content:
                        cleaned_text += f" [Attachment: {text_content[:100]}...]"

            # Handle thread info
            thread_ts = message.get("thread_ts")
            parent_user_id = None
            parent_username = None

            if thread_ts and thread_ts != ts:
                parent_user_id = message.get("parent_user_id", "")
                if parent_user_id:
                    parent_username = self._get_username(parent_user_id)

            result = {
                "user_id": user_id,
                "username": username,
                "text": cleaned_text,
                "timestamp": timestamp_iso,
                "formatted_time": formatted_time,
                "message_ts": ts,
                "date": date,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "client_msg_id": message.get("client_msg_id", ""),
                "thread_ts": thread_ts,
                "parent_user_id": parent_user_id,
                "parent_username": parent_username,
            }

            # Add team info if available
            if self._team_metadata:
                team_id, team_data = next(iter(self._team_metadata.items()))
                team_domain = team_data.get("domain", "")
                if team_id:
                    result["team_id"] = team_id
                if team_domain:
                    result["team_domain"] = team_domain

            return result

        except Exception as e:
            logger.warning(f"Failed to process message: {e}")
            # Record exception to New Relic for individual message processing failures
            import newrelic.agent

            newrelic.agent.record_exception()
            return None

    def _get_username(self, user_id: str) -> str:
        """Get username for a user ID from cached user map."""
        if not user_id:
            return "unknown"
        return self._user_map.get(user_id, user_id)

    def _resolve_slack_mentions(self, text: str) -> str:
        """Resolve Slack user mentions from <@USER_ID> to <@USER_ID|@username> format."""
        if not text:
            return ""

        def replace_mention(match):
            user_id = match.group(1)
            username = self._user_map.get(user_id)
            if not username:
                return f"<@{user_id}>"
            return f"<@{user_id}|@{username}>"

        return self.MENTION_PATTERN.sub(replace_mention, text)

    def _resolve_slack_channels(self, text: str) -> str:
        """Resolve Slack channel mentions to <#CHANNEL_ID|#channel-name> format."""
        if not text:
            return ""

        def replace_channel(match):
            channel_id = match.group(1)
            channel_name = self._channel_map.get(channel_id)
            if not channel_name:
                return f"<#{channel_id}>"
            return f"<#{channel_id}|#{channel_name}>"

        return self.CHANNEL_PATTERN.sub(replace_channel, text)

    def _clean_slack_text(self, text: str) -> str:
        """Clean up Slack message text and resolve mentions."""
        if not text:
            return ""

        # Clean up whitespace
        text = " ".join(text.split())

        # Unescape HTML
        text = html.unescape(text)

        # Resolve mentions
        text = self._resolve_slack_mentions(text)
        text = self._resolve_slack_channels(text)

        return text

    def _get_user_email(self, user_id: str) -> str | None:
        """Get email address for a user ID.

        Args:
            user_id: The Slack user ID

        Returns:
            User email address or None if not found
        """
        user_data = self._users_metadata.get(user_id)
        if not user_data:
            return None

        # Try different email fields that might be available in Slack user data
        profile = user_data.get("profile", {})
        email = profile.get("email") or user_data.get("email")

        return email

    def _get_dm_permission_tokens(self, dm_id: str) -> list[str] | None:
        """Get permission tokens for DM participants using in-memory DM participants map.

        Args:
            dm_id: The DM channel ID

        Returns:
            List of permission tokens for DM participants, or None if no participants found
        """
        logger.debug(f"Getting DM permission tokens from memory for {dm_id}")

        # Get participants from the DM participants map
        members = self._dm_participants_map.get(dm_id, [])

        if not members:
            logger.warning(f"No DM participants found for {dm_id}")
            return None

        # Deduplicate members list to avoid duplicate permission tokens
        unique_members = list(set(members))
        if len(unique_members) != len(members):
            logger.debug(
                f"Deduplicated {len(members)} members to {len(unique_members)} for DM {dm_id}"
            )

        logger.debug(f"Found {len(unique_members)} unique members for DM {dm_id}: {unique_members}")

        # Convert user IDs to email addresses and then to permission tokens
        permission_tokens_set = set()  # Use set to automatically deduplicate
        for user_id in unique_members:
            user_email = self._get_user_email(user_id)
            if user_email:
                token = make_email_permission_token(user_email)
                permission_tokens_set.add(token)
                logger.debug(
                    f"Added permission token for user {user_id} ({user_email}) in DM {dm_id}"
                )
            else:
                logger.warning(f"No email found for user {user_id} in DM {dm_id}")

        if not permission_tokens_set:
            logger.warning(f"No valid permission tokens created for DM {dm_id}")
            return None

        permission_tokens = list(permission_tokens_set)
        logger.debug(f"Generated {len(permission_tokens)} unique permission tokens for DM {dm_id}")
        return permission_tokens
