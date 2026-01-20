# AGENTS.md

This file provides guidance to AI agents when working with code in this repository.

## Project Overview

Grapevine is a real-time unified knowledge store that ingests information from various corporate knowledge sources (GitHub, Slack, Notion, Linear, Google Drive, and HubSpot) and provides semantic search capabilities through an MCP (Model Context Protocol) server. It's a collection of services working together (ingest-gatekeeper, MCP server, admin UI/API, Slack bot, ingest workers, index workers) to provide an MCP and Slack bot experience that understands all of the information at your company and helps you easily answer internal questions.

## Development Commands

### Environment Setup

```bash
# Install dependencies
mise install

# Start dev environment
mise dev
```

### Testing (Python)

Grapevine uses pytest for Python testing. Tests are provided via the test dependency group and should be run with uv:

```bash
# Install test dependencies
uv sync --group test

# Run tests
uv run pytest tests/ -v
```

Tests include MCP tool tests (keyword and semantic search) and use real backends (OpenSearch + Postgres), so ensure your environment is configured before running.

### Code Quality

```bash
# Install test dependencies (includes mypy and ruff)
uv sync --group test

# Run type checking
uv run mypy

# Run linting
uv run ruff check

# Run formatting
uv run ruff format

# Auto-fix linting issues
uv run ruff check --fix

# Auto-fix with unsafe fixes (for more aggressive fixes)
uv run ruff check --fix --unsafe-fixes
```

### Dead Code Detection

```bash
# Primary tool: Vulture (detects both globally unused and unreachable code)
uv run vulture

# Detect unreachable code with vulture (60%+ confidence)
uv run vulture --min-confidence 60

# Detect only 100% certain dead code with vulture
uv run vulture --min-confidence 100

# Run custom autofix script for 100% confident vulture issues
 scripts/vulture_autofix.py
```

**IMPORTANT**: Always run typing, linting, formatting, and dead code checks after making any code changes:

1. **Auto-fix lint issues first**: `uv run ruff check --fix` (try `--unsafe-fixes` if needed)
2. **Format code**: `uv run ruff format`
3. **Verify lint passes**: `uv run ruff check`
4. **Check types**: `uv run mypy`
5. **Check for dead code**: `uv run vulture`

These commands must be run after every code modification to maintain code quality standards.

### JavaScript/TypeScript Services Code Quality

For JavaScript/TypeScript services in `js-services/`:

```bash
# Navigate to the js-services directory
cd js-services

# Install dependencies
yarn install

# Run linting for all services
yarn lint

# Run linting for specific service
yarn nx run slack-bot:lint

# Auto-fix linting issues
yarn lint:fix

# Run type checking for all services
yarn type-check

# Format code for all services
yarn format

# Check formatting
yarn format:check

# Build all services
yarn build

# Build specific service
yarn nx run slack-bot:build

# Run development server with hot-reloading
yarn nx run slack-bot:serve:dev
```

**IMPORTANT**: Always run the following after making any code changes to JavaScript/TypeScript services:

1. **Format code**: `yarn format`
2. **Verify lint passes**: `yarn lint`
3. **Check types**: `yarn type-check`
4. **Build**: `yarn build`

These commands must be run after every code modification to maintain code quality standards.

### JavaScript/TypeScript Testing

For JavaScript/TypeScript services in `js-services/`, Jest is configured for unit testing:

```bash
# Navigate to the js-services directory
cd js-services

# Run all tests for all services
yarn test

# Run tests for specific service
yarn nx run admin-frontend:test
yarn nx run admin-backend:test
yarn nx run slack-bot:test

# Run tests in watch mode for development
yarn nx run admin-frontend:test:watch
yarn nx run admin-backend:test:watch

# Run tests with coverage reporting
yarn nx run admin-frontend:test:coverage
yarn nx run admin-backend:test:coverage
```

**Test Configuration**:

- Jest is configured via `jest.config.cjs` in each service directory
- Frontend tests use jsdom environment for React component testing
- Backend tests use Node.js environment for API and utility function testing
- Test files should be placed in `__tests__` directories alongside source files
- TypeScript support is configured automatically

**Test Coverage**:

- Domain validation functions have comprehensive test suites covering all edge cases
- Both frontend and backend validation logic are tested for consistency
- Tests include protocol stripping, subdomain handling, path removal, and error cases

