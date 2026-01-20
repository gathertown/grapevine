# Grapevine

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A self-hostable unified knowledge store that ingests information from corporate knowledge sources and makes it searchable through an MCP (Model Context Protocol) server.

## What is Grapevine?

Grapevine is an open source knowledge aggregation platform that:

- **Connects to your tools**: Integrates with Slack, Notion, Linear, GitHub, Google Drive, HubSpot, Salesforce, and many more
- **Indexes everything**: Extracts, processes, and embeds your company's knowledge into a unified search index
- **Provides semantic search**: Uses AI embeddings to find relevant information across all your data sources
- **Exposes an MCP server**: Allows AI assistants (Claude, etc.) to search and retrieve your company's knowledge
- **Includes a Slack bot**: Optional AI-powered question answering directly in Slack

## Quick Start

### Prerequisites

- Docker and Docker Compose
- PostgreSQL 15+ with pgvector extension
- OpenSearch 2.x
- Redis 6+
- OpenAI API key (for embeddings)
- WorkOS account (for authentication)

### Local Development Setup

1. **Clone and install dependencies:**

   ```bash
   git clone https://github.com/gathertown/grapevine.git
   cd grapevine
   
   # Install mise for toolchain management
   brew install mise
   # Set up your shell: https://mise.jdx.dev/getting-started.html#activate-mise
   
   mise install
   uv sync
   ```

2. **Configure environment:**

   Copy `.env.example` to `.env` and configure your settings:

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Start infrastructure with Tilt:**

   ```bash
   # Build JS dependencies first
   cd js-services && yarn install && yarn build && cd ..
   
   # Start all services
   mise dev
   
   # One-time database setup (after PostgreSQL starts)
   mise setup
   ```

4. **Access the admin UI:**
   
   Open http://localhost:5173 to configure data sources and onboard your organization.

### Docker Compose (Production-like)

For a production-like deployment, see [docs/SELF_HOSTING.md](docs/SELF_HOSTING.md).

## Configuration

All settings are configured via environment variables. See `.env.example` for the complete list.

### Required Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/grapevine
CONTROL_DATABASE_URL=postgresql://user:pass@localhost:5432/grapevine_control

# Search
OPENSEARCH_DOMAIN_HOST=localhost
OPENSEARCH_PORT=9200

# Cache
REDIS_PRIMARY_ENDPOINT=redis://localhost:6379

# AI/Embeddings
OPENAI_API_KEY=sk-...

# Authentication
WORKOS_API_KEY=...
WORKOS_CLIENT_ID=...

# AWS (use LocalStack for local dev)
AWS_REGION=us-east-1
AWS_ENDPOINT_URL=http://localhost:4566  # LocalStack
```

### Optional Features

Many features are optional and disabled by default:

- **Billing/Usage Tracking**: Set `BILLING_ENABLED=true` with Stripe keys
- **Analytics**: Configure Amplitude, PostHog, or Langfuse keys
- **Monitoring**: Set New Relic license key

See [docs/optional-features.md](docs/optional-features.md) for details.

## MCP Server

The MCP server provides search and retrieval capabilities for AI assistants.

### Starting the Server

```bash
uv run python -m src.mcp.server
```

By default, the server runs on port 8000. Configure with `--host` and `--port` flags.

### Available Tools

- **Navigation Tools**: `semantic_search`, `keyword_search` - Find documents matching a query
- **Fetching Tools**: `get_document`, `get_document_metadata` - Retrieve document contents
- **Agent Tools**: `ask` - AI-powered question answering using the knowledge store

### Generating Service Tokens

For services that need to authenticate with the MCP server:

```bash
uv run python scripts/generate_mcp_token.py --tenant-id <tenant_id>

# With custom expiry
uv run python scripts/generate_mcp_token.py \
  --tenant-id <tenant_id> \
  --expires-in 30d \
  --description "Production indexing service"
