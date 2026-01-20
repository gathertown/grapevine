#!/usr/bin/env python
"""Create test conversations in Intercom for development/testing purposes.

Usage:
    uv run python scripts/intercom/create_intercom_test_conversations.py \\
        --access-token <token> --count 5

This script creates random test conversations with messages in Intercom.
Useful for testing the ingestion pipeline when you don't have real conversation data.

WARNING: This will create real conversations in your Intercom workspace!
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from types import TracebackType
from typing import Any

import httpx

INTERCOM_API_BASE = "https://api.intercom.io"

# Path to sample data JSON file
SCRIPT_DIR = Path(__file__).parent
SAMPLE_DATA_FILE = SCRIPT_DIR / "intercom_sample_data.json"


def load_sample_data() -> dict[str, Any]:
    """Load sample data from JSON file.

    Returns:
        Dictionary with 'topics', 'customer_messages', and 'support_responses' lists

    Raises:
        FileNotFoundError: If the sample data file doesn't exist
        json.JSONDecodeError: If the JSON file is invalid
    """
    if not SAMPLE_DATA_FILE.exists():
        raise FileNotFoundError(
            f"Sample data file not found: {SAMPLE_DATA_FILE}. "
            "Please ensure intercom_sample_data.json exists in the same directory."
        )

    with open(SAMPLE_DATA_FILE) as f:
        data = json.load(f)

    # Validate structure
    required_keys = ["topics", "customer_messages", "support_responses"]
    for key in required_keys:
        if key not in data:
            raise ValueError(f"Sample data file missing required key: {key}")

    if not isinstance(data["topics"], list) or len(data["topics"]) == 0:
        raise ValueError("Sample data 'topics' must be a non-empty list")
    if not isinstance(data["customer_messages"], list) or len(data["customer_messages"]) == 0:
        raise ValueError("Sample data 'customer_messages' must be a non-empty list")
    if not isinstance(data["support_responses"], list) or len(data["support_responses"]) == 0:
        raise ValueError("Sample data 'support_responses' must be a non-empty list")

    return data


class IntercomClassicClient:
    """Tiny helper around the Intercom REST API."""

    def __init__(self, access_token: str, timeout: float = 15.0) -> None:
        token = (access_token or "").strip()
        if not token:
            raise ValueError("Intercom access token is required")

        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "intercom-classic-scripts/0.1",
            "Intercom-Version": "2.10",
        }
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> IntercomClassicClient:
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _tb: TracebackType | None,
    ) -> None:
        self.close()

    def get_me(self) -> dict[str, Any]:
        """Get current admin/app information."""
        return self._request("GET", "/me")

    def create_or_find_contact(self, email: str, name: str | None = None) -> dict[str, Any]:
        """Create a contact or find existing one by email.

        Args:
            email: Contact email address
            name: Optional contact name

        Returns:
            Contact data with ID and type
        """
        # Try to find existing contact first using POST /contacts/search
        try:
            search_body = {
                "query": {
                    "field": "email",
                    "operator": "=",
                    "value": email,
                }
            }
            response = self._request("POST", "/contacts/search", json=search_body)
            contacts = response.get("data", [])
            if contacts and len(contacts) > 0:
                contact = contacts[0]
                # Ensure type is set
                if "type" not in contact:
                    contact["type"] = "contact"
                return contact
        except Exception:
            # Contact doesn't exist, will create it
            pass

        # Create new contact
        body: dict[str, Any] = {"email": email}
        if name:
            body["name"] = name

        response = self._request("POST", "/contacts", json=body)
        # Intercom API returns contact in different formats, normalize it
        contact = response
        if "contact" in response:
            contact = response["contact"]

        # Ensure type is set - use role if available, otherwise default to "contact"
        if "type" not in contact:
            # If contact has role "user", use "user" as type for conversation creation
            if contact.get("role") == "user":
                contact["type"] = "user"
            else:
                contact["type"] = "contact"

        return contact

    def create_conversation(
        self,
        *,
        from_contact: dict[str, Any],
        message_body: str,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """Create a new conversation from a contact.

        Args:
            from_contact: Contact creating the conversation (must have 'id' and 'type')
            message_body: Initial message body
            subject: Optional conversation subject/title

        Returns:
            Created conversation data
        """
        # Extract only the required fields for the "from" object
        contact_id = from_contact.get("id")
        contact_type = from_contact.get("type", "contact")

        if not contact_id:
            raise ValueError("Contact must have an 'id' field")

        body: dict[str, Any] = {
            "from": {
                "type": contact_type,
                "id": contact_id,
            },
            "body": message_body,
        }
        if subject:
            body["subject"] = subject

        return self._request("POST", "/conversations", json=body)

    def create_conversation_part(
        self,
        conversation_id: str,
        *,
        message_body: str,
        author_type: str = "admin",
        author_id: str | None = None,
    ) -> dict[str, Any]:
        """Add a message/part to an existing conversation.

        Args:
            conversation_id: The conversation ID
            message_body: Message content
            author_type: Type of author ("admin", "user", "contact")
            author_id: Author ID (if None, uses current admin)

        Returns:
            Created conversation part data
        """
        if author_id is None and author_type == "admin":
            author_id = self._get_admin_id()

        # Intercom API requires the admin ID in the "from" field for replies
        # The "ID is required" error suggests the from.id is missing or invalid
        if not author_id:
            raise ValueError("Admin ID is required for creating conversation parts")

        # Try the reply endpoint with proper format
        body: dict[str, Any] = {
            "type": "admin",
            "message_type": "comment",
            "body": message_body,
            "from": {
                "type": "admin",
                "id": str(author_id),  # Ensure it's a string
            },
        }

        # Try the reply endpoint first
        try:
            return self._request("POST", f"/conversations/{conversation_id}/reply", json=body)
        except Exception as e:
            # If reply endpoint fails, try the parts endpoint with different format
            error_msg = str(e)
            if "404" in error_msg or "not_found" in error_msg.lower():
                # Try alternative: create a conversation part directly
                body_alt: dict[str, Any] = {
                    "type": "admin",
                    "body": message_body,
                    "admin_id": str(author_id),
                }
                try:
                    return self._request(
                        "POST", f"/conversations/{conversation_id}/parts", json=body_alt
                    )
                except Exception:
                    # Re-raise original error if both fail
                    raise e
            elif "400" in error_msg and "id" in error_msg.lower():
                # If we get "ID is required" error, try without the "from" wrapper
                body_simple: dict[str, Any] = {
                    "type": "admin",
                    "message_type": "comment",
                    "body": message_body,
                    "admin_id": str(author_id),
                }
                try:
                    return self._request(
                        "POST", f"/conversations/{conversation_id}/reply", json=body_simple
                    )
                except Exception:
                    raise e
            else:
                raise

    def _get_admin_id(self) -> str:
        """Get the current admin ID, caching it."""
        if not hasattr(self, "_cached_admin_id"):
            me = self.get_me()
            self._cached_admin_id = me.get("id") or me.get("app", {}).get("id")
            if not self._cached_admin_id:
                raise ValueError("Could not determine admin ID from /me endpoint")
        return self._cached_admin_id

    def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        response = self._client.request(
            method,
            f"{INTERCOM_API_BASE}{path}",
            headers=self._headers,
            json=json,
            **kwargs,
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - script only
            body = exc.response.text
            raise RuntimeError(
                f"Intercom API request failed: {exc.response.status_code} {body}"
            ) from exc

        # Handle empty responses
        if not response.content:
            return {}

        return response.json()


def generate_test_contact_email(index: int) -> tuple[str, str]:
    """Generate a test contact email and name.

    Args:
        index: Contact index number

    Returns:
        Tuple of (email, name)
    """
    name = f"Test User {index}"
    email = f"test-user-{index}@example.com"
    return email, name


def generate_test_conversation(
    index: int, contact: dict[str, Any], sample_data: dict[str, Any]
) -> dict[str, Any]:
    """Generate a test conversation payload.

    Args:
        index: Conversation index number
        contact: Contact dictionary with 'id' and 'type'
        sample_data: Dictionary with 'topics' and 'customer_messages' lists

    Returns:
        Conversation payload dictionary
    """
    topic = random.choice(sample_data["topics"])
    initial_message = random.choice(sample_data["customer_messages"])

    return {
        "from_contact": contact,
        "subject": f"Test Conversation {index}: {topic}",
        "body": initial_message,
    }


def generate_test_message(sample_data: dict[str, Any]) -> str:
    """Generate a test message/response.

    Args:
        sample_data: Dictionary with 'support_responses' list

    Returns:
        Random support response message
    """
    return random.choice(sample_data["support_responses"])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create test conversations in Intercom",
    )
    parser.add_argument(
        "--access-token",
        help="Intercom classic access token (falls back to INTERCOM_ACCESS_TOKEN env var)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=5,
        help="Number of conversations to create (default: 5)",
    )
    parser.add_argument(
        "--messages-per-conversation",
        type=int,
        default=2,
        help="Number of messages to add to each conversation (default: 2)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between API calls in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="HTTP timeout in seconds (default: 15)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without actually creating conversations",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    access_token = args.access_token or os.environ.get("INTERCOM_ACCESS_TOKEN", "")

    if not access_token:
        print(
            "Error: provide --access-token or set INTERCOM_ACCESS_TOKEN in the environment.",
            file=sys.stderr,
        )
        return 1

    # Load sample data
    try:
        sample_data = load_sample_data()
        print(
            f"✅ Loaded sample data: {len(sample_data['topics'])} topics, "
            f"{len(sample_data['customer_messages'])} customer messages, "
            f"{len(sample_data['support_responses'])} support responses\n",
            file=sys.stderr,
        )
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"Error loading sample data: {e}", file=sys.stderr)
        return 1

    try:
        with IntercomClassicClient(access_token, timeout=args.timeout) as client:
            # Get admin ID
            try:
                me = client.get_me()
                admin_id = me.get("id") or me.get("app", {}).get("id")
                if not admin_id:
                    print("Error: Could not determine admin ID", file=sys.stderr)
                    return 1
                print(f"✅ Using admin ID: {admin_id}\n", file=sys.stderr)
            except Exception as e:
                print(f"Error getting admin info: {e}", file=sys.stderr)
                return 1

            if args.dry_run:
                print(f"DRY RUN: Would create {args.count} conversation(s)\n", file=sys.stderr)
                for i in range(1, args.count + 1):
                    email, name = generate_test_contact_email(i)
                    # Create a mock contact for dry run
                    mock_contact = {
                        "id": f"mock-{i}",
                        "type": "contact",
                        "email": email,
                        "name": name,
                    }
                    conv = generate_test_conversation(i, mock_contact, sample_data)
                    print(f"Conversation {i}:", file=sys.stderr)
                    print(f"  Contact: {name} ({email})", file=sys.stderr)
                    print(f"  Subject: {conv.get('subject')}", file=sys.stderr)
                    print(f"  Initial message: {conv.get('body')[:50]}...", file=sys.stderr)
                    print(
                        f"  Would add {args.messages_per_conversation} additional message(s)",
                        file=sys.stderr,
                    )
                    print("", file=sys.stderr)
                return 0

            created_conversations = []

            for i in range(1, args.count + 1):
                try:
                    # Create or find test contact
                    email, name = generate_test_contact_email(i)
                    print(
                        f"Creating/finding contact for conversation {i}/{args.count}...",
                        file=sys.stderr,
                    )
                    try:
                        contact = client.create_or_find_contact(email, name)
                        contact_id = contact.get("id")
                        # Use role as type if available, otherwise use type field
                        contact_role = contact.get("role")
                        contact_type = contact.get("type", "contact")
                        # If role is "user", use "user" as the type for conversation creation
                        if contact_role == "user":
                            contact_type = "user"
                        if not contact_id:
                            print(
                                f"⚠️  Warning: Could not get contact ID, skipping conversation {i}",
                                file=sys.stderr,
                            )
                            print(
                                f"   Contact response: {json.dumps(contact, indent=2)}",
                                file=sys.stderr,
                            )
                            continue
                        print(
                            f"  ✅ Using contact: {contact.get('name', name)} ({email})",
                            file=sys.stderr,
                        )
                        print(
                            f"     Contact ID: {contact_id}, Type: {contact_type}, Role: {contact_role}",
                            file=sys.stderr,
                        )
                    except Exception as e:
                        print(f"⚠️  Failed to create/find contact: {e}", file=sys.stderr)
                        continue

                    # Wait a bit for contact to be fully created/indexed
                    time.sleep(max(args.delay, 0.5))  # At least 0.5s delay

                    # Generate conversation data
                    conv_data = generate_test_conversation(i, contact, sample_data)

                    print(f"Creating conversation {i}/{args.count}...", file=sys.stderr)
                    print(f"  Subject: {conv_data.get('subject')}", file=sys.stderr)
                    print(f"  From contact ID: {contact_id}, Type: {contact_type}", file=sys.stderr)

                    # Create conversation - use minimal contact reference
                    # Intercom API expects just type and id in the "from" field
                    conversation = client.create_conversation(
                        from_contact={"id": contact_id, "type": contact_type},
                        message_body=conv_data["body"],
                        subject=conv_data.get("subject"),
                    )

                    # The response has both 'id' (message ID) and 'conversation_id' (conversation ID)
                    # We need to use 'conversation_id' for adding messages
                    conv_id = conversation.get("conversation_id")
                    if not conv_id:
                        # Fallback to nested format
                        conv_id = conversation.get("conversation", {}).get("id")
                    if not conv_id:
                        # Last resort: try the top-level id (but this is usually the message ID)
                        conv_id = conversation.get("id")
                        print(
                            "  ⚠️  Warning: Using 'id' field as conversation ID (might be message ID)",
                            file=sys.stderr,
                        )
                    if not conv_id:
                        print(
                            "⚠️  Warning: Could not get conversation ID from response",
                            file=sys.stderr,
                        )
                        print(f"   Response: {json.dumps(conversation, indent=2)}", file=sys.stderr)
                        continue

                    # Log full conversation response for debugging
                    print(f"  ✅ Created conversation: {conv_id}", file=sys.stderr)
                    if "conversation_id" in conversation:
                        print("     Using conversation_id from response", file=sys.stderr)
                    else:
                        print(
                            f"     Full response keys: {list(conversation.keys())}", file=sys.stderr
                        )

                    # Wait a bit for conversation to be fully created/indexed before adding messages
                    time.sleep(max(args.delay, 1.0))  # At least 1s delay after creation

                    # Add additional messages
                    for msg_num in range(1, args.messages_per_conversation + 1):
                        time.sleep(args.delay)  # Rate limiting
                        message_body = generate_test_message(sample_data)
                        try:
                            print(
                                f"  Attempting to add message {msg_num} to conversation {conv_id}...",
                                file=sys.stderr,
                            )
                            client.create_conversation_part(
                                conv_id,
                                message_body=message_body,
                                author_type="admin",
                            )
                            print(
                                f"  ✅ Added message {msg_num}/{args.messages_per_conversation}",
                                file=sys.stderr,
                            )
                        except Exception as e:
                            error_str = str(e)
                            print(
                                f"  ⚠️  Failed to add message {msg_num}: {error_str}",
                                file=sys.stderr,
                            )
                            # If it's a 404, the conversation might not be ready yet or endpoint is wrong
                            if "404" in error_str or "not_found" in error_str.lower():
                                print(
                                    "     This might indicate the conversation ID format is wrong or endpoint doesn't exist",
                                    file=sys.stderr,
                                )
                            # Continue with next message even if one fails
                            continue

                    created_conversations.append(conv_id)
                    time.sleep(args.delay)  # Rate limiting between conversations

                except Exception as e:
                    print(f"⚠️  Failed to create conversation {i}: {e}", file=sys.stderr)
                    continue

            print(
                f"\n✅ Successfully created {len(created_conversations)} conversation(s)",
                file=sys.stderr,
            )
            if created_conversations:
                print("\nCreated conversation IDs:", file=sys.stderr)
                for conv_id in created_conversations:
                    print(f"  - {conv_id}", file=sys.stderr)

    except Exception as exc:  # pragma: no cover - script only
        print(f"Failed to create conversations: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
