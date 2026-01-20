# Local Development Guide

This guide covers setting up Grapevine for local development. For production deployment, see [Self-Hosting Guide](SELF_HOSTING.md).

## Prerequisites

### Required Software

- **Docker** and **Docker Compose** (v2.0+)
- **Python 3.13+**
- **Node.js 20+** and **Yarn**
- **mise** (recommended) - Install with `brew install mise`
- **uv** - Python package manager (installed via mise or `pip install uv`)

### Required Accounts

Even for local development, you'll need accounts for these external services:

| Service         | Purpose                     | Signup                                             |
| --------------- | --------------------------- | -------------------------------------------------- |
| **Turbopuffer** | Vector database             | [turbopuffer.com](https://turbopuffer.com)         |
| **WorkOS**      | Authentication (AuthKit)    | [workos.com](https://workos.com)                   |
| **OpenAI**      | Embeddings generation       | [platform.openai.com](https://platform.openai.com) |

> **Note**: AWS services (SQS, S3, SSM, KMS) are emulated locally using [LocalStack](https://localstack.cloud/).

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/gathertown/grapevine.git
cd grapevine
```

### 2. Configure Environment Variables

Create a `.env` file in the project root:

```bash
# === Databases ===
CONTROL_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/grapevine_control
OPENSEARCH_DOMAIN_HOST=localhost
OPENSEARCH_PORT=9200
OPENSEARCH_ADMIN_USERNAME=admin
OPENSEARCH_ADMIN_PASSWORD=admin
REDIS_PRIMARY_ENDPOINT=redis://localhost:6379

# === Turbopuffer (required - no local emulation) ===
TURBOPUFFER_API_KEY=your-turbopuffer-api-key
TURBOPUFFER_REGION=us-east-1

# === OpenAI (required - no local emulation) ===
OPENAI_API_KEY=sk-your-openai-api-key

# === WorkOS (required - no local emulation) ===
AUTHKIT_DOMAIN=https://your-project.authkit.app
WORKOS_API_KEY=sk_your_workos_api_key
WORKOS_CLIENT_ID=client_your_workos_client_id

# === AWS/LocalStack ===
AWS_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost:4566
KMS_KEY_ID=alias/grapevine-ssm
INGEST_JOBS_QUEUE_ARN=arn:aws:sqs:us-east-1:000000000000:grapevine-ingest-jobs.fifo
INDEX_JOBS_QUEUE_ARN=arn:aws:sqs:us-east-1:000000000000:grapevine-index-jobs.fifo
SLACK_JOBS_QUEUE_ARN=arn:aws:sqs:us-east-1:000000000000:grapevine-slack-jobs.fifo
S3_BUCKET_NAME=grapevine-storage
INGEST_WEBHOOK_DATA_S3_BUCKET_NAME=grapevine-webhook-payloads

# === Application ===
GRAPEVINE_ENVIRONMENT=local
MCP_BASE_URL=http://localhost:8000
FRONTEND_URL=http://localhost:5173
BASE_DOMAIN=localhost
```

See [Feature Configuration](optional-features.md) for the complete list of environment variables.

### 3. Start Infrastructure Services

```bash
# Start PostgreSQL, OpenSearch, Redis, and LocalStack
docker compose --profile local-data up -d

# Initialize LocalStack resources (creates SQS queues, S3 buckets, KMS key)
uv run python scripts/localstack_init.py
```

### 4. Initialize the Database

```bash
# Install Python dependencies
pip install uv
uv sync

# Run database migrations
uv run python -m src.migrations.cli migrate --control --all-tenants
```

### 5. Start Application Services

```bash
# Start MCP server
uv run python -m src.mcp.server

# In another terminal - start admin backend
cd js-services && yarn install && yarn nx run admin-backend:serve:dev

# In another terminal - start admin frontend
yarn nx run admin-frontend:serve:dev
```

### 6. Access the Application

- **Admin UI**: <http://localhost:5173>
- **MCP Server**: <http://localhost:8000>
- **OpenSearch**: <http://localhost:9200>

## Using mise (Recommended)

If you have mise installed, you can start the entire development environment with a single command:

```bash
# Install all dependencies and start services
mise install
mise dev
```

This starts all services with hot-reloading enabled.

## Infrastructure Services

### PostgreSQL

The local PostgreSQL instance runs via Docker Compose on port 5432.

```bash
# Connect to PostgreSQL
psql postgresql://postgres:postgres@localhost:5432/grapevine_control

# View databases
\l

# View tables in control database
\dt
```

### OpenSearch

Single-node OpenSearch runs on port 9200 with security disabled for development.

```bash
# Check OpenSearch health
curl http://localhost:9200/_cluster/health?pretty

# List indices
curl http://localhost:9200/_cat/indices?v
```

### Redis

Redis runs on port 6379 without authentication.

```bash
# Connect to Redis
redis-cli

# Check connection
PING
```

### LocalStack (AWS Emulation)

LocalStack emulates AWS services locally on port 4566.

```bash
# List SQS queues
aws --endpoint-url=http://localhost:4566 sqs list-queues

# List S3 buckets
aws --endpoint-url=http://localhost:4566 s3 ls

# View SSM parameters
aws --endpoint-url=http://localhost:4566 ssm get-parameters-by-path --path "/" --recursive
```

## Running Background Workers

For full functionality, you may need to run background workers:

```bash
# Ingest worker (processes webhooks)
uv run python -m src.jobs.ingest_job_worker

# Index worker (generates embeddings)
uv run python -m src.jobs.index_job_worker
```

## Code Quality

After making changes, run the code quality checks:

### Python

```bash
# Auto-fix lint issues
uv run ruff check --fix

# Format code
uv run ruff format

# Verify lint passes
uv run ruff check

# Type checking
uv run mypy

# Dead code detection
uv run vulture
```

### JavaScript/TypeScript

```bash
cd js-services

# Format code
yarn format

# Lint
yarn lint

# Type checking
yarn type-check

# Build
yarn build
```

## Running Tests

### Python Tests

```bash
# Install test dependencies
uv sync --group test

# Run all tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_keyword_search.py -v
```

### JavaScript/TypeScript Tests

```bash
cd js-services

# Run all tests
yarn test

# Run tests for specific service
yarn nx run admin-frontend:test
yarn nx run admin-backend:test
```

## Troubleshooting

### Docker Compose Issues

```bash
# View container status
docker compose ps

# View logs for a specific service
docker compose logs postgres
docker compose logs opensearch
docker compose logs localstack

# Restart all services
docker compose --profile local-data down
docker compose --profile local-data up -d
```

### Database Connection Errors

- Ensure PostgreSQL container is running: `docker compose ps postgres`
- Check if port 5432 is available: `lsof -i :5432`
- Verify connection string in `.env`

### LocalStack Not Working

- Ensure LocalStack container is running: `docker compose ps localstack`
- Re-run initialization: `uv run python scripts/localstack_init.py`
- Check LocalStack logs: `docker compose logs localstack`

### OpenSearch Issues

- Wait for OpenSearch to fully start (can take 30-60 seconds)
- Check health: `curl http://localhost:9200/_cluster/health`
- View logs: `docker compose logs opensearch`

### WorkOS/Authentication Errors

- Verify `AUTHKIT_DOMAIN` matches your WorkOS project
- Ensure Dynamic Client Registration is enabled in WorkOS dashboard
- Check redirect URIs are configured correctly

## Related Documentation

- [Architecture Overview](ARCHITECTURE.md) - System design and data flow
- [Self-Hosting Guide](SELF_HOSTING.md) - Production deployment
- [Feature Configuration](optional-features.md) - Environment variables
- [Authentication Setup](auth-setup.md) - WorkOS/AuthKit configuration
- [Migrations Guide](migrations.md) - Database schema management