### Running Services

#### Development

To start dev environment:

```bash
mise dev
```

## Database Migrations

The project uses a comprehensive migration system for both control and tenant databases:

```bash
# Create a new migration
mise migrations create tenant "add user preferences table"

# Run migrations locally
mise migrations migrate --control --all-tenants

# Check migration status
mise migrations status

# List existing migrations
mise run migrations list

# Mark/unmark migrations (for manual maintenance)
mise migrations mark --apply 20250828000000 --control
mise migrations mark --unapply 20250828000000 --tenant abc123
mise migrations mark --DANGEROUS-apply-all --all-tenants --dry-run
```

**Migration Files Structure:**

- `migrations/control/` - Control database migrations
- `migrations/tenant/` - Tenant database migrations

For complete documentation, see [docs/migrations.md](docs/migrations.md).

## Usage Reporting CLI

Generate usage reports across all tenants:

```bash
# Generate usage report for all tenants (table format)
uv run python -m src.usage.cli report

# Generate report for specific tenant
uv run python -m src.usage.cli report --tenant abc123def456

# Export to JSON or CSV
uv run python -m src.usage.cli report --format json --output report.json
uv run python -m src.usage.cli report --format csv --output report.csv

# Show quick summary
uv run python -m src.usage.cli summary --days 30

# Reset trial for a tenant (resets trial_start_at and clears cache)
uv run python -m src.usage.cli reset-trial --tenant abc123def456

# Reset usage for a tenant (deletes all usage records)
uv run python -m src.usage.cli reset-usage --tenant abc123def456

# Enterprise plan management
uv run python -m src.usage.cli set-enterprise-plan abc123def456 50000
uv run python -m src.usage.cli show-enterprise-plan abc123def456
uv run python -m src.usage.cli remove-enterprise-plan abc123def456
```

## Architecture Overview

### Core Components

1. **MCP Server** (`src/mcp/`)

   - FastMCP-based server providing search and retrieval tools
   - Combines FastAPI HTTP endpoints with MCP protocol
   - Main entry point: `src/mcp/server.py`

2. **Ingest System** (`src/ingest/`)

   - FastAPI webhook server for real-time updates
   - Background task processing for document storage
   - Webhook endpoints: `/webhooks/github`, `/webhooks/slack`, etc.

3. **Document System** (`src/documents/`)

   - Base classes: `BaseChunk` and `BaseDocument`
   - Each source has specific document types (e.g., `GitHubPRDocument`)
   - Documents split into chunks for embedding and search

4. **Configuration** (`src/utils/config.py`)

   - Environment variables as primary source (e.g., `GITHUB_TOKEN`)
   - Per-tenant database configuration
   - Type-safe configuration access

5. **Admin Web UI** (`js-services/admin-frontend/` and `js-services/admin-backend/`)

   - React frontend (Vite + React 19) for configuration management
   - Express.js backend for API endpoints and database operations
   - Handles onboarding and setup for data sources
   - AWS S3 integration for file uploads
   - Multi-tenant organization management

6. **Slack Bot** (`js-services/slack-bot/`)

   - TypeScript Slack bot using Bolt framework
   - Tenant-aware question identification and answering
   - Integrates with per-tenant knowledge stores
   - SQS-based job processing for scalability
   - Includes Jest tests and deployment configuration

7. **Steward Service** (`src/steward/`)

   - Tenant provisioning and lifecycle management
   - Automated database and OpenSearch index creation
   - Multi-tenant resource management
   - AWS resource provisioning

8. **Ingest Gatekeeper** (`src/ingest/gatekeeper/`)
   - Multi-tenant webhook processor with signature verification
   - Tenant resolution using WorkOS organization IDs
   - SQS message publishing for background processing
   - Webhook signature verification and routing

### Data Flow

1. **Ingestion**: Sources extract data from APIs or webhooks
2. **Processing**: Transform into standardized document format
3. **Embedding**: Generate OpenAI embeddings (text-embedding-3-large)
4. **Storage**:
   - PostgreSQL: Document registry and vectors
   - Supabase: Blob storage
   - OpenSearch: Full-text search
   - Local files: `./data/<source>/*.jsonl`

### Key Patterns

