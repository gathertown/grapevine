#!/usr/bin/env python3
"""
Test script for SQS Extended Client with large webhook payloads.

This script sends a large webhook payload to the gatekeeper service to test
that it properly uses S3 storage for messages exceeding the size threshold.

Set DANGEROUSLY_DISABLE_WEBHOOK_VALIDATION=1 on ingest-gatekeeper before running this script.
Requires a valid tenant_id for your local environment, pass via TENANT_ID env var.
Disable ingest-worker before running to make sure the objects aren't deleted out of the s3 bucket
before we verify that they exist.
"""

import json
import os
from datetime import datetime

import requests


def create_large_github_payload(size_kb: int = 250) -> dict:
    """Create a large GitHub webhook payload for testing.

    Args:
        size_kb: Approximate payload size in KB

    Returns:
        Dictionary representing a GitHub webhook payload
    """
    # Calculate how much filler data we need
    base_payload_size = 1000  # Approximate size of base payload
    filler_size = (size_kb * 1024) - base_payload_size

    return {
        "action": "opened",
        "number": 123,
        "pull_request": {
            "id": 123456789,
            "number": 123,
            "state": "open",
            "title": "Test large payload PR",
            "body": f"This is test data for SQS Extended Client.\n{'x' * max(0, filler_size)}",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "user": {
                "id": 12345,
                "login": "testuser",
                "avatar_url": "https://example.com/avatar.png",
            },
            "head": {
                "ref": "feature-branch",
                "sha": "abc123def456",
                "user": {
                    "id": 12345,
                    "login": "testuser",
                },
                "repo": {
                    "id": 98765,
                    "name": "test-repo",
                    "full_name": "testuser/test-repo",
                },
            },
            "base": {
                "ref": "main",
                "sha": "def456abc123",
                "user": {
                    "id": 12345,
                    "login": "testuser",
                },
                "repo": {
                    "id": 98765,
                    "name": "test-repo",
                    "full_name": "testuser/test-repo",
                },
            },
        },
        "repository": {
            "id": 98765,
            "name": "test-repo",
            "full_name": "testuser/test-repo",
            "private": False,
            "owner": {
                "id": 12345,
                "login": "testuser",
            },
        },
        "sender": {
            "id": 12345,
            "login": "testuser",
        },
    }


def send_webhook(payload: dict, tenant_id: str, gatekeeper_url: str = "http://localhost:8001"):
    """Send webhook payload to gatekeeper service.

    Args:
        payload: Webhook payload dictionary
        tenant_id: Tenant ID for the webhook
        gatekeeper_url: Base URL of the gatekeeper service

    Returns:
        requests.Response object
    """
    url = f"{gatekeeper_url}/{tenant_id}/webhooks/github"

    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": f"test-delivery-{datetime.now().timestamp()}",
        "X-Hub-Signature-256": "sha256=test-signature",
    }

    print(f"Sending webhook to: {url}")
    print(f"Payload size: {len(json.dumps(payload)):,} bytes")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        return response
    except requests.RequestException as e:
        print(f"❌ Request failed: {e}")
        return None


def get_s3_client():
    """Create S3 client for LocalStack."""
    try:
        import boto3

        return boto3.client(
            "s3",
            endpoint_url="http://localhost:4566",
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name="us-east-1",
        )
    except ImportError:
        return None


def count_s3_objects(bucket_name: str) -> int:
    """Count objects in S3 bucket.

    Args:
        bucket_name: Name of the S3 bucket to check

    Returns:
        Number of objects in bucket, or -1 if unable to check
    """
    s3_client = get_s3_client()
    if not s3_client:
        return -1

    try:
        from botocore.exceptions import ClientError

        response = s3_client.list_objects_v2(Bucket=bucket_name)
        return len(response.get("Contents", []))
    except ClientError as e:
        print(f"❌ Error counting S3 objects: {e}")
        return -1
    except Exception as e:
        print(f"❌ Unexpected error counting S3 objects: {e}")
        return -1


def check_bucket_encryption(bucket_name: str):
    """Check and display S3 bucket encryption configuration.

    Args:
        bucket_name: Name of the S3 bucket to check
    """
    s3_client = get_s3_client()
    if not s3_client:
        print("⚠️  boto3 not available, cannot check bucket encryption")
        return

    try:
        from botocore.exceptions import ClientError

        encryption_response = s3_client.get_bucket_encryption(Bucket=bucket_name)
        rules = encryption_response.get("ServerSideEncryptionConfiguration", {}).get("Rules", [])

        for rule in rules:
            sse_config = rule.get("ApplyServerSideEncryptionByDefault", {})
            if sse_config.get("SSEAlgorithm") == "aws:kms":
                kms_key = sse_config.get("KMSMasterKeyID", "N/A")
                print(f"🔐 Bucket '{bucket_name}' is encrypted with KMS")
                print(f"   - KMS Key: {kms_key}")
                print(f"   - Bucket Key Enabled: {rule.get('BucketKeyEnabled', False)}")
                break
        else:
            print(f"⚠️  No KMS encryption found on bucket '{bucket_name}'")
    except ClientError as e:
        if e.response["Error"]["Code"] == "ServerSideEncryptionConfigurationNotFoundError":
            print(f"⚠️  No encryption configured for bucket '{bucket_name}'")
        else:
            print(f"❌ Error checking bucket encryption: {e}")
    except Exception as e:
        print(f"❌ Unexpected error checking encryption: {e}")


