"""Slack client utility for interacting with Slack API."""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.rate_limiter import RateLimitedError, rate_limited
from src.utils.ttl_cache import ttl_cache


class SlackClient:
    """A client for interacting with the Slack API."""

    def __init__(self, token: str):
        """Initialize the Slack client.

        Args:
            token: Slack bot token (required).

        Raises:
            ValueError: If token is empty
        """
        if not token:
            raise ValueError("Slack token is required and cannot be empty")

        self.client = WebClient(token=token)
        self._token = token

    @rate_limited()
    def auth_test(self) -> dict[str, Any]:
        """Test authentication and get bot info.

        Returns:
            Dictionary with authentication info including user and team
        """
        try:
            response = self.client.auth_test()
            return response.data  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
        except SlackApiError as e:
            error = e.response.get("error", "")
            if error in ("rate_limited", "ratelimited"):
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise RateLimitedError(retry_after=retry_after)
            raise

    @rate_limited()
    def get_conversation_history(
        self,
        channel_id: str,
        limit: int | None = None,
        oldest: str | None = None,
        latest: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Get messages from a Slack channel.

        Args:
            channel_id: ID of the channel
            limit: Maximum number of messages to fetch
            oldest: Only messages after this timestamp
            latest: Only messages before this timestamp

        Yields:
            Message dictionaries
        """
        kwargs = {
            "channel": channel_id,
            "limit": 100,  # Max per page
        }

        if oldest:
            kwargs["oldest"] = oldest
        if latest:
            kwargs["latest"] = latest

        message_count = 0

        try:
            while True:
                response = self.client.conversations_history(**kwargs)  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

                if not response.get("messages"):
                    break

                for message in response.get("messages", []):  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                    yield message
                    message_count += 1

                    if limit and message_count >= limit:
                        return

                # Check if there are more messages
                if not response.get("has_more", False):
                    break

                # Set cursor for next page
                next_cursor = response.get("response_metadata", {}).get("next_cursor")  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                if not next_cursor:
                    break
                kwargs["cursor"] = next_cursor

        except SlackApiError as e:
            error = e.response.get("error", "")
            if error == "channel_not_found":
                raise ValueError(f"Channel {channel_id} not found")
            elif error in ("rate_limited", "ratelimited"):
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise RateLimitedError(retry_after=retry_after)
            raise

    @rate_limited()
    @ttl_cache(ttl=900)  # Cache for 15 minutes
    def get_channel_info(self, channel_id: str) -> dict[str, Any]:
        """Get information about a Slack channel.

        Args:
            channel_id: ID of the channel

        Returns:
            Channel information dictionary

        Raises:
            ValueError: If channel not found
            SlackApiError: If API error
        """
        try:
            response = self.client.conversations_info(channel=channel_id)
            return response.get("channel", {})
        except SlackApiError as e:
            error = e.response.get("error", "")
            if error == "channel_not_found":
                raise ValueError(f"Channel {channel_id} not found")
            elif error in ("rate_limited", "ratelimited"):
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise RateLimitedError(retry_after=retry_after)
            raise

    @rate_limited()
    @ttl_cache(ttl=900)  # Cache for 15 minutes
    def get_user_info(self, user_id: str) -> dict[str, Any] | None:
        """Get information about a Slack user.

        Args:
            user_id: ID of the user

        Returns:
            User information dictionary or None if not found
        """
        try:
            response = self.client.users_info(user=user_id)
            return response.get("user")
        except SlackApiError as e:
            error = e.response.get("error", "")
            if error in ("rate_limited", "ratelimited"):
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise RateLimitedError(retry_after=retry_after)
            # Return None for user not found or other errors
            return None

    @rate_limited()
    def list_channels(
        self, types: str = "public_channel,private_channel", exclude_archived: bool = True
    ) -> list[dict[str, Any]]:
        """List all channels accessible to the bot.

        Args:
            types: Comma-separated channel types
            exclude_archived: Whether to exclude archived channels

        Returns:
            List of channel dictionaries
        """
        channels = []
        kwargs = {
            "types": types,
            "exclude_archived": exclude_archived,
            "limit": 100,
        }

        try:
            while True:
                response = self.client.conversations_list(**kwargs)  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                response_channels = response.get("channels", [])  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                if response_channels:
                    channels.extend(response_channels)

                next_cursor = response.get("response_metadata", {}).get("next_cursor")  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                if not next_cursor:
                    break

                kwargs["cursor"] = next_cursor

        except SlackApiError as e:
            error = e.response.get("error", "")
            if error in ("rate_limited", "ratelimited"):
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise RateLimitedError(retry_after=retry_after)
            raise

        return channels

    @rate_limited()
    def list_users(self, include_deleted: bool = False) -> list[dict[str, Any]]:
        """List all users in the workspace.

        Args:
            include_deleted: Whether to include deleted users

        Returns:
            List of user dictionaries
        """
        users = []
        kwargs = {
            "limit": 100,
        }

        try:
            while True:
                response = self.client.users_list(**kwargs)  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                response_users = response.get("members", [])  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

                if response_users:
                    # Filter out deleted users if requested
                    if not include_deleted:
                        response_users = [
                            user for user in response_users if not user.get("deleted", False)
                        ]
                    users.extend(response_users)

                next_cursor = response.get("response_metadata", {}).get("next_cursor")  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                if not next_cursor:
                    break

                kwargs["cursor"] = next_cursor

        except SlackApiError as e:
            error = e.response.get("error", "")
            if error in ("rate_limited", "ratelimited"):
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise RateLimitedError(retry_after=retry_after)
            raise

        return users

    @rate_limited()
    def get_conversation_replies(self, channel_id: str, message_ts: str):
        """Get replies to a specific message in a thread.

        Args:
            channel_id: ID of the channel
            message_ts: Timestamp of the parent message

        Returns:
            Dictionary containing thread messages

        Raises:
            ValueError: If channel/message not found
            SlackApiError: If API error
        """
        try:
            response = self.client.conversations_replies(channel=channel_id, ts=message_ts)
            return response
        except SlackApiError as e:
            error = e.response.get("error", "")
            if error == "channel_not_found":
                raise ValueError(f"Channel {channel_id} not found")
            elif error == "thread_not_found":
                raise ValueError(f"Thread {message_ts} not found in channel {channel_id}")
            elif error in ("rate_limited", "ratelimited"):
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise RateLimitedError(retry_after=retry_after)
            raise

    @rate_limited()
    def get_team_info(self) -> dict[str, Any]:
        """Get information about the Slack workspace/team.

        Returns:
            Team information dictionary

        Raises:
            SlackApiError: If API error
        """
        try:
            response = self.client.team_info()
            return response.get("team", {})
        except SlackApiError as e:
            error = e.response.get("error", "")
            if error in ("rate_limited", "ratelimited"):
                retry_after = int(e.response.headers.get("Retry-After", 60))
                raise RateLimitedError(retry_after=retry_after)
            raise