```

## Architecture

Grapevine consists of several interconnected services:

### Core Services

| Service | Description |
|---------|-------------|
| **MCP Server** | Model Context Protocol server for search and document retrieval |
| **Admin UI** | React frontend + Express backend for configuration and onboarding |
| **Ingest Gatekeeper** | Webhook processor with signature verification |
| **Steward** | Tenant provisioning and lifecycle management |

### Background Workers

| Worker | Description |
|--------|-------------|
| **Ingest Worker** | Processes webhook data and transforms into documents |
| **Index Worker** | Generates embeddings and maintains search indices |
| **Slack Bot** | AI-powered question answering in Slack (optional) |

### Data Flow

```
External Services → Webhooks → Gatekeeper → SQS → Ingest Worker
                                                      ↓
                                               Documents → Index Worker → OpenSearch + PostgreSQL
                                                                               ↓
                                                      MCP Server ← AI Assistants / Slack Bot
```

### Supported Data Sources

Grapevine includes connectors for:

- **Communication**: Slack, Gmail, Intercom
- **Project Management**: Linear, Jira, Asana, Monday, ClickUp, Trello, Teamwork
- **Documentation**: Notion, Confluence, Google Drive
- **Code**: GitHub, GitLab
- **CRM**: HubSpot, Salesforce, Pipedrive, Attio
- **Design**: Figma, Canva
- **Analytics**: PostHog
- **Meetings**: Fireflies, Gong
- **Support**: Zendesk, Pylon
- **Custom**: Upload your own documents

## Development

### Code Quality

```bash
# Python
uv run ruff check --fix    # Lint and auto-fix
uv run ruff format         # Format
uv run mypy                # Type check
uv run vulture             # Dead code detection

# JavaScript/TypeScript
cd js-services
yarn lint:fix              # Lint and auto-fix
yarn format                # Format
yarn type-check            # Type check
yarn build                 # Build all services
```

### Running Tests

```bash
# Python tests
uv sync --group test
uv run pytest tests/ -v

# JavaScript tests
cd js-services && yarn test
```

### Database Migrations

```bash
# Create a new migration
mise migrations create tenant "add user preferences table"

# Run migrations
mise migrations migrate --control --all-tenants

# Check status
mise migrations status
```

See [docs/migrations.md](docs/migrations.md) for complete documentation.

### Local Webhooks

For local webhook development, use ngrok:

```bash
ngrok http 8001
```

Then configure webhooks to point to `https://<your-ngrok-domain>/<tenant-id>/webhooks/<source>`.

## Deployment

### Kubernetes

Grapevine includes Kubernetes deployment configurations in `kustomize/`:

**Resource Requirements (approximate):**
- Total: 2.5-8 CPU cores, 4-11GB RAM

See `kustomize/` for detailed deployment manifests.

### Adding New Data Sources

1. Create connector directory: `connectors/{source}/`
2. Implement document types (extend `BaseDocument`, `BaseChunk`)
3. Implement extractor (extend `BaseExtractor`)
4. Implement transformer (extend `BaseTransformer`)
5. Add webhook endpoint in gatekeeper
6. Register in ingest and index workers
7. Update admin UI for configuration

See [docs/connector-ingestion-implementation-guide.md](docs/connector-ingestion-implementation-guide.md).

## Documentation

- [Self-Hosting Guide](docs/SELF_HOSTING.md) - Production deployment instructions
- [Architecture](docs/ARCHITECTURE.md) - Detailed system architecture
- [Migrations](docs/migrations.md) - Database migration system
- [Feature Flags](docs/feature-flags.md) - Feature flag configuration
- [Optional Features](docs/optional-features.md) - Analytics, billing, etc.
- [Connector Guide](docs/connector-ingestion-implementation-guide.md) - Adding new data sources

## Requirements

- Python 3.13+
- Node.js 20+
- PostgreSQL 15+ with pgvector extension
- OpenSearch 2.x
- Redis 6+
- WorkOS account (authentication)
- OpenAI API key (embeddings)

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines. Note that this repository is provided as-is without active maintenance.

## License

MIT License - see [LICENSE](LICENSE) for details.
