#!/usr/bin/env python
"""
Initialize LocalStack with required AWS resources for development.
This script creates SQS queues, S3 buckets, and other AWS resources in LocalStack.
"""

import json
import logging
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# LocalStack configuration
LOCALSTACK_ENDPOINT = "http://localhost:4566"
AWS_REGION = "us-east-1"


def get_queue_name_from_arn(arn_or_name):
    """Extract queue name from ARN or return the name as-is."""
    if arn_or_name and arn_or_name.startswith("arn:aws:sqs:"):
        # Extract queue name from ARN format: arn:aws:sqs:region:account:queue-name
        return arn_or_name.split(":")[-1]
    return arn_or_name


def get_sqs_queues_to_create():
    """Get list of SQS queues to create from environment variables."""
    queue_configs = []

    # Common queue attributes
    base_attributes = {
        "FifoQueue": "true",
        "DelaySeconds": "0",
        "MessageRetentionPeriod": "345600",  # 4 days
    }

    # Queue configurations with specific visibility timeouts
    queue_env_vars = [
        (
            "INDEX_JOBS_QUEUE_ARN",
            "60",  # vis timeout
            "false",  # content based deduplication
        ),
        (
            "INGEST_JOBS_QUEUE_ARN",
            "30",  # vis timeout
            "false",  # content based deduplication
        ),
        (
            "SLACK_JOBS_QUEUE_ARN",
            "45",  # vis timeout
            "true",  # content based deduplication
        ),
    ]

    for env_var, visibility_timeout, content_based_deduplication in queue_env_vars:
        queue_arn = os.environ.get(env_var)
        if queue_arn:
            queue_name = get_queue_name_from_arn(queue_arn)
            attributes = {
                **base_attributes,
                "VisibilityTimeout": visibility_timeout,
                "ContentBasedDeduplication": content_based_deduplication,
            }
            queue_configs.append(
                {
                    "name": queue_name,
                    "attributes": attributes,
                }
            )

    return queue_configs


# S3 Buckets to create (configurable via environment variable)
def get_s3_buckets_to_create():
    """Get list of S3 buckets to create from environment variable."""
    bucket_name = os.environ.get("S3_BUCKET_NAME", "corporate-context-local")
    # Support comma-separated bucket names for multiple buckets
    bucket_names = [name.strip() for name in bucket_name.split(",") if name.strip()]
    return bucket_names


def get_ssm_seed_parameters():
    """Parse SSM parameters from LOCALSTACK_SSM_SEED environment variable.

    Expected format: JSON object with key-value pairs
    Example: {"key1": "value1", "key2": "value2"}

    Returns a list of parameter dictionaries for SSM.
    """
    seed_json = os.environ.get("LOCALSTACK_SSM_SEED")
    if not seed_json:
        return []

    try:
        seed_data = json.loads(seed_json)
        if not isinstance(seed_data, dict):
            logger.warning(
                f"LOCALSTACK_SSM_SEED must be a JSON object, got {type(seed_data).__name__}"
            )
            return []

        # Convert to SSM parameter format
        parameters = []
        for key, value in seed_data.items():
            # Ensure key starts with / for proper SSM path
            if not key.startswith("/"):
                key = f"/{key}"

            parameters.append(
                {
                    "Name": key,
                    "Value": str(value),  # Ensure value is string
                    "Type": "SecureString",  # Default to SecureString for safety
                }
            )

        return parameters
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LOCALSTACK_SSM_SEED JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"Error processing LOCALSTACK_SSM_SEED: {e}")
        return []


def wait_for_localstack():
    """Wait for LocalStack to be ready."""
    logger.info("Waiting for LocalStack to be ready...")
    max_retries = 30
    retry_count = 0

    while retry_count < max_retries:
        try:
            # Try to connect to LocalStack health endpoint
            import requests

            response = requests.get(f"{LOCALSTACK_ENDPOINT}/_localstack/health")
            if response.status_code == 200:
                logger.info("LocalStack is ready!")
                return True
        except Exception:
            pass

        retry_count += 1
        time.sleep(2)

    logger.error("LocalStack failed to start after 60 seconds")
    return False


