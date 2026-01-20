# Self-Hosting Guide

This guide covers deploying Grapevine in a production environment. For local development, see [Local Development Guide](LOCAL_DEVELOPMENT.md).

## Table of Contents

- [Prerequisites](#prerequisites)
- [Infrastructure Checklist](#infrastructure-checklist)
- [Database Setup](#database-setup)
- [AWS Infrastructure](#aws-infrastructure)
- [External Services](#external-services)
- [Deployment](#deployment)
- [Operations](#operations)

## Prerequisites

### Required Accounts

| Service         | Purpose                             | Signup                                             |
| --------------- | ----------------------------------- | -------------------------------------------------- |
| **AWS**         | SQS, S3, KMS, SSM                   | [aws.amazon.com](https://aws.amazon.com)           |
| **Turbopuffer** | Vector database for semantic search | [turbopuffer.com](https://turbopuffer.com)         |
| **WorkOS**      | Authentication (AuthKit)            | [workos.com](https://workos.com)                   |
| **OpenAI**      | Embeddings generation               | [platform.openai.com](https://platform.openai.com) |

### Related Documentation

- [Architecture Overview](ARCHITECTURE.md) - System design and data flow
- [Local Development Guide](LOCAL_DEVELOPMENT.md) - Running Grapevine locally
- [Feature Configuration](optional-features.md) - Environment variables and optional features
- [Authentication Setup](auth-setup.md) - WorkOS/AuthKit configuration
- [Billing Setup](billing-and-usage.md) - Stripe integration

## Infrastructure Checklist

Use this checklist to track provisioning progress.

### Required Components

| Component   | Type        | Purpose                                       | Setup Section                               |
| ----------- | ----------- | --------------------------------------------- | ------------------------------------------- |
| PostgreSQL  | Database    | Control database + tenant databases           | [Database Setup](#postgresql)               |
| OpenSearch  | Database    | Full-text keyword search (BM25)               | [Database Setup](#opensearch)               |
| Turbopuffer | Database    | Semantic search via embeddings                | [Database Setup](#turbopuffer)              |
| Redis       | Cache       | Sessions, rate limiting, job state            | [Database Setup](#redis)                    |
| SQS Queues  | Queue       | Async job processing (ingest, index, Slack)   | [AWS Infrastructure](#sqs-queues)           |
| S3 Buckets  | Storage     | File uploads, large webhook payloads          | [AWS Infrastructure](#s3-buckets)           |
| KMS Key     | Encryption  | SSM parameter encryption                      | [AWS Infrastructure](#kms-key)              |
| SSM         | Secrets     | Tenant credentials, API keys, webhook secrets | [AWS Infrastructure](#ssm-parameter-store)  |
| IAM Policy  | Permissions | Application access to AWS services            | [AWS Infrastructure](#iam-permissions)      |
| WorkOS      | Auth        | User authentication and SSO                   | [External Services](#workos-authentication) |
| OpenAI      | AI          | Embeddings generation                         | [External Services](#openai)                |

### Optional Components

| Component | Type          | Purpose                 | Documentation                                                                  |
| --------- | ------------- | ----------------------- | ------------------------------------------------------------------------------ |
| Stripe    | Billing       | Subscription management | [Billing Setup](billing-and-usage.md)                                          |
| Langfuse  | Observability | LLM observability       | [Feature Configuration](optional-features.md#langfuse-tracing--optional)       |
| Amplitude | Analytics     | User analytics          | [Feature Configuration](optional-features.md#amplitude)                        |
| PostHog   | Analytics     | Product analytics       | [Feature Configuration](optional-features.md#posthog)                          |
| Mailgun   | Email         | Invitation emails       | [Feature Configuration](optional-features.md#email-delivery-mailgun--optional) |
| New Relic | Observability | Application performance | [Feature Configuration](optional-features.md#new-relic--optional)              |

> **Note**: When billing is disabled (no `STRIPE_SECRET_KEY`), all tenants have unlimited usage.

## Database Setup

### PostgreSQL

Grapevine uses PostgreSQL for:

1. **Control Database**: Tenant registry and provisioning state
2. **Tenant Databases**: Per-tenant isolated databases (auto-created by Steward service)

#### Managed Service (Recommended)

Use a managed PostgreSQL service:

- **AWS RDS** - Multi-AZ for high availability
- **Google Cloud SQL** - Automatic backups and failover
- **Azure Database for PostgreSQL**

**Requirements:**

- PostgreSQL 14+
- SSL enabled
- `uuid-ossp` extension available

#### Control Database Setup

```sql
-- Create the control database
CREATE DATABASE grapevine_control;

-- Connect to grapevine_control and enable extensions
\c grapevine_control
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

#### Tenant Database Configuration

The Steward service creates tenant databases automatically. Configure admin credentials:

```bash
# Host where tenant databases will be created
PG_TENANT_DATABASE_HOST=your-rds-cluster.cluster-xxxxx.us-east-1.rds.amazonaws.com

# Admin credentials (must have CREATE DATABASE and CREATE ROLE privileges)
# For Aurora, the default master username is "postgres"
PG_TENANT_DATABASE_ADMIN_USERNAME=postgres
PG_TENANT_DATABASE_ADMIN_PASSWORD=secure-admin-password
PG_TENANT_DATABASE_ADMIN_DB=postgres
```

#### IAM Database Authentication (Recommended for AWS)

Grapevine services can use IAM database authentication instead of passwords. This is configured via the `rds-db:connect` IAM permission in each service's policy.

To enable IAM authentication:

1. Enable IAM authentication on your RDS cluster
2. Create database users that authenticate via IAM
3. Services will automatically use IAM credentials when connecting

#### Connection Configuration

```bash
# Control database URL (include SSL for production)
CONTROL_DATABASE_URL=postgresql://user:password@host:5432/grapevine_control?sslmode=require
```

### OpenSearch

OpenSearch provides full-text keyword search (BM25). Each tenant gets an isolated index.

#### AWS OpenSearch Service (Recommended)

Create an OpenSearch domain with these settings:

1. **Cluster configuration**:

   - Zone awareness enabled (3 availability zones)
   - Dedicated master nodes enabled (3 nodes recommended)
   - Data nodes: 1+ per availability zone

2. **Security**:

   - Fine-grained access control enabled
   - Internal user database enabled
   - Master user: `opensearch_admin` (or your chosen username)
   - Node-to-node encryption enabled
   - Encryption at rest with KMS (use the Grapevine KMS key)
   - HTTPS required (TLS 1.2 minimum)

3. **Network**:

   - Deploy within your VPC
   - Security group allowing HTTPS (port 443) from application subnets

4. **Access policy** (allow all from within VPC, IAM controls access):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": { "AWS": "*" },
         "Action": "es:*",
         "Resource": "arn:aws:es:{region}:{account}:domain/{domain-name}/*"
       }
     ]
   }
   ```

**Environment variables:**

```bash
OPENSEARCH_DOMAIN_HOST=your-domain.us-east-1.es.amazonaws.com
OPENSEARCH_PORT=443
OPENSEARCH_ADMIN_USERNAME=opensearch_admin
OPENSEARCH_ADMIN_PASSWORD=your-secure-password
OPENSEARCH_USE_SSL=true
```

#### Self-Managed Cluster

For self-managed OpenSearch:

1. Deploy minimum 3 data nodes for high availability
2. Enable security plugin with TLS (node-to-node and client encryption)
3. Configure 3 dedicated master nodes for larger clusters
4. Enable fine-grained access control with internal user database
5. Configure encryption at rest

### Turbopuffer

Turbopuffer is the hosted vector database for semantic search.

#### Setup

1. Create an account at [turbopuffer.com](https://turbopuffer.com)
2. Copy your API key from the dashboard

#### Environment Variables

```bash
TURBOPUFFER_API_KEY=your-api-key-here
TURBOPUFFER_REGION=us-east-1

# Environment prefix for namespace isolation
# Namespaces: {GRAPEVINE_ENVIRONMENT}-tenant-{tenant_id}-chunks
GRAPEVINE_ENVIRONMENT=production
```

### Redis

Redis handles session caching, rate limiting, job state, and billing limits cache.

#### AWS ElastiCache (Recommended)

Create an ElastiCache Redis replication group:

1. **Engine**: Redis 7.x
2. **Node type**: Based on your load (e.g., `cache.t3.micro` for dev, `cache.r6g.large` for production)
3. **Number of cache clusters**: 1 (single-node for cost efficiency, or 2+ for HA)
4. **Encryption**:
   - Encryption at rest enabled with KMS (use the Grapevine KMS key)
   - Encryption in transit (TLS) - optional but recommended
5. **Network**:
   - Deploy within your VPC private subnets
   - Security group allowing port 6379 from application subnets (CIDR `10.0.0.0/8` or your VPC CIDR)

**Environment variable:**

```bash
# Without TLS (internal VPC traffic)
REDIS_PRIMARY_ENDPOINT=redis://your-cluster.cache.amazonaws.com:6379

# With TLS (recommended for production)
REDIS_PRIMARY_ENDPOINT=rediss://your-cluster.cache.amazonaws.com:6379

# With authentication (if AUTH is enabled)
REDIS_PRIMARY_ENDPOINT=rediss://:auth-token@your-cluster.cache.amazonaws.com:6379
```

#### Self-Managed Redis

For self-managed Redis:

- Redis 7.x recommended
- Enable encryption at rest
- Enable TLS for client connections (production)
- Configure `maxmemory-policy allkeys-lru`
- Set up replication for high availability (optional)

## AWS Infrastructure

> **Important**: All resource names in this section (S3 bucket names, SQS queue names, KMS key IDs, etc.) are **templates** that must be customized for your deployment. S3 bucket names are globally unique across all AWS accounts—you cannot use the exact names shown here. Replace all placeholder values with your actual resource names before applying any IAM policies or configurations.

### KMS Key

Create a KMS key first—it's used for encrypting data across all other Grapevine AWS resources (SQS, S3, SSM, and optionally RDS/OpenSearch):

```bash
# Create the key with automatic rotation enabled
KEY_ID=$(aws kms create-key \
  --description "Grapevine infrastructure encryption key for OpenSearch, RDS, SQS, S3, SSM and other services" \
  --query 'KeyMetadata.KeyId' \
  --output text)

# Enable automatic key rotation
aws kms enable-key-rotation --key-id ${KEY_ID}

# Create an alias
aws kms create-alias --alias-name alias/grapevine-kms --target-key-id ${KEY_ID}
```

**Configure the KMS key policy** to allow access from AWS services:

```bash
# Get your AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"

# Create the key policy
cat > /tmp/kms-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EnableRootUserFullAccess",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::${ACCOUNT_ID}:root" },
      "Action": "kms:*",
      "Resource": "*"
    },
    {
      "Sid": "AllowOpenSearchAccess",
      "Effect": "Allow",
      "Principal": { "AWS": "*" },
      "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:CreateGrant", "kms:ListGrants", "kms:DescribeKey"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "es.${REGION}.amazonaws.com",
          "kms:CallerAccount": "${ACCOUNT_ID}"
        }
      }
    },
    {
      "Sid": "AllowRDSAccess",
      "Effect": "Allow",
      "Principal": { "AWS": "*" },
      "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:CreateGrant", "kms:ListGrants", "kms:DescribeKey"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "rds.${REGION}.amazonaws.com",
          "kms:CallerAccount": "${ACCOUNT_ID}"
        }
      }
    },
    {
      "Sid": "AllowSQSAccess",
      "Effect": "Allow",
      "Principal": { "Service": "sqs.amazonaws.com" },
      "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
      "Resource": "*",
      "Condition": {
        "StringEquals": { "kms:CallerAccount": "${ACCOUNT_ID}" }
      }
    },
    {
      "Sid": "AllowS3Access",
      "Effect": "Allow",
      "Principal": { "AWS": "*" },
      "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:CreateGrant", "kms:ListGrants", "kms:DescribeKey"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "s3.${REGION}.amazonaws.com",
          "kms:CallerAccount": "${ACCOUNT_ID}"
        }
      }
    },
    {
      "Sid": "AllowSSMAccess",
      "Effect": "Allow",
      "Principal": { "AWS": "*" },
      "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:CreateGrant", "kms:ListGrants", "kms:DescribeKey"],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "ssm.${REGION}.amazonaws.com",
          "kms:CallerAccount": "${ACCOUNT_ID}"
        }
      }
    }
  ]
}
EOF

# Apply the policy
aws kms put-key-policy --key-id ${KEY_ID} --policy-name default --policy file:///tmp/kms-policy.json
```

**Environment variable:**

```bash
# Use the alias or the full ARN
KMS_KEY_ARN=arn:aws:kms:us-east-1:123456789012:key/your-key-id
# Or use the alias
KMS_KEY_ID=alias/grapevine-kms
```

### IAM Permissions

Grapevine uses **separate IAM policies for each service** to follow least-privilege principles. Create an IAM role for each service and attach the corresponding policy.

> **Note for Kubernetes deployments**: Use [IAM Roles for Service Accounts (IRSA)](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) to associate each Kubernetes service account with its dedicated IAM role.

#### Admin Backend (grapevine-app)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowListUploadArtifactsBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::grapevine-upload-artifacts"
    },
    {
      "Sid": "AllowUploadArtifactsObjectAccess",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::grapevine-upload-artifacts/*"
    },
    {
      "Sid": "AllowSSMParameterAccess",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:PutParameter",
        "ssm:DeleteParameter"
      ],
      "Resource": "arn:aws:ssm:{region}:{account}:parameter/*"
    },
    {
      "Sid": "AllowRDSConnect",
      "Effect": "Allow",
      "Action": ["rds-db:connect"],
      "Resource": "arn:aws:rds-db:{region}:{account}:dbuser:{cluster-resource-id}/*"
    },
    {
      "Sid": "AllowSQSSendToIngestAndSlackJobs",
      "Effect": "Allow",
      "Action": ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"],
      "Resource": [
        "arn:aws:sqs:{region}:{account}:grapevine-ingest-jobs.fifo",
        "arn:aws:sqs:{region}:{account}:grapevine-slack-jobs.fifo"
      ]
    },
    {
      "Sid": "AllowSQSServiceAccess",
      "Effect": "Allow",
      "Action": ["sqs:ListQueues"],
      "Resource": "*"
    },
    {
      "Sid": "AllowKMSForGrapevineServices",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:{region}:{account}:key/{kms-key-id}",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": [
            "s3.{region}.amazonaws.com",
            "ssm.{region}.amazonaws.com",
            "rds.{region}.amazonaws.com",
            "sqs.{region}.amazonaws.com"
          ]
        }
      }
    }
  ]
}
```

#### MCP Server (grapevine-api)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowRDSConnect",
      "Effect": "Allow",
      "Action": ["rds-db:connect"],
      "Resource": "arn:aws:rds-db:{region}:{account}:dbuser:{cluster-resource-id}/*"
    },
    {
      "Sid": "AllowOpenSearchAccess",
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost",
        "es:ESHttpPut",
        "es:ESHttpDelete",
        "es:ESHttpHead"
      ],
      "Resource": [
        "arn:aws:es:{region}:{account}:domain/{domain-name}",
        "arn:aws:es:{region}:{account}:domain/{domain-name}/*"
      ]
    },
    {
      "Sid": "AllowSSMParameterAccess",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:PutParameter",
        "ssm:DeleteParameter"
      ],
      "Resource": "arn:aws:ssm:{region}:{account}:parameter/*"
    },
    {
      "Sid": "AllowKMSForRDSOpenSearch",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:{region}:{account}:key/{kms-key-id}",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": [
            "rds.{region}.amazonaws.com",
            "es.{region}.amazonaws.com",
            "ssm.{region}.amazonaws.com"
          ]
        }
      }
    }
  ]
}
```

#### Ingest Gatekeeper

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowListIngestWebhookDataBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::grapevine-ingest-webhook-data"
    },
    {
      "Sid": "AllowWriteIngestWebhookDataObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::grapevine-ingest-webhook-data/*"
    },
    {
      "Sid": "AllowSQSSendMessages",
      "Effect": "Allow",
      "Action": ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"],
      "Resource": [
        "arn:aws:sqs:{region}:{account}:grapevine-slack-jobs.fifo",
        "arn:aws:sqs:{region}:{account}:grapevine-ingest-jobs.fifo",
        "arn:aws:sqs:{region}:{account}:grapevine-index-jobs.fifo"
      ]
    },
    {
      "Sid": "AllowRDSConnect",
      "Effect": "Allow",
      "Action": ["rds-db:connect"],
      "Resource": "arn:aws:rds-db:{region}:{account}:dbuser:{cluster-resource-id}/*"
    },
    {
      "Sid": "AllowSSMSigningSecrets",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters", "ssm:PutParameter"],
      "Resource": "arn:aws:ssm:{region}:{account}:parameter/*"
    },
    {
      "Sid": "AllowKMSForGatekeeperServices",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:{region}:{account}:key/{kms-key-id}",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": [
            "s3.{region}.amazonaws.com",
            "sqs.{region}.amazonaws.com",
            "rds.{region}.amazonaws.com",
            "ssm.{region}.amazonaws.com"
          ]
        }
      }
    }
  ]
}
```

#### Ingest Worker

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowListUploadArtifactsBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::grapevine-upload-artifacts"
    },
    {
      "Sid": "AllowReadUploadArtifactsObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::grapevine-upload-artifacts/*"
    },
    {
      "Sid": "AllowListIngestWebhookDataBucket",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::grapevine-ingest-webhook-data"
    },
    {
      "Sid": "AllowReadWriteIngestWebhookDataObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::grapevine-ingest-webhook-data/*"
    },
    {
      "Sid": "AllowSQSReceiveIngestJobs",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueUrl",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:{region}:{account}:grapevine-ingest-jobs.fifo"
    },
    {
      "Sid": "AllowSQSSendToIndexAndIngestJobs",
      "Effect": "Allow",
      "Action": ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"],
      "Resource": [
        "arn:aws:sqs:{region}:{account}:grapevine-index-jobs.fifo",
        "arn:aws:sqs:{region}:{account}:grapevine-ingest-jobs.fifo"
      ]
    },
    {
      "Sid": "AllowRDSConnect",
      "Effect": "Allow",
      "Action": ["rds-db:connect"],
      "Resource": "arn:aws:rds-db:{region}:{account}:dbuser:{cluster-resource-id}/*"
    },
    {
      "Sid": "AllowOpenSearchAccess",
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost",
        "es:ESHttpPut",
        "es:ESHttpDelete",
        "es:ESHttpHead"
      ],
      "Resource": [
        "arn:aws:es:{region}:{account}:domain/{domain-name}",
        "arn:aws:es:{region}:{account}:domain/{domain-name}/*"
      ]
    },
    {
      "Sid": "AllowSSMParameterAccess",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:PutParameter",
        "ssm:DeleteParameter"
      ],
      "Resource": "arn:aws:ssm:{region}:{account}:parameter/*"
    },
    {
      "Sid": "AllowKMSForIngestJobsServices",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:Encrypt"],
      "Resource": "arn:aws:kms:{region}:{account}:key/{kms-key-id}",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": [
            "s3.{region}.amazonaws.com",
            "sqs.{region}.amazonaws.com",
            "rds.{region}.amazonaws.com",
            "es.{region}.amazonaws.com",
            "ssm.{region}.amazonaws.com"
          ]
        }
      }
    }
  ]
}
```

#### Index Worker

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSQSReceiveIndexJobs",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueUrl",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:{region}:{account}:grapevine-index-jobs.fifo"
    },
    {
      "Sid": "AllowSQSSendToSlackJobs",
      "Effect": "Allow",
      "Action": ["sqs:SendMessage", "sqs:GetQueueUrl", "sqs:GetQueueAttributes"],
      "Resource": "arn:aws:sqs:{region}:{account}:grapevine-slack-jobs.fifo"
    },
    {
      "Sid": "AllowRDSConnect",
      "Effect": "Allow",
      "Action": ["rds-db:connect"],
      "Resource": "arn:aws:rds-db:{region}:{account}:dbuser:{cluster-resource-id}/*"
    },
    {
      "Sid": "AllowOpenSearchAccess",
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost",
        "es:ESHttpPut",
        "es:ESHttpDelete",
        "es:ESHttpHead"
      ],
      "Resource": [
        "arn:aws:es:{region}:{account}:domain/{domain-name}",
        "arn:aws:es:{region}:{account}:domain/{domain-name}/*"
      ]
    },
    {
      "Sid": "AllowSSMAPIKeys",
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:GetParameters"],
      "Resource": [
        "arn:aws:ssm:{region}:{account}:parameter/*/api-key/*",
        "arn:aws:ssm:{region}:{account}:parameter/*/credentials/*"
      ]
    },
    {
      "Sid": "AllowKMSForIndexJobsServices",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:{region}:{account}:key/{kms-key-id}",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": [
            "sqs.{region}.amazonaws.com",
            "rds.{region}.amazonaws.com",
            "es.{region}.amazonaws.com",
            "ssm.{region}.amazonaws.com"
          ]
        }
      }
    }
  ]
}
```

#### Slack Bot

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowSQSSlackJobs",
      "Effect": "Allow",
      "Action": [
        "sqs:ReceiveMessage",
        "sqs:SendMessage",
        "sqs:DeleteMessage",
        "sqs:ChangeMessageVisibility",
        "sqs:GetQueueUrl",
        "sqs:GetQueueAttributes"
      ],
      "Resource": "arn:aws:sqs:{region}:{account}:grapevine-slack-jobs.fifo"
    },
    {
      "Sid": "AllowRDSConnect",
      "Effect": "Allow",
      "Action": ["rds-db:connect"],
      "Resource": "arn:aws:rds-db:{region}:{account}:dbuser:{cluster-resource-id}/*"
    },
    {
      "Sid": "AllowSSMParameterAccess",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:PutParameter",
        "ssm:DeleteParameter"
      ],
      "Resource": "arn:aws:ssm:{region}:{account}:parameter/*"
    },
    {
      "Sid": "AllowKMSForSlackbotServices",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey"],
      "Resource": "arn:aws:kms:{region}:{account}:key/{kms-key-id}",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": [
            "sqs.{region}.amazonaws.com",
            "rds.{region}.amazonaws.com",
            "ssm.{region}.amazonaws.com"
          ]
        }
      }
    }
  ]
}
```

#### Steward (Tenant Provisioning)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowRDSAdminAccess",
      "Effect": "Allow",
      "Action": [
        "rds:CreateDBCluster",
        "rds:CreateDBInstance",
        "rds:DescribeDBClusters",
        "rds:DescribeDBInstances",
        "rds:ModifyDBCluster",
        "rds:ModifyDBInstance",
        "rds-db:connect"
      ],
      "Resource": [
        "arn:aws:rds:{region}:{account}:cluster:{cluster-identifier}",
        "arn:aws:rds:{region}:{account}:cluster:{cluster-identifier}:*",
        "arn:aws:rds-db:{region}:{account}:dbuser:{cluster-resource-id}/*"
      ]
    },
    {
      "Sid": "AllowOpenSearchAdminAccess",
      "Effect": "Allow",
      "Action": [
        "es:ESHttpGet",
        "es:ESHttpPost",
        "es:ESHttpPut",
        "es:ESHttpDelete",
        "es:ESHttpHead",
        "es:ESHttpPatch"
      ],
      "Resource": [
        "arn:aws:es:{region}:{account}:domain/{domain-name}",
        "arn:aws:es:{region}:{account}:domain/{domain-name}/*"
      ]
    },
    {
      "Sid": "AllowSSMTenantCredentials",
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters",
        "ssm:PutParameter",
        "ssm:DeleteParameter"
      ],
      "Resource": "arn:aws:ssm:{region}:{account}:parameter/*/credentials/*"
    },
    {
      "Sid": "AllowKMSForStewardServices",
      "Effect": "Allow",
      "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:Encrypt", "kms:ReEncrypt*"],
      "Resource": "arn:aws:kms:{region}:{account}:key/{kms-key-id}",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": [
            "rds.{region}.amazonaws.com",
            "es.{region}.amazonaws.com",
            "ssm.{region}.amazonaws.com"
          ]
        }
      }
    }
  ]
}
```

#### Policy Template Variables

Replace these placeholders in the policies above:

| Placeholder                     | Description                                    | Example                        |
| ------------------------------- | ---------------------------------------------- | ------------------------------ |
| `{region}`                      | AWS region                                     | `us-east-1`                    |
| `{account}`                     | AWS account ID                                 | `123456789012`                 |
| `{cluster-resource-id}`         | RDS cluster resource ID (found in RDS console) | `cluster-ABCDEFGHIJ`           |
| `{cluster-identifier}`          | RDS cluster identifier                         | `grapevine`                    |
| `{domain-name}`                 | OpenSearch domain name                         | `grapevine`                    |
| `{kms-key-id}`                  | KMS key ID (from the KMS key you created)      | `12345678-1234-...`            |
| `grapevine-upload-artifacts`    | S3 bucket for file uploads (globally unique)   | `mycompany-grapevine-uploads`  |
| `grapevine-ingest-webhook-data` | S3 bucket for webhook data (globally unique)   | `mycompany-grapevine-webhooks` |
| `grapevine-ingest-jobs.fifo`    | SQS queue for ingest jobs                      | `mycompany-ingest-jobs.fifo`   |
| `grapevine-index-jobs.fifo`     | SQS queue for index jobs                       | `mycompany-index-jobs.fifo`    |
| `grapevine-slack-jobs.fifo`     | SQS queue for Slack jobs                       | `mycompany-slack-jobs.fifo`    |

### SQS Queues

Create three FIFO queues with their corresponding dead letter queues. All queues use KMS encryption.

#### Main Queues

```bash
# Set your KMS key ARN
KMS_KEY_ARN="arn:aws:kms:us-east-1:123456789012:key/your-key-id"

# Ingest jobs queue (webhook processing)
aws sqs create-queue \
  --queue-name "grapevine-ingest-jobs.fifo" \
  --attributes '{
    "FifoQueue": "true",
    "FifoThroughputLimit": "perMessageGroupId",
    "DeduplicationScope": "messageGroup",
    "ContentBasedDeduplication": "false",
    "VisibilityTimeoutSeconds": "30",
    "MessageRetentionPeriod": "1209600",
    "ReceiveMessageWaitTimeSeconds": "20",
    "KmsMasterKeyId": "'${KMS_KEY_ARN}'",
    "KmsDataKeyReusePeriodSeconds": "300",
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:123456789012:grapevine-ingest-jobs-dlq.fifo\",\"maxReceiveCount\":5}"
  }'

# Index jobs queue (embedding generation)
aws sqs create-queue \
  --queue-name "grapevine-index-jobs.fifo" \
  --attributes '{
    "FifoQueue": "true",
    "FifoThroughputLimit": "perMessageGroupId",
    "DeduplicationScope": "messageGroup",
    "ContentBasedDeduplication": "false",
    "VisibilityTimeoutSeconds": "30",
    "MessageRetentionPeriod": "1209600",
    "ReceiveMessageWaitTimeSeconds": "20",
    "KmsMasterKeyId": "'${KMS_KEY_ARN}'",
    "KmsDataKeyReusePeriodSeconds": "300",
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:123456789012:grapevine-index-jobs-dlq.fifo\",\"maxReceiveCount\":5}"
  }'

# Slack bot jobs queue
aws sqs create-queue \
  --queue-name "grapevine-slack-jobs.fifo" \
  --attributes '{
    "FifoQueue": "true",
    "FifoThroughputLimit": "perMessageGroupId",
    "DeduplicationScope": "messageGroup",
    "ContentBasedDeduplication": "true",
    "VisibilityTimeoutSeconds": "30",
    "MessageRetentionPeriod": "1209600",
    "ReceiveMessageWaitTimeSeconds": "20",
    "KmsMasterKeyId": "'${KMS_KEY_ARN}'",
    "KmsDataKeyReusePeriodSeconds": "300",
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:123456789012:grapevine-slack-jobs-dlq.fifo\",\"maxReceiveCount\":5}"
  }'
```

#### Dead Letter Queues

Create DLQs **before** the main queues (they're referenced in the redrive policy):

```bash
# Ingest jobs DLQ
aws sqs create-queue \
  --queue-name "grapevine-ingest-jobs-dlq.fifo" \
  --attributes '{
    "FifoQueue": "true",
    "ContentBasedDeduplication": "false",
    "VisibilityTimeoutSeconds": "300",
    "MessageRetentionPeriod": "1209600",
    "KmsMasterKeyId": "'${KMS_KEY_ARN}'",
    "KmsDataKeyReusePeriodSeconds": "300",
    "RedriveAllowPolicy": "{\"redrivePermission\":\"allowAll\"}"
  }'

# Index jobs DLQ
aws sqs create-queue \
  --queue-name "grapevine-index-jobs-dlq.fifo" \
  --attributes '{
    "FifoQueue": "true",
    "ContentBasedDeduplication": "false",
    "VisibilityTimeoutSeconds": "300",
    "MessageRetentionPeriod": "1209600",
    "KmsMasterKeyId": "'${KMS_KEY_ARN}'",
    "KmsDataKeyReusePeriodSeconds": "300",
    "RedriveAllowPolicy": "{\"redrivePermission\":\"allowAll\"}"
  }'

# Slack jobs DLQ
aws sqs create-queue \
  --queue-name "grapevine-slack-jobs-dlq.fifo" \
  --attributes '{
    "FifoQueue": "true",
    "ContentBasedDeduplication": "false",
    "VisibilityTimeoutSeconds": "300",
    "MessageRetentionPeriod": "1209600",
    "KmsMasterKeyId": "'${KMS_KEY_ARN}'",
    "KmsDataKeyReusePeriodSeconds": "300",
    "RedriveAllowPolicy": "{\"redrivePermission\":\"allowAll\"}"
  }'
```

#### Queue Configuration Summary

| Queue             | ContentBasedDeduplication | VisibilityTimeout | Retention | MaxReceiveCount |
| ----------------- | ------------------------- | ----------------- | --------- | --------------- |
| ingest-jobs       | false                     | 30s               | 14 days   | 5               |
| index-jobs        | false                     | 30s               | 14 days   | 5               |
| slack-jobs        | true                      | 30s               | 14 days   | 5               |
| \*-dlq (all DLQs) | false                     | 300s              | 14 days   | -               |

**Environment variables:**

```bash
INGEST_JOBS_QUEUE_ARN=arn:aws:sqs:us-east-1:123456789012:grapevine-ingest-jobs.fifo
INDEX_JOBS_QUEUE_ARN=arn:aws:sqs:us-east-1:123456789012:grapevine-index-jobs.fifo
SLACK_JOBS_QUEUE_ARN=arn:aws:sqs:us-east-1:123456789012:grapevine-slack-jobs.fifo
```

### S3 Buckets

Create two buckets with KMS encryption and lifecycle policies:

```bash
KMS_KEY_ARN="arn:aws:kms:us-east-1:123456789012:key/your-key-id"

# Upload artifacts bucket (file uploads, Slack exports)
aws s3 mb s3://grapevine-upload-artifacts

# Ingest webhook data bucket (large webhook payloads for SQS extended client)
aws s3 mb s3://grapevine-ingest-webhook-data
```

**Configure server-side encryption** with KMS:

```bash
# Upload artifacts bucket
aws s3api put-bucket-encryption \
  --bucket grapevine-upload-artifacts \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "'${KMS_KEY_ARN}'"
      },
      "BucketKeyEnabled": true
    }]
  }'

# Ingest webhook data bucket
aws s3api put-bucket-encryption \
  --bucket grapevine-ingest-webhook-data \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "'${KMS_KEY_ARN}'"
      },
      "BucketKeyEnabled": true
    }]
  }'
```

**Block public access** for both buckets:

```bash
for BUCKET in "grapevine-upload-artifacts" "grapevine-ingest-webhook-data"; do
  aws s3api put-public-access-block \
    --bucket ${BUCKET} \
    --public-access-block-configuration '{
      "BlockPublicAcls": true,
      "IgnorePublicAcls": true,
      "BlockPublicPolicy": true,
      "RestrictPublicBuckets": true
    }'
done
```

**Configure lifecycle policies** to auto-delete objects after 7 days:

```bash
LIFECYCLE_POLICY='{
  "Rules": [{
    "ID": "delete_objects_after_7days",
    "Status": "Enabled",
    "Expiration": { "Days": 7 },
    "AbortIncompleteMultipartUpload": { "DaysAfterInitiation": 1 }
  }]
}'

aws s3api put-bucket-lifecycle-configuration \
  --bucket grapevine-upload-artifacts \
  --lifecycle-configuration "${LIFECYCLE_POLICY}"

aws s3api put-bucket-lifecycle-configuration \
  --bucket grapevine-ingest-webhook-data \
  --lifecycle-configuration "${LIFECYCLE_POLICY}"
```

**Environment variables:**

```bash
S3_BUCKET_NAME=grapevine-upload-artifacts
INGEST_WEBHOOK_DATA_S3_BUCKET_NAME=grapevine-ingest-webhook-data
```

### SSM Parameter Store

SSM stores tenant credentials, API keys, and webhook signing secrets. The Steward service manages parameters automatically when provisioning tenants.

**Parameter structure:**

```text
/{tenant_id}/credentials/postgresql/db_name      # Tenant database name
/{tenant_id}/credentials/postgresql/db_rw_user   # Database read-write username
/{tenant_id}/credentials/postgresql/db_rw_pass   # Database read-write password
/{tenant_id}/signing-secret/{source}             # Webhook signing secrets (e.g., github, slack, linear)
/{tenant_id}/api-key/{key_name}                  # API keys for external services
```

**Configuration:**

- All parameters are encrypted with the Grapevine KMS key
- Parameters are created automatically by the Steward service during tenant provisioning
- No manual setup required - just ensure IAM roles have the correct SSM permissions

## External Services

### WorkOS (Authentication)

See [Authentication Setup](auth-setup.md) for detailed configuration.

**Quick setup:**

1. Create account at [workos.com](https://workos.com)
2. Enable AuthKit and Dynamic Client Registration
3. Configure redirect URIs for your domain

**Environment variables:**

```bash
WORKOS_API_KEY=sk_live_...
WORKOS_CLIENT_ID=client_...
AUTHKIT_DOMAIN=https://your-project.authkit.app
```

### OpenAI

OpenAI generates document embeddings using `text-embedding-3-large`.

1. Create account at [platform.openai.com](https://platform.openai.com)
2. Create an API key with appropriate rate limits

**Environment variable:**

```bash
OPENAI_API_KEY=sk-...
```

### Optional Services

For billing (Stripe), analytics (Amplitude, PostHog), and observability (Langfuse, New Relic), see [Feature Configuration](optional-features.md).

## Deployment

### Kubernetes (Recommended)

Grapevine includes Kubernetes configurations in `kustomize/`. See [kustomize/README.md](../kustomize/README.md) for details.

```bash
# Deploy to production
kubectl apply -k kustomize/overlays/production/

# Deploy to staging
kubectl apply -k kustomize/overlays/staging/
```

### Service Resource Requirements

**API Services:**

| Service               | CPU Request | CPU Limit | Memory Request | Memory Limit |
| --------------------- | ----------- | --------- | -------------- | ------------ |
| ingest-gatekeeper     | 250m        | 1000m     | 512Mi          | 1Gi          |
| grapevine-api (MCP)   | 500m        | 2000m     | 1Gi            | 4Gi          |
| grapevine-app (Admin) | 250m        | 1000m     | 512Mi          | 1Gi          |
| steward               | 250m        | 500m      | 256Mi          | 512Mi        |

**Background Workers:**

| Service       | CPU Request | CPU Limit | Memory Request | Memory Limit |
| ------------- | ----------- | --------- | -------------- | ------------ |
| index-worker  | 500m        | 1000m     | 1Gi            | 2Gi          |
| ingest-worker | 250m        | 1000m     | 512Mi          | 1Gi          |
| slackbot      | 250m        | 500m      | 256Mi          | 512Mi        |

### High Availability

1. **PostgreSQL**: Multi-AZ deployment with automatic failover
2. **OpenSearch**: 3+ node cluster with dedicated master nodes
3. **Redis**: Cluster mode with replication
4. **Application**: Multiple replicas per service behind load balancer

### Database Migrations

Run migrations before deploying new versions:

```bash
# Run all pending migrations
uv run python -m src.migrations.cli migrate --control --all-tenants

# Check migration status
uv run python -m src.migrations.cli status
```

See [Migrations Guide](migrations.md) for complete documentation.

## Operations

### Health Check Endpoints

| Service           | Endpoint                | Purpose         |
| ----------------- | ----------------------- | --------------- |
| MCP Server        | `GET /health/live`      | Liveness probe  |
| MCP Server        | `GET /health/ready`     | Readiness probe |
| Ingest Gatekeeper | `GET /health`           | Health check    |
| Admin Backend     | `GET /api/health/ready` | Readiness probe |
| Ingest Worker     | `GET /health/live`      | Liveness probe  |
| Index Worker      | `GET /health/live`      | Liveness probe  |

### Upgrading

1. **Backup databases** before upgrading
2. **Pull latest changes**: `git pull origin main`
3. **Run migrations**: `uv run python -m src.migrations.cli migrate --control --all-tenants`
4. **Deploy new images** via rolling update

### Monitoring

Configure alerting for:

- Health check failures
- SQS queue depth (indicates processing backlog)
- Error rates in application logs
- Database connection pool exhaustion
- OpenSearch cluster health

### Troubleshooting

#### Database Connection Errors

- Verify security groups allow connections from application
- Check SSL configuration matches connection string
- Verify credentials in SSM are correct

#### OpenSearch Issues

- Check cluster health: `GET /_cluster/health`
- Verify fine-grained access control credentials
- Check security group rules

#### SQS Processing Issues

- Check IAM permissions include SQS access
- Verify queue ARNs are correct (must end in `.fifo`)
- Monitor dead-letter queues for failed messages

#### Turbopuffer Errors

- Verify API key is valid
- Check region matches your account
- Ensure `GRAPEVINE_ENVIRONMENT` is set correctly

#### Authentication Errors

See [Authentication Setup - Troubleshooting](auth-setup.md#troubleshooting).

### Getting Help

- Check [GitHub Issues](https://github.com/gathertown/grapevine/issues)
- Review [Architecture Overview](ARCHITECTURE.md)