- **Async-first**: All database operations are async
- **Type safety**: Generic types and Pydantic models throughout
- **Incremental updates**: Documents updated, not replaced
- **Chunk-based search**: Semantic search operates on document chunks
- **Environment flexibility**: Config file with env var overrides

### Database Schema

Documents are stored with:

- Metadata in PostgreSQL `documents` table
- Embeddings in PostgreSQL with pgvector
- Full content in Supabase blobs
- Search indices in OpenSearch

### Adding New Sources

1. Create document type in `src/documents/`
2. Implement source processor in `src/sources/`
3. Add webhook endpoint in `src/ingest/api.py`
4. Set required environment variables

## Gatekeeper Service

The gatekeeper service provides multi-tenant webhook processing with signature verification and SQS queuing.

### Running Gatekeeper

```bash
# Start gatekeeper service (runs on port 8001 by default)
python -m src.ingest.gatekeeper.main

# Or with uvicorn directly
uvicorn src.ingest.gatekeeper.main:app --host 0.0.0.0 --port 8001 --reload
```

### Gatekeeper Architecture

The gatekeeper service handles the following flow:

1. **Webhook Reception**: Receives webhooks from various sources (GitHub, Slack, Linear, Notion)
2. **Workspace ID Extraction**: Extracts workspace/organization IDs from webhook payloads
3. **Tenant Resolution**: Uses WorkOS organization IDs to identify tenants directly
4. **Signature Verification**: Retrieves tenant-specific signing secrets from AWS SSM and verifies webhook signatures
5. **STS Credential Generation**: Optionally generates temporary AWS credentials for tenant-specific processing
6. **SQS Publishing**: Publishes verified webhooks to AWS SQS for background processing

### Database Schema

The system uses a `tenants` table to manage tenant provisioning and identity:

```sql
CREATE TABLE tenants (
    id VARCHAR(255) PRIMARY KEY, -- Internal tenant ID (format: <16 hex chars>)
    workos_org_id VARCHAR(255) UNIQUE,
    state TEXT CHECK (state IN ('pending', 'provisioning', 'provisioned', 'error')),
    error_message TEXT,
    provisioned_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### AWS Integration

- **SSM Parameter Store**: Signing secrets stored as `/{tenant_id}/signing-secret/{source}`
- **STS AssumeRole**: Temporary credentials using role template: `arn:aws:iam::{account}:role/corporate-context-tenant-{tenant_id}`
- **SQS**: Webhooks published to queue configured in `SQS_WEBHOOK_QUEUE`

### Configuration

Gatekeeper-specific environment variables:

```bash
# Gatekeeper Configuration
GATEKEEPER_ENABLED=true
GATEKEEPER_PORT=8001
GATEKEEPER_GENERATE_STS_CREDENTIALS=true
GATEKEEPER_STS_DURATION=3600