def create_sqs_queues():
    """Create SQS queues in LocalStack."""
    sqs_client = boto3.client(
        "sqs",
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name=AWS_REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

    sqs_queues = get_sqs_queues_to_create()
    for queue_config in sqs_queues:
        queue_name = queue_config["name"]
        try:
            # Check if queue already exists
            response = sqs_client.get_queue_url(QueueName=queue_name)
            logger.info(f"Queue '{queue_name}' already exists at {response['QueueUrl']}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "AWS.SimpleQueueService.NonExistentQueue":
                # Create the queue
                response = sqs_client.create_queue(
                    QueueName=queue_name, Attributes=queue_config["attributes"]
                )
                logger.info(f"Created queue '{queue_name}' at {response['QueueUrl']}")
            else:
                logger.error(f"Error checking/creating queue '{queue_name}': {e}")
                raise


def create_ssm_parameters():
    """Create SSM parameters from LOCALSTACK_SSM_SEED environment variable."""
    # Get parameters from environment variable
    seed_parameters = get_ssm_seed_parameters()

    if not seed_parameters:
        logger.info("No LOCALSTACK_SSM_SEED provided, skipping SSM parameter creation")
        return

    ssm_client = boto3.client(
        "ssm",
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name=AWS_REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

    logger.info(f"Creating {len(seed_parameters)} SSM parameters from LOCALSTACK_SSM_SEED")

    created_count = 0
    for param in seed_parameters:
        try:
            ssm_client.put_parameter(
                Name=param["Name"],
                Value=param["Value"],
                Type=param["Type"],
                Tier="Advanced",
                Overwrite=True,
            )
            logger.info(f"Created SSM parameter: {param['Name']}")
            created_count += 1
        except Exception as e:
            logger.warning(f"Could not create SSM parameter {param['Name']}: {e}")

    if created_count > 0:
        logger.info(f"Successfully created {created_count} SSM parameters")


def set_bucket_cors(s3_client, bucket_name):
    """Set permissive CORS configuration for a bucket."""
    cors_configuration = {
        "CORSRules": [
            {
                "AllowedHeaders": ["*"],
                "AllowedMethods": ["GET", "PUT", "POST", "DELETE", "HEAD"],
                "AllowedOrigins": ["*"],
                "ExposeHeaders": ["ETag", "x-amz-server-side-encryption"],
                "MaxAgeSeconds": 3000,
            }
        ]
    }
    s3_client.put_bucket_cors(Bucket=bucket_name, CORSConfiguration=cors_configuration)
    logger.info(f"Set permissive CORS configuration for bucket '{bucket_name}'")


def create_kms_key_for_s3():
    """Create KMS key for S3 bucket encryption."""
    kms_client = boto3.client(
        "kms",
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name=AWS_REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

    try:
        # Create the KMS key
        response = kms_client.create_key(
            Description="SQS Extended Client S3 bucket encryption key",
            KeyUsage="ENCRYPT_DECRYPT",
            Origin="AWS_KMS",
        )
        key_id = response["KeyMetadata"]["KeyId"]
        logger.info(f"Created KMS key: {key_id}")

        # Create an alias for easier identification
        alias_name = "alias/sqs-extended-client"
        try:
            kms_client.create_alias(
                AliasName=alias_name,
                TargetKeyId=key_id,
            )
            logger.info(f"Created KMS key alias: {alias_name}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "AlreadyExistsException":
                logger.info(f"KMS alias {alias_name} already exists")
            else:
                logger.warning(f"Could not create KMS alias: {e}")

        return key_id
    except Exception as e:
        logger.error(f"Failed to create KMS key: {e}")
        raise


def get_sqs_extended_bucket_name():
    return os.environ.get(
        "INGEST_WEBHOOK_DATA_S3_BUCKET_NAME", "corporate-context-ingest-webhook-data-local"
    )


def create_sqs_extended_bucket():
    """Create S3 bucket for SQS Extended Client with KMS encryption."""
    s3_client = boto3.client(
        "s3",
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name=AWS_REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

    bucket_name = get_sqs_extended_bucket_name()

    try:
        # Check if bucket already exists
        s3_client.head_bucket(Bucket=bucket_name)
        logger.info(f"SQS Extended bucket '{bucket_name}' already exists")
    except ClientError as e:
        error_code = int(e.response["Error"]["Code"])
        if error_code == 404:
            # Bucket doesn't exist, create it
            try:
                if AWS_REGION == "us-east-1":
                    s3_client.create_bucket(Bucket=bucket_name)
                else:
                    s3_client.create_bucket(
                        Bucket=bucket_name,
                        CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
                    )
                logger.info(f"Created SQS Extended S3 bucket: {bucket_name}")
            except ClientError as create_error:
                logger.error(f"Failed to create bucket '{bucket_name}': {create_error}")
                raise
        else:
            logger.error(f"Error checking bucket '{bucket_name}': {e}")
            raise

    # Create KMS key for encryption
    kms_key_id = create_kms_key_for_s3()

    # Apply KMS encryption to the bucket
    try:
        encryption_config = {
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "aws:kms",
                        "KMSMasterKeyID": kms_key_id,
                    },
                    "BucketKeyEnabled": True,
                }
            ]
        }
        s3_client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration=encryption_config,
        )
        logger.info(f"Applied KMS encryption to bucket '{bucket_name}' with key {kms_key_id}")
    except Exception as e:
        logger.error(f"Failed to apply encryption to bucket '{bucket_name}': {e}")
        raise

    # Set CORS configuration
    set_bucket_cors(s3_client, bucket_name)


def create_s3_buckets():
    """Create S3 buckets in LocalStack."""
    s3_client = boto3.client(
        "s3",
        endpoint_url=LOCALSTACK_ENDPOINT,
        region_name=AWS_REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )

    bucket_names = get_s3_buckets_to_create()

    for bucket_name in bucket_names:
        try:
            # Check if bucket already exists
            s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"Bucket '{bucket_name}' already exists")

            # Set permissive CORS configuration for existing bucket
            set_bucket_cors(s3_client, bucket_name)
        except ClientError as e:
            error_code = int(e.response["Error"]["Code"])
            if error_code == 404:
                # Bucket doesn't exist, create it
                try:
                    if AWS_REGION == "us-east-1":
                        # For us-east-1, don't specify LocationConstraint
                        s3_client.create_bucket(Bucket=bucket_name)
                    else:
                        # For other regions, specify LocationConstraint
                        s3_client.create_bucket(
                            Bucket=bucket_name,
                            CreateBucketConfiguration={"LocationConstraint": AWS_REGION},
                        )
                    logger.info(f"Created S3 bucket: {bucket_name}")

                    # Verify bucket was created by listing it
                    s3_client.list_objects_v2(Bucket=bucket_name, MaxKeys=1)
                    logger.info(f"Verified S3 bucket '{bucket_name}' is accessible")

                    # Set permissive CORS configuration for local development
                    set_bucket_cors(s3_client, bucket_name)

                except ClientError as create_error:
                    logger.error(f"Failed to create bucket '{bucket_name}': {create_error}")
                    raise
            else:
                logger.error(f"Error checking bucket '{bucket_name}': {e}")
                raise


def main():
    """Main function to initialize LocalStack resources."""
    logger.info("Starting LocalStack initialization...")

    # Wait for LocalStack to be ready
    if not wait_for_localstack():
        logger.error("LocalStack is not available. Please start it first with: mise dev")
        sys.exit(1)

    try:
        # Create SQS queues
        logger.info("Creating SQS queues...")
        create_sqs_queues()

        # Create S3 buckets
        logger.info("Creating S3 buckets...")
        create_s3_buckets()

        # Create SQS Extended bucket with KMS encryption
        logger.info("Creating SQS Extended S3 bucket with KMS encryption...")
        create_sqs_extended_bucket()

        # Create SSM parameters (optional)
        logger.info("Creating SSM parameters...")
        create_ssm_parameters()

        logger.info("✅ LocalStack initialization completed successfully!")
        logger.info("\nYou can now connect to LocalStack at:")
        logger.info(f"  Endpoint: {LOCALSTACK_ENDPOINT}")
        logger.info(f"  Region: {AWS_REGION}")
        logger.info("\nCreated resources:")
        logger.info("SQS Queues:")
        sqs_queues = get_sqs_queues_to_create()
        for queue in sqs_queues:
            logger.info(f"  - {queue['name']}")

        bucket_names = get_s3_buckets_to_create()
        if bucket_names:
            logger.info("S3 Buckets:")
            for bucket_name in bucket_names:
                logger.info(f"  - {bucket_name}")

        sqs_extended_bucket = get_sqs_extended_bucket_name()
        if sqs_extended_bucket:
            logger.info("SQS Extended S3 Bucket (KMS encrypted):")
            logger.info(f"  - {sqs_extended_bucket}")
            logger.info("  - KMS Key Alias: alias/sqs-extended-client")

    except Exception as e:
        logger.error(f"Failed to initialize LocalStack: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