def main():
    """Main function to run the test."""
    print("🧪 Testing SQS Extended Client with Large Webhook Payloads")
    print("=" * 60)
    tenant_id = os.environ.get("TENANT_ID")
    if not tenant_id:
        raise Exception("Must set TENANT_ID env var")
    print(f"Using tenant_id {tenant_id}")

    # Check if gatekeeper is configured for extended client
    s3_bucket = os.getenv(
        "INGEST_WEBHOOK_DATA_S3_BUCKET_NAME", "corporate-context-ingest-webhook-data-local"
    )
    # Use the correct threshold from the code: 256KB
    threshold = int(os.getenv("SQS_EXTENDED_THRESHOLD", "262144"))  # 256 * 1024

    print(f"S3 Bucket: {s3_bucket or 'Not configured'}")
    print(f"Size Threshold: {threshold:,} bytes")
    print()

    # Check initial bucket encryption
    if s3_bucket:
        print("🔍 Checking S3 bucket encryption...")
        check_bucket_encryption(s3_bucket)
        print()

    # Test with different payload sizes
    test_sizes = [50, 150, 250, 300]  # KB - mix of under and over 256KB threshold
    test_results = []

    for size_kb in test_sizes:
        print(f"📤 Testing with {size_kb}KB payload...")

        # Count S3 objects before webhook
        objects_before = count_s3_objects(s3_bucket) if s3_bucket else -1
        if objects_before >= 0:
            print(f"   📊 S3 objects before: {objects_before}")

        # Create payload
        payload = create_large_github_payload(size_kb)
        payload_size = len(json.dumps(payload))
        should_use_s3 = payload_size > threshold

        # Send webhook
        response = send_webhook(payload, tenant_id=tenant_id)

        if response and response.status_code == 200:
            print(f"✅ Webhook accepted ({payload_size:,} bytes)")

            # Count S3 objects after webhook
            objects_after = count_s3_objects(s3_bucket) if s3_bucket else -1

            if objects_before >= 0 and objects_after >= 0:
                objects_created = objects_after - objects_before
                print(f"   📊 S3 objects after: {objects_after} (created: {objects_created})")

                # Validate expected behavior
                if should_use_s3:
                    if objects_created == 1:
                        print("   ✅ PASS: Large payload created 1 S3 object as expected")
                        test_results.append(("PASS", size_kb, payload_size, should_use_s3))
                    else:
                        print(
                            f"   ❌ FAIL: Large payload should have created 1 S3 object, created {objects_created}"
                        )
                        test_results.append(("FAIL", size_kb, payload_size, should_use_s3))
                else:
                    if objects_created == 0:
                        print("   ✅ PASS: Small payload created 0 S3 objects as expected")
                        test_results.append(("PASS", size_kb, payload_size, should_use_s3))
                    else:
                        print(
                            f"   ❌ FAIL: Small payload should not have created S3 objects, created {objects_created}"
                        )
                        test_results.append(("FAIL", size_kb, payload_size, should_use_s3))

                print(
                    f"   📦 Expected S3 usage: {'YES' if should_use_s3 else 'NO'} (threshold: {threshold:,} bytes)"
                )
            else:
                print("   ⚠️  Cannot validate S3 behavior - S3 check failed")
                test_results.append(("UNKNOWN", size_kb, payload_size, should_use_s3))
        else:
            error_msg = (
                f"{response.status_code} - {response.text}" if response else "Request failed"
            )
            print(f"❌ Webhook rejected: {error_msg}")
            test_results.append(("FAIL", size_kb, payload_size, should_use_s3))
        print()

    # Summary of test results
    print("📋 Test Summary:")
    print("=" * 60)
    passed = failed = unknown = 0
    for result, size_kb, payload_size, should_use_s3 in test_results:
        status_icon = "✅" if result == "PASS" else "❌" if result == "FAIL" else "⚠️"
        s3_expected = "S3" if should_use_s3 else "SQS"
        print(
            f"{status_icon} {size_kb}KB payload ({payload_size:,} bytes) -> {s3_expected}: {result}"
        )
        if result == "PASS":
            passed += 1
        elif result == "FAIL":
            failed += 1
        else:
            unknown += 1

    print(f"\n📊 Results: {passed} passed, {failed} failed, {unknown} unknown")

    print("\n✅ Test completed!")
    print("\nTo monitor the processing:")
    print("1. Check gatekeeper logs for 'Large ingest webhook message' messages")
    print("2. Check worker logs for 'extended SQS client' messages")
    print(
        "3. Inspect S3 bucket contents with: aws --endpoint-url=http://localhost:4566 s3 ls s3://{bucket}/"
    )


if __name__ == "__main__":
    main()
