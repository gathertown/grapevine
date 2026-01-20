import asyncio
import json
import random
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.clients.ssm import SSMClient
from src.utils.logging import get_logger

logger = get_logger(__name__)


class RateLimitExceeded(Exception):
    """Custom exception for rate limit errors."""

    pass


class GoogleEmailClient:
    DEFAULT_MAX_RETRIES = 5
    DEFAULT_BASE_DELAY = 1.0  # seconds
    DEFAULT_MAX_DELAY = 60.0  # seconds
    RETRYABLE_SERVER_ERRORS = [500, 502, 503, 504]  # Server errors that may be transient

    def __init__(
        self,
        tenant_id: str,
        admin_email: str | None = None,
        ssm_client: SSMClient | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
    ):
        """Initialize Google Email client with service account authentication.

        Args:
            tenant_id: Tenant identifier for credential retrieval
            admin_email: Admin email to impersonate for domain-wide delegation
            ssm_client: Optional SSM client instance for credential management
        """
        self.tenant_id = tenant_id
        self.admin_email = admin_email
        self.ssm_client = ssm_client or SSMClient()
        self._drive_service = None
        self._admin_service = None
        self._email_service = None
        self._credentials: service_account.Credentials | None = None
        # Extract domain from admin email if provided
        self._domain: str | None = admin_email.split("@")[1] if admin_email else None

        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def _get_credentials(self):
        """Get service account credentials with domain-wide delegation.

        Returns:
            Service account credentials

        Raises:
            ValueError: If no credentials found or invalid
        """
        if self._credentials:
            return self._credentials

        # Get tenant-specific service account from SSM
        service_account_json = await self.ssm_client.get_google_email_service_account(
            self.tenant_id
        )

        if not service_account_json:
            raise ValueError(
                f"No Google Drive service account found in SSM for tenant {self.tenant_id}"
            )

        logger.info(f"Using tenant-specific service account from SSM for tenant {self.tenant_id}")
        service_account_info = json.loads(service_account_json)

        # Create credentials with proper scopes
        scopes = [
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/admin.directory.user.readonly",
            "https://www.googleapis.com/auth/admin.directory.group.readonly",
        ]

        self._credentials = service_account.Credentials.from_service_account_info(
            service_account_info, scopes=scopes
        )

        # If admin email provided, use domain-wide delegation
        if self.admin_email and self._credentials:
            self._credentials = self._credentials.with_subject(self.admin_email)

        return self._credentials

    async def _get_email_service(self):
        """Get or create Google Email API service."""
        if not self._email_service:
            credentials = await self._get_credentials()
            self._email_service = build("gmail", "v1", credentials=credentials)
        return self._email_service

    async def _get_admin_service(self):
        """Get or create Google Admin SDK service.

        Returns:
            Google Admin SDK service instance
        """
        if not self._admin_service:
            if not self.admin_email:
                raise ValueError("Admin email required for Admin SDK operations")
            credentials = await self._get_credentials()
            self._admin_service = build("admin", "directory_v1", credentials=credentials)
        return self._admin_service

    async def _execute_with_retry(self, request, operation_name: str = "API call") -> Any:
        """Execute a Google API request with exponential backoff retry logic.

        Args:
            request: Google API request object
            operation_name: Description of the operation for logging

        Returns:
            API response

        Raises:
            RateLimitExceeded: If max retries exceeded due to rate limiting
            HttpError: For non-retryable errors
        """
        # Define which errors are retryable

        for attempt in range(self.max_retries):
            try:
                # Execute the request
                result = request.execute()

                # If successful after retries, log it
                if attempt > 0:
                    logger.info(f"{operation_name} succeeded after {attempt} retries")

                return result

            except HttpError as e:
                status_code = e.resp.status

                # Determine if this is a rate limit error
                is_rate_limit = status_code == 429

                # For 403 errors, check if it's specifically a rate limit issue
                if status_code == 403:
                    try:
                        error_content = json.loads(e.content.decode())
                        error_reason = (
                            error_content.get("error", {}).get("errors", [{}])[0].get("reason")
                        )
                        is_rate_limit = error_reason in [
                            "rateLimitExceeded",
                            "userRateLimitExceeded",
                            "quotaExceeded",
                        ]
                    except (json.JSONDecodeError, IndexError, KeyError, AttributeError):
                        # If we can't parse the error, default to treating 403 as not a rate limit
                        is_rate_limit = False

                # Check if this is a transient server error
                is_server_error = status_code in self.RETRYABLE_SERVER_ERRORS

                # Determine if we should retry
                should_retry = is_rate_limit or is_server_error

                if should_retry:
                    # Calculate delay with exponential backoff
                    delay = min(self.base_delay * (2**attempt), self.max_delay)

                    # Add jitter to prevent synchronized retries
                    jitter = random.uniform(0, delay * 0.1)
                    total_delay = delay + jitter

                    error_type = "rate limited" if is_rate_limit else "server error"
                    logger.warning(
                        f"{operation_name} {error_type} (attempt {attempt + 1}/{self.max_retries}). "
                        f"Status: {status_code}. Retrying in {total_delay:.2f}s..."
                    )

                    # Check if we have more retries
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(total_delay)
                        continue
                    else:
                        if is_rate_limit:
                            logger.error(
                                f"{operation_name} failed after {self.max_retries} retries due to rate limiting"
                            )
                            raise RateLimitExceeded(
                                f"Rate limit exceeded for {operation_name} after {self.max_retries} attempts"
                            ) from e
                        else:
                            logger.error(
                                f"{operation_name} failed after {self.max_retries} retries due to server errors"
                            )
                            raise  # Re-raise the original error
                else:
                    # Non-retryable error
                    logger.error(f"{operation_name} failed with status {status_code}: {e}")
                    raise

            except Exception as e:
                # Handle unexpected errors (network issues, etc.)
                logger.error(f"{operation_name} failed with unexpected error: {e}")

                # For certain errors like connection issues, we might want to retry
                is_connection_error = isinstance(e, (ConnectionError, TimeoutError))

                if is_connection_error and attempt < self.max_retries - 1:
                    delay = min(self.base_delay * (2**attempt), self.max_delay)
                    jitter = random.uniform(0, delay * 0.1)
                    total_delay = delay + jitter

                    logger.warning(
                        f"{operation_name} had connection error (attempt {attempt + 1}/{self.max_retries}). "
                        f"Retrying in {total_delay:.2f}s..."
                    )

                    await asyncio.sleep(total_delay)
                    continue
                else:
                    raise

    async def get_user_info_by_email(self, email: str) -> dict[str, Any] | None:
        """Get user info by email."""
        try:
            admin_service = await self._get_admin_service()
            get_user_request = admin_service.users().get(userKey=email)
            return await self._execute_with_retry(get_user_request, f"Get user info for {email}")
        except RateLimitExceeded:
            logger.error(f"Rate limit exceeded while getting user info for {email}")
            raise
        except HttpError as e:
            logger.error(f"Failed to get user info for {email}: {e}")
            return None

    async def list_users(self, max_results: int = 500) -> list[dict[str, Any]]:
        """List all users in the Google Workspace domain with rate limiting.

        Args:
            max_results: Maximum number of users per page

        Returns:
            List of user dictionaries
        """
        admin_service = await self._get_admin_service()
        all_users: list[dict[str, Any]] = []
        page_token = None

        try:
            while True:
                request = admin_service.users().list(
                    domain=self._domain,
                    maxResults=max_results,
                    pageToken=page_token,
                    orderBy="email",
                )
                results = await self._execute_with_retry(
                    request, f"List users (page {len(all_users) // max_results + 1})"
                )

                users = results.get("users", [])
                all_users.extend(users)

                page_token = results.get("nextPageToken")
                if not page_token:
                    break

            logger.info(f"Found {len(all_users)} users in domain {self._domain}")
            return all_users

        except RateLimitExceeded:
            logger.error("Rate limit exceeded while listing users")
            raise
        except HttpError as e:
            logger.error(f"Failed to list users: {e}")
            raise

    async def list_user_emails(
        self, user_id: str, query: str, page_token: str | None = None, max_results: int = 500
    ) -> dict[str, Any]:
        """List all emails for a user with rate limiting."""
        email_service = await self._get_email_service()

        try:
            request = (
                email_service.users()
                .messages()
                .list(
                    userId=user_id,
                    q=query,
                    maxResults=max_results,
                    pageToken=page_token,
                )
            )
            return await self._execute_with_retry(request, f"List emails for {user_id}")
        except RateLimitExceeded:
            logger.error(f"Rate limit exceeded while listing emails for {user_id}")
            raise
        except HttpError as e:
            logger.error(f"Failed to list user emails: {e}")
            raise

    async def get_new_emails(
        self, user_id: str, start_history_id: str, max_results: int = 500
    ) -> list[Any]:
        """Get new emails for a user with rate limiting."""
        next_page_token = None
        new_message_ids = []
        email_service = await self._get_email_service()

        try:
            while True:
                request = (
                    email_service.users()
                    .history()
                    .list(
                        userId=user_id,
                        startHistoryId=start_history_id,
                        historyTypes=["messageAdded"],
                        maxResults=max_results,
                        pageToken=next_page_token,
                    )
                )
                history = await self._execute_with_retry(request, f"Get history for {user_id}")

                changes = history.get("history", [])
                for change in changes:
                    if "messagesAdded" in change:
                        for message_added in change["messagesAdded"]:
                            new_message_ids.append(message_added["message"]["id"])

                next_page_token = history.get("nextPageToken")
                if not next_page_token:
                    break

            return new_message_ids

        except RateLimitExceeded:
            logger.error(f"Rate limit exceeded while getting new emails for {user_id}")
            raise

    async def get_email(
        self, user_id: str, message_id: str, format: str = "full"
    ) -> dict[str, Any]:
        """Get a single email with rate limiting."""
        try:
            email_service = await self._get_email_service()
            request = (
                email_service.users().messages().get(userId=user_id, id=message_id, format=format)
            )
            message = await self._execute_with_retry(
                request, f"Get email {message_id} for {user_id}"
            )
            return (
                self.extract_email_info(message)
                | self.extract_email_body(message)
                | {"raw": message}
            )
        except RateLimitExceeded:
            logger.error(f"Rate limit exceeded while getting email {message_id}")
            raise
        except Exception as e:
            logger.error(f"Failed to get email: {e}")
            raise

    async def get_emails_batch(
        self, user_id: str, message_ids: list[str], format: str = "full"
    ) -> list[dict[str, Any] | Exception]:
        """Get multiple emails using Gmail API batch request.
        Args:
            user_id: User ID (typically "me")
            message_ids: List of message IDs to fetch
            format: Message format (full, metadata, minimal, raw)
        Returns:
            List of email data dictionaries or exceptions for failed requests
        """
        email_service = await self._get_email_service()
        results: list[dict[str, Any] | Exception] = [None] * len(message_ids)  # type: ignore[list-item]

        def create_callback(index: int):
            """Create a callback for batch request that captures the index."""

            def callback(_request_id, response, exception):
                if exception:
                    logger.error(f"Failed to get email {message_ids[index]}: {exception}")
                    results[index] = exception
                else:
                    try:
                        results[index] = (
                            self.extract_email_info(response)
                            | self.extract_email_body(response)
                            | {"raw": response}
                        )
                    except Exception as e:
                        logger.error(f"Failed to process email {message_ids[index]}: {e}")
                        results[index] = e

            return callback

        # Create batch request
        batch = email_service.new_batch_http_request()
        for i, message_id in enumerate(message_ids):
            batch.add(
                email_service.users().messages().get(userId=user_id, id=message_id, format=format),
                callback=create_callback(i),
                request_id=str(i),
            )

        try:
            await self._execute_with_retry(batch, f"Get emails batch for {user_id}")
        except RateLimitExceeded:
            logger.error(f"Rate limit exceeded while getting email {message_id}")
            raise
        except Exception as e:
            logger.error(f"Failed to get email: {e}")
            raise

        return results

    def extract_email_info(self, message: dict[str, Any]) -> dict[str, Any]:
        """Extract useful information from a Gmail message object.

        Args:
            message: Gmail message object from API

        Returns:
            Dictionary with extracted email information
        """
        headers = message.get("payload", {}).get("headers", [])

        # Extract common headers
        email_info = {
            "id": message.get("id"),
            "thread_id": message.get("threadId"),
            "snippet": message.get("snippet", ""),
            "size_estimate": message.get("sizeEstimate", 0),
            "internal_date": message.get("internalDate"),
            "labels": message.get("labelIds", []),
            "date": "",
            "from": "",
            "to": "",
            "cc": "",
            "bcc": "",
            "subject": "",
            "message_id": "",
            "in_reply_to": "",
            "references": "",
        }

        # Parse headers
        for header in headers:
            name = header["name"].lower()
            value = header["value"]

            if name == "from":
                email_info["from"] = value
            elif name == "to":
                email_info["to"] = value
            elif name == "cc":
                email_info["cc"] = value
            elif name == "bcc":
                email_info["bcc"] = value
            elif name == "subject":
                email_info["subject"] = value
            elif name == "date":
                email_info["date"] = value
            elif name == "message-id":
                email_info["message_id"] = value
            elif name == "in-reply-to":
                email_info["in_reply_to"] = value
            elif name == "references":
                email_info["references"] = value

        return email_info

    def extract_email_body(self, message: dict[str, Any]) -> dict[str, str]:
        """Extract email body content from a Gmail message.

        Args:
            message: Gmail message object from API

        Returns:
            Dictionary with 'text' and 'html' body content
        """

        def decode_data(data: str) -> str:
            """Decode base64url encoded data."""
            import base64

            # Add padding if needed
            missing_padding = len(data) % 4
            if missing_padding:
                data += "=" * (4 - missing_padding)
            # Replace URL-safe characters
            data = data.replace("-", "+").replace("_", "/")
            return base64.b64decode(data).decode("utf-8", errors="ignore")

        def extract_parts(payload: dict) -> dict[str, str]:
            """Recursively extract text and HTML parts."""
            body_content = {"text": "", "html": ""}

            if "parts" in payload:
                # Multi-part message
                for part in payload["parts"]:
                    part_content = extract_parts(part)
                    if part_content["text"]:
                        body_content["text"] += part_content["text"] + "\n"
                    if part_content["html"]:
                        body_content["html"] += part_content["html"]
            else:
                # Single part message
                mime_type = payload.get("mimeType", "")
                body = payload.get("body", {})
                data = body.get("data", "")

                if data:
                    decoded_data = decode_data(data)
                    if "text/plain" in mime_type:
                        body_content["text"] = decoded_data
                    elif "text/html" in mime_type:
                        body_content["html"] = decoded_data

            return body_content

        payload = message.get("payload", {})
        return extract_parts(payload)

    async def impersonate_user(self, user_email: str) -> "GoogleEmailClient":
        """Create a new client instance that impersonates a specific user.

        Args:
            user_email: Email of the user to impersonate

        Returns:
            New GoogleEmailClient instance with user impersonation
        """
        return GoogleEmailClient(
            tenant_id=self.tenant_id, admin_email=user_email, ssm_client=self.ssm_client
        )

    async def get_start_page_token(self) -> str:
        """Get start page token for changes API.

        Returns:
            Start page token for changes tracking

        Raises:
            HttpError: If API call fails
        """
        try:
            email_service = await self._get_email_service()
            request = email_service.users().messages().list(userId="me", q="label:UNREAD")
            return await self._execute_with_retry(request, "Get start page token")
        except RateLimitExceeded:
            logger.error("Rate limit exceeded while getting start page token")
            raise
        except HttpError as e:
            logger.error(f"Failed to get start page token: {e}")
            raise

    async def create_watch(self, topic_name: str) -> dict[str, Any]:
        """Create a watch channel for changes API."""
        try:
            email_service = await self._get_email_service()

            watch_config = {
                "topicName": topic_name,
                "labelIds": ["INBOX", "SENT"],
            }

            email_watch = email_service.users().watch(userId="me", body=watch_config)
            return await self._execute_with_retry(email_watch, "Create watch channel")
        except RateLimitExceeded:
            logger.error(f"Rate limit exceeded while creating watch channel for {topic_name}")
            raise
        except HttpError as e:
            logger.error(f"Failed to create watch channel for {topic_name}: {e}")
            raise

    async def stop_all_watches(self):
        """Stop all watches for a user."""
        try:
            email_service = await self._get_email_service()
            stop_watch = email_service.users().stop(userId="me")
            await self._execute_with_retry(stop_watch, "Stop all watches")
            logger.info(f"Stopped all watches for user {self.admin_email}")
        except RateLimitExceeded:
            logger.error(f"Rate limit exceeded while stopping all watches for {self.admin_email}")
            raise
        except HttpError as e:
            logger.error(f"Failed to stop all watches for {self.admin_email}: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to stop all watches for {self.admin_email}: {e}")
            raise


def parse_email_addresses(email_str: str) -> list[str]:
    """
    Advanced email parsing that handles names with emails

    Args:
        email_str: Email string that might include names like "John Doe <john@example.com>, jane@example.com"

    Returns:
        List of cleaned email addresses
    """
    import re

    if not email_str or not email_str.strip():
        return []

    # Regular expression to extract email addresses from strings like "Name <email@domain.com>"
    email_pattern = r"<([^>]+)>|([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"

    emails = []

    # Split by comma first
    parts = email_str.split(",")

    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Try to extract email using regex
        matches = re.findall(email_pattern, part)

        if matches:
            # Extract the non-empty group from the match
            for match in matches:
                email = match[0] if match[0] else match[1]
                if email:
                    emails.append(email.strip())
        else:
            # If no regex match, assume the whole part is an email
            emails.append(part)

    return emails
