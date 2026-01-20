#!/usr/bin/env python
"""
Script to send test ingest/backfill messages to SQS ingest queue.
Matches the pattern used in the admin backend's SQS client.
"""

import json
import os
import random
import sys
import time
import uuid

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
        region = parts[3]
        account_id = parts[4]
        queue_name = parts[5]
        return f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}"

    # Plain queue name support
    region = os.environ.get("AWS_REGION")
    account_id = os.environ.get("AWS_ACCOUNT_ID")
    if not region or not account_id:
        raise ValueError(
            f"Cannot resolve queue URL from plain name '{queue_identifier}' "
            "without AWS_REGION and AWS_ACCOUNT_ID environment variables"
        )
    # After the None check, we know these are strings
    assert region is not None and account_id is not None
    return f"https://sqs.{region}.amazonaws.com/{account_id}/{queue_identifier}"


def create_sqs_client(queue_arn: str = None):
    """
    Create SQS client following the same pattern as admin backend.
    Extracts region from ARN if provided.
    """
    region = os.environ.get("AWS_REGION")
    endpoint_url = os.environ.get("AWS_ENDPOINT_URL")

    # Extract region from ARN if provided
    if queue_arn and queue_arn.startswith("arn:"):
        parts = queue_arn.split(":")
        if len(parts) >= 4:
            region = parts[3]  # Region is the 4th part of ARN

    config = {}
    if region:
        config["region_name"] = region
    if endpoint_url:
        config["endpoint_url"] = endpoint_url
        print(f"SQS client configured for LocalStack at {endpoint_url}")

    return boto3.client("sqs", **config)


def get_ingest_jobs_queue_arn() -> str:
    """
    Get the ingest jobs queue ARN from configuration.
    Matches the pattern in admin backend.
    """
    return os.environ.get("INGEST_JOBS_QUEUE_ARN", "corporate-context-ingest-jobs")


def remove_json_comments(text: str) -> str:
    """Remove // comments from JSONC content to make it valid JSON."""
    # Remove // comments (but not inside strings)
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        # Simple approach: remove everything after // that's not inside quotes
        in_string = False
        escape_next = False
        result = ""
        i = 0
        while i < len(line):
            char = line[i]
            if escape_next:
                result += char
                escape_next = False
            elif char == "\\" and in_string:
                result += char
                escape_next = True
            elif char == '"' and not escape_next:
                in_string = not in_string
                result += char
            elif char == "/" and i + 1 < len(line) and line[i + 1] == "/" and not in_string:
                # Found comment, stop processing this line
                break
            else:
                result += char
            i += 1
        cleaned_lines.append(result.rstrip())
    return "\n".join(cleaned_lines)


def get_ingest_lane(message_body: dict) -> str:
    """Get the ingest lane for a given ingest job message (simplified from lanes.py)."""
    tenant_id = message_body["tenant_id"]
    message_type = message_body["message_type"]

    if message_type == "webhook":
        # Webhooks = 60 lanes per tenant, total
        return f"ingest_webhook_{tenant_id}_{random.randint(0, 59)}"
    elif message_type == "backfill":
        # Backfill = 30 lanes per tenant per source
        source = message_body["source"]
        return f"ingest_backfill_{tenant_id}_{source}_{random.randint(0, 29)}"
    elif message_type == "reindex":
        # Reindex = infinite lanes (using large random number)
        source = message_body["source"]
        return f"reindex_{tenant_id}_{source}_{random.randint(0, 9999999)}"
    elif message_type == "tenant_data_deletion":
        # Tenant data deletion = single lane per tenant
        return f"tenant_data_deletion_{tenant_id}"
    else:
        raise ValueError(f"Unknown message type: {message_type}")


# Load test messages
with open("test_ingest_messages.jsonc") as f:
    content = f.read()
    cleaned_content = remove_json_comments(content)
    test_messages = json.loads(cleaned_content)

# Get queue ARN first to extract region
queue_arn = get_ingest_jobs_queue_arn()

# Create SQS client using the same pattern as admin backend
sqs = create_sqs_client(queue_arn)


def send_message(message_key: str):
    """Send a test ingest message to the SQS queue."""
    if message_key not in test_messages:
        print(f"Error: Unknown message key '{message_key}'")
        print(f"Available keys: {', '.join(test_messages.keys())}")
        return False

    message_body = test_messages[message_key]
    queue_url = arn_to_queue_url(queue_arn)

    print(f"Sending {message_key} message to queue...")
    print(f"Queue ARN: {queue_arn}")
    print(f"Queue URL: {queue_url}")
    print(f"Message body: {json.dumps(message_body, indent=2)}")

    try:
        # Determine lane for FIFO queue
        lane = get_ingest_lane(message_body)
        print(f"Lane (MessageGroupId): {lane}")

        # Generate unique deduplication ID
        dedup_id = f"{message_key}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        print(f"MessageDeduplicationId: {dedup_id}")

        response = sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
            MessageGroupId=lane,
            MessageDeduplicationId=dedup_id,
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
        print("Usage: python send_ingest_message.py <message_type>")
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
