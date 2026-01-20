#!/usr/bin/env python
"""
Script to send test messages to SQS indexing queue.
Matches the pattern used in the admin backend's SQS client.
"""

import json
import os
import sys

import boto3


def arn_to_queue_url(queue_identifier: str) -> str:
    """
    Convert various queue identifiers into a queue URL expected by AWS SDK.
    Matches the TypeScript implementation in admin-backend/src/jobs/sqs-client.ts
    """
    # Already a full URL
    if queue_identifier.startswith("https://"):
        return queue_identifier

    # ARN format: arn:aws:sqs:<region>:<account-id>:<queue-name>
    if queue_identifier.startswith("arn:"):
        parts = queue_identifier.split(":")
        if len(parts) != 6 or parts[0] != "arn" or parts[1] != "aws" or parts[2] != "sqs":
            raise ValueError(f"Invalid SQS ARN format: {queue_identifier}")
        arn_region = parts[3]
        arn_account_id = parts[4]
        queue_name = parts[5]
        return f"https://sqs.{arn_region}.amazonaws.com/{arn_account_id}/{queue_name}"

    # Plain queue name support
    region: str | None = os.environ.get("AWS_REGION")
    account_id: str | None = os.environ.get("AWS_ACCOUNT_ID")
    if not region or not account_id:
        raise ValueError(
            f"Cannot resolve queue URL from plain name '{queue_identifier}' "
            "without AWS_REGION and AWS_ACCOUNT_ID environment variables"
        )
    # After the None check, we know these are strings
    assert region is not None and account_id is not None
    return f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_identifier}"


def create_sqs_client():
    """
    Create SQS client following the same pattern as admin backend.
    """
    region: str | None = os.environ.get("AWS_REGION")
    endpoint_url: str | None = os.environ.get("AWS_ENDPOINT_URL")

    config = {}
    if region:
        config["region_name"] = region
    if endpoint_url:
        config["endpoint_url"] = endpoint_url
        print(f"SQS client configured for LocalStack at {endpoint_url}")

    return boto3.client("sqs", **config)


def get_index_jobs_queue_arn() -> str:
    """
    Get the index jobs queue ARN from configuration.
    Matches the pattern in admin backend.
    """
    return os.environ.get("INDEX_JOBS_QUEUE_ARN", "corporate-context-index-jobs")


# Load test messages
with open("test_index_messages.json") as f:
    test_messages = json.load(f)

# Create SQS client using the same pattern as admin backend
sqs = create_sqs_client()


def send_message(message_key: str):
    """Send a test index message to the SQS queue."""
    if message_key not in test_messages:
        print(f"Error: Unknown message key '{message_key}'")
        print(f"Available keys: {', '.join(test_messages.keys())}")
        return False

    message_body = test_messages[message_key]
    queue_arn = get_index_jobs_queue_arn()
    queue_url = arn_to_queue_url(queue_arn)

    print(f"Sending {message_key} message to queue...")
    print(f"Queue ARN: {queue_arn}")
    print(f"Queue URL: {queue_url}")
    print(f"Message body: {json.dumps(message_body, indent=2)}")

    try:
        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
        )

        print("✅ Message sent successfully!")
        print(f"Message ID: {response['MessageId']}")
        print(f"MD5: {response['MD5OfMessageBody']}")
        return True

    except Exception as e:
        print(f"❌ Error sending message: {e}")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python send_index_message.py <message_type>")
        print("\nAvailable message types:")
        for key in test_messages:
            source = test_messages[key].get("source", "unknown")
            msg_type = test_messages[key].get("message_type", "unknown")
            print(f"  - {key} ({msg_type} for {source})")
        sys.exit(1)

    message_key = sys.argv[1]
    success = send_message(message_key)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