# AWS Configuration
AWS_REGION=us-east-1
SQS_WEBHOOK_QUEUE=corporate-context-webhooks-staging
TENANT_ROLE_ARN_TEMPLATE="arn:aws:iam::{account}:role/corporate-context-tenant-{tenant_id}"
```

### Endpoints

- `GET /health` - Health check for all dependencies
- `POST /webhooks/github` - GitHub webhook processing
- `POST /webhooks/slack` - Slack webhook processing
- `POST /webhooks/linear` - Linear webhook processing
- `POST /webhooks/notion` - Notion webhook processing

## Testing

Grapevine includes integration tests that exercise the search functionality against real backends.

### Running Tests

1. **Install test dependencies:**

   ```bash
   uv sync --group test
   ```

2. **Run all integration tests:**

   ```bash
   uv run pytest tests/ -v
   ```

3. **Run specific test files:**

   ```bash
   # Keyword search tests
   uv run pytest tests/test_keyword_search.py -v

   # Semantic search tests
   uv run pytest tests/test_semantic_search.py -v
   ```

4. **Run specific test classes:**
   ```bash
   # Run specific test class from any file
   uv run pytest tests/test_keyword_search.py::TestKeywordSearchTool -v
   uv run pytest tests/test_semantic_search.py::TestSemanticSearchTool -v
   ```

### Test Requirements

- **Real Backends**: Tests connect to actual OpenSearch and PostgreSQL instances
- **Configuration**: Uses same environment variables as the application
- **Data**: Tests run against production data, no isolated test fixtures needed

## Important Notes

- The project uses Python 3.11+ features
- All webhook signatures must be verified
- Database connections use connection pooling
- Rate limiting is implemented for external APIs

## Development Philosophy

- EXTREMELY IMPORTANT: Unless explicitly stated, backwards compatibility isn't important - especially within an API boundary
- YOU MUST keep types in sync between `src/jobs/models.py` and `js-services/*/src/jobs/models.ts`
- Use the vendored design components heavily - we should very rarely be writing CSS ourselves or using basic HTML elements
- We shouldn't use exact px values, as they prevent us from being responsive across different devices
- Use Flex from the design system instead of div, and Text from the design system instead of span

### Vendored Design Components

The project includes a vendored design system in `js-services/gather-design-system/` and `js-services/gather-design-foundations/`. This is a local copy included in the repository.

**Key type exports include:**

- Layout: `FlexProps`, `BoxProps`
- Typography: `Text` component
- Form components: `ButtonProps`, `InputProps`, etc.
- UI elements: `ModalProps`, `TooltipProps`, `AvatarProps`, etc.

Types are automatically available when importing from the design system packages.

**Usage Guidelines:**

- Use `Flex` instead of `div` for layout containers
- Use `Text` instead of `span` for text content
- Prefer design system components over custom CSS
- Use responsive units instead of exact pixel values

## Environment Variable Management

### Frontend Environment Variables

The frontend uses different environment variable patterns for different deployment environments:

#### Local Development (Vite)

- **Pattern**: Use `VITE_` prefixed environment variables
- **Source**: Local `.env` files or shell environment
- **Examples**:
  ```bash
  VITE_BASE_DOMAIN=localhost
  VITE_FRONTEND_URL=http://localhost:5173
  VITE_WORKOS_CLIENT_ID=client_123...
  VITE_AMPLITUDE_API_KEY=abc123...
  ```

#### Production/Staging (Runtime Config Injection)

- **Pattern**: Use non-prefixed environment variables
- **Source**: Container environment variables, injected at runtime via `docker-entrypoint.sh`
- **Examples**:
  ```bash
  BASE_DOMAIN=example.com
  FRONTEND_URL=https://app.example.com
  WORKOS_CLIENT_ID=client_123...
  AMPLITUDE_API_KEY=abc123...
  ```

#### Key Points:

- **Do NOT special-case variables** in `vite.config.ts` - keep the pattern consistent
- **Local development** always uses `VITE_` prefixed variables that Vite exposes to client code
- **Production/staging** uses runtime config injection system where variables are injected into `window.__ENV_CONFIG__`
- **The frontend config system** (`js-services/admin-frontend/src/lib/config.ts`) automatically handles the dev vs prod split

#### Adding New Frontend Environment Variables:

1. **Add to TypeScript definitions** (`js-services/admin-frontend/src/vite-env.d.ts`):

   ```typescript
   readonly VITE_YOUR_NEW_VAR: string;
   ```

2. **Add to config interface** (`js-services/admin-frontend/src/lib/config.ts`):

   ```typescript
   export interface EnvConfig {
     YOUR_NEW_VAR?: string;
     // ...
   }
   ```

3. **Add to both development and production config blocks**:

   ```typescript
   // Development block
   YOUR_NEW_VAR: import.meta.env.VITE_YOUR_NEW_VAR,

   // Production uses runtime config automatically
   ```

4. **Add to runtime config injection** (`docker-entrypoint.sh`):

   ```bash
   sed -i "s|__YOUR_NEW_VAR__|${VITE_YOUR_NEW_VAR:-__YOUR_NEW_VAR__}|g" "$ENV_CONFIG_FILE"
   ```

5. **Add to runtime config template** (`js-services/admin-frontend/public/env-config.js`):
   ```javascript
   window.__ENV_CONFIG__ = {
     YOUR_NEW_VAR: '__YOUR_NEW_VAR__',
     // ...
   };
   ```

### Backend Environment Variables

Backend services (admin-backend, slack-bot) use environment variables directly without prefixes:

```bash
# Same for all environments (local, staging, production)
BASE_DOMAIN=localhost                    # or your domain
FRONTEND_URL=http://localhost:5173       # or https://app.yourdomain.com
DATABASE_URL=postgresql://...
JWT_SECRET=...
```

Backend services access these via `process.env.VARIABLE_NAME` regardless of environment.
