# Architecture Overview

This document provides a comprehensive overview of Grapevine's architecture, explaining how the various components work together to provide a unified knowledge store.

## Table of Contents

- [System Overview](#system-overview)
- [Core Components](#core-components)
- [Data Flow](#data-flow)
- [Multi-Tenant Architecture](#multi-tenant-architecture)
- [Database Schema](#database-schema)
- [Search Architecture](#search-architecture)
- [Connector System](#connector-system)
- [Authentication & Security](#authentication--security)

## System Overview

Grapevine is a real-time unified knowledge store that:

1. **Ingests** data from corporate knowledge sources (Slack, GitHub, Notion, Linear, etc.)
2. **Processes** and transforms data into a standardized document format
3. **Indexes** documents with semantic embeddings for AI-powered search
4. **Serves** queries through an MCP (Model Context Protocol) server

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              External Services                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐           │
│  │  Slack  │  │ GitHub  │  │ Notion  │  │ Linear  │  │  etc.   │           │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘           │
└───────┼────────────┼────────────┼────────────┼────────────┼─────────────────┘
        │            │            │            │            │
        │         Webhooks / API Polling                    │
        ▼            ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Ingest Gatekeeper (Port 8001)                        │
│  • Webhook signature verification                                            │
│  • Tenant resolution via WorkOS org ID                                       │
│  • Rate limiting and validation                                              │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS SQS Queues                                  │
│  ┌─────────────────────┐    ┌─────────────────────┐                         │
│  │    Ingest Queue     │    │     Index Queue     │                         │
│  └──────────┬──────────┘    └──────────┬──────────┘                         │
└─────────────┼───────────────────────────┼───────────────────────────────────┘
              │                           │
              ▼                           ▼
┌─────────────────────────┐  ┌─────────────────────────┐
│     Ingest Workers      │  │     Index Workers       │
│  • Document extraction  │  │  • Embedding generation │
│  • Data transformation  │  │  • Vector indexing      │
│  • Metadata enrichment  │  │  • Search index update  │
└───────────┬─────────────┘  └───────────┬─────────────┘
            │                            │
            ▼                            ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Data Storage Layer                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │   PostgreSQL     │  │   Turbopuffer    │  │      Redis       │          │
│  │                  │  │                  │  │                  │          │
│  │  • Artifacts     │  │  • Embeddings    │  │  • Session cache │          │
│  │  • Metadata      │  │  • Vector search │  │  • Rate limits   │          │
│  │  • Documents     │  │                  │  │  • Job state     │          │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘          │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          MCP Server (Port 8000)                              │
│  • Semantic search (vector similarity)                                       │
│  • Keyword search (BM25 + full-text)                                        │
│  • Document retrieval                                                        │
│  • AI-powered Q&A (ask tool)                                                │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
              ┌──────────┐                   ┌──────────┐
              │ MCP      │                   │ Admin    │
              │ Clients  │                   │ UI       │
              └──────────┘                   └──────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                              AWS SQS Queues                                  │
│  ┌─────────────────────┐                                                    │
│  │   Slack Bot Queue   │                                                    │
│  └──────────┬──────────┘                                                    │
└─────────────┼───────────────────────────────────────────────────────────────┘
              │
              ▼
        ┌──────────┐
        │ Slack    │
        │ Bot      │
        └──────────┘
```

## Core Components

### 1. MCP Server (`src/mcp/`)

The MCP (Model Context Protocol) server is the primary query interface for Grapevine.

**Technology Stack:**

- FastMCP framework with FastAPI
- Python 3.13+
- Async/await throughout

**Key Features:**

- **Semantic Search**: Vector similarity search using OpenAI embeddings
- **Keyword Search**: BM25 full-text search via OpenSearch
- **Document Retrieval**: Fetch complete document contents
- **AI-Powered Q&A**: Agent-based question answering with citations

**Entry Point:** `src/mcp/server.py`

**Available Tools:**
| Tool | Description |
|------|-------------|
| `semantic_search` | Find documents by meaning using vector similarity |
| `keyword_search` | Find documents by exact terms using BM25 |
| `get_document` | Retrieve full document content by ID |
| `get_document_metadata` | Get document metadata without content |
| `ask` | AI agent that searches and answers questions |

### 2. Ingest Gatekeeper (`src/ingest/gatekeeper/`)

The gatekeeper receives webhooks from external services and routes them for processing.

**Responsibilities:**

- Webhook signature verification
- Tenant resolution from WorkOS organization IDs
- Request validation and rate limiting
- SQS message publishing

**Supported Webhook Sources:**

- GitHub (push, PR, issues, etc.)
- Slack (messages, channels, reactions)
- Linear (issues, projects, comments)
- Notion (page updates)
- And many more via connectors

### 3. Ingest Workers (`src/jobs/ingest_job_worker.py`)

Background workers that process incoming data from the SQS ingest queue.

**Processing Pipeline:**

1. Receive webhook/job from SQS
2. Load appropriate connector for the source
3. Extract raw data using the connector's extractor
4. Transform into standardized document format
5. Store artifacts in PostgreSQL artifacts table
6. Queue artifacts for indexing

### 4. Index Workers (`src/jobs/index_job_worker.py`)

Background workers that generate embeddings and update search indices.

**Processing Pipeline:**

1. Receive artifact from SQS index queue
2. Split artifact into chunks
3. Generate embeddings via OpenAI API (`text-embedding-3-large`)
4. Store embeddings in Turbopuffer (vector database)
5. Update OpenSearch full-text index

### 5. Admin Web UI (`js-services/admin-frontend/` and `js-services/admin-backend/`)

Web interface for configuration and administration.

**Frontend (React + Vite):**

- Organization setup and onboarding
- Data source configuration
- OAuth flow management
- Usage monitoring

**Backend (Express.js):**

- API endpoints for configuration
- Database operations
- OAuth token management
- S3 integration for file uploads

### 6. Steward Service (`src/steward/`)

Handles tenant provisioning and lifecycle management.

**Responsibilities:**

- Create tenant databases when new organizations sign up
- Apply database migrations to tenant databases
- Create OpenSearch indices per tenant
- Configure AWS SSM parameters for tenant secrets
- Manage tenant state transitions

### 7. Slack Bot (`js-services/slack-bot/`)

Optional Slack integration for asking questions directly in Slack.

**Architecture:**

- Consumes messages from a dedicated SQS queue
- Processes Slack events asynchronously for scalability

**Features:**

- Natural language question detection
- Integration with MCP `ask` tool
- Citation formatting for Slack
- Per-tenant configuration

## Data Flow

### Webhook Ingestion Flow

```
1. External Service (e.g., GitHub)
   │
   │ POST /webhooks/github
   ▼
2. Ingest Gatekeeper
   ├── Verify webhook signature using tenant's signing secret
   ├── Extract workspace/org ID from payload
   ├── Resolve tenant ID via WorkOS org mapping
   └── Publish to SQS ingest queue
   │
   ▼
3. Ingest Worker
   ├── Load GitHub connector
   ├── Parse webhook payload (GitHubPRExtractor, etc.)
   ├── Transform to GitHubPRDocument
   ├── Store in PostgreSQL artifacts table
   └── Publish to SQS index queue
   │
   ▼
4. Index Worker
   ├── Load artifact from database
   ├── Split into chunks (GitHubPRChunk)
   ├── Generate embeddings (OpenAI text-embedding-3-large)
   ├── Store vectors in Turbopuffer
   └── Index in OpenSearch for full-text search
```

### Search Query Flow

```
1. MCP Client
   │
   │ semantic_search("How do I deploy to production?")
   ▼
2. MCP Server
   ├── Authenticate request (WorkOS AuthKit)
   ├── Generate query embedding
   └── Search Turbopuffer using vector similarity
   │
   ▼
3. Turbopuffer
   └── Return top-k similar chunks with scores
   │
   ▼
4. MCP Server
   ├── Fetch full document metadata
   ├── Format results with citations
   └── Return to client
```

## Multi-Tenant Architecture

Grapevine is designed for multi-tenancy from the ground up.

### Tenant Isolation

```
┌─────────────────────────────────────────────────────────────┐
│                     Control Database                         │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    tenants table                     │    │
│  │  • id (tenant_id)                                   │    │
│  │  • workos_org_id                                    │    │
│  │  • state (pending/provisioning/provisioned/error)   │    │
│  │  • provisioned_at                                   │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           ▼                  ▼                  ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Tenant DB: abc123│ │ Tenant DB: def456│ │ Tenant DB: ghi789│
│ • documents      │ │ • documents      │ │ • documents      │
│ • artifacts      │ │ • artifacts      │ │ • artifacts      │
│ • config         │ │ • config         │ │ • config         │
└──────────────────┘ └──────────────────┘ └──────────────────┘
        │                    │                    │
        └────────────────────┼────────────────────┘
                             ▼
              ┌──────────────────────────┐
              │       Turbopuffer        │
              │  (Vector embeddings)     │
              │  • tenant-abc123-chunks  │
              │  • tenant-def456-chunks  │
              │  • tenant-ghi789-chunks  │
              └──────────────────────────┘
```

### Tenant Resolution

1. **From Webhooks**: Extract workspace ID → lookup in `tenants` table
2. **From MCP Requests**: JWT contains org_id → lookup tenant
3. **From Admin UI**: AuthKit session → WorkOS org_id → tenant

### Resource Isolation

| Resource              | Isolation Level                           |
| --------------------- | ----------------------------------------- |
| PostgreSQL Database   | Per-tenant database                       |
| Turbopuffer Namespace | Per-tenant namespace                      |
| OpenSearch Index      | Per-tenant index                          |
| AWS SSM Secrets       | Per-tenant namespace (`/{tenant_id}/...`) |
| SQS Processing        | Shared queues, tenant ID in message       |

## Database Schema

### Control Database

```sql
-- Tenant registry and provisioning state
CREATE TABLE tenants (
    id VARCHAR(255) PRIMARY KEY,           -- 16-char hex tenant ID
    workos_org_id VARCHAR(255) UNIQUE,     -- WorkOS organization ID
    state TEXT CHECK (state IN ('pending', 'provisioning', 'provisioned', 'error')),
    error_message TEXT,
    provisioned_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

### Tenant Database

```sql
-- Ingested artifacts from connectors
CREATE TABLE ingest_artifact (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity TEXT NOT NULL,                  -- 'github_pr', 'slack_message', 'notion_page', etc.
    entity_id TEXT NOT NULL,               -- External ID from source
    ingest_job_id UUID NOT NULL,
    metadata JSONB DEFAULT '{}',
    content JSONB DEFAULT '{}',
    source_updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE(entity, entity_id)
);

-- Document metadata and content for search
CREATE TABLE documents (
    id VARCHAR(255) PRIMARY KEY,
    content_hash VARCHAR(64) UNIQUE NOT NULL,
    metadata JSONB DEFAULT '{}',
    source VARCHAR(255) NOT NULL,
    content TEXT,
    source_created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    source_updated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Key-value configuration storage
CREATE TABLE config (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Plus: exclusion_rules, slack_messages, usage_records, document_permissions,
-- api_keys, webhook_subscriptions, knowledge_bases, and various feature-specific tables.
```

**Note:** Embeddings and chunks are stored in Turbopuffer (external vector database), not in PostgreSQL. All vector operations go through Turbopuffer for scalability and query performance.

## Search Architecture

### Dual Search Strategy

Grapevine uses both semantic and keyword search:

**Semantic Search (Vector Similarity):**

- Powered by Turbopuffer (hosted vector database)
- Uses OpenAI `text-embedding-3-large` (3072 dimensions)
- Optimized for fast approximate nearest neighbor search
- Best for conceptual/meaning-based queries

**Keyword Search (BM25):**

- Powered by OpenSearch
- Full-text search with relevance ranking
- Supports filters, aggregations, and facets
- Best for exact term matching

### Embedding Model

| Property   | Value                    |
| ---------- | ------------------------ |
| Model      | `text-embedding-3-large` |
| Dimensions | 3072                     |
| Max Tokens | 8191                     |
| Provider   | OpenAI                   |

### Search Query Processing

```python
# Semantic search flow
query = "How do I deploy to production?"

# 1. Generate query embedding
query_embedding = openai.embeddings.create(
    model="text-embedding-3-large",
    input=query
)

# 2. Vector similarity search via Turbopuffer
results = turbopuffer_client.query(
    namespace=tenant_namespace,
    vector=query_embedding,
    top_k=10,
    include_attributes=["title", "source", "artifact_id"]
)
```

## Connector System

Each data source has a dedicated connector in `connectors/`.

### Connector Structure

```
connectors/
└── github/
    ├── __init__.py
    ├── github_sync_service.py      # Orchestrates full sync
    ├── github_citation_resolver.py # Generates URLs for citations
    ├── github_pruner.py            # Handles deletions
    ├── extractors/
    │   ├── github_pr_extractor.py  # Extracts PR data
    │   ├── github_issue_extractor.py
    │   └── ...
    ├── transformers/
    │   ├── github_pr_transformer.py
    │   └── ...
    └── client/
        └── github_client.py        # API client wrapper
```

### Base Classes

All connectors extend these base classes:

```python
# connectors/base/document.py
class BaseDocument:
    """Standard document format for all sources."""
    id: str
    source: str
    source_id: str
    title: str
    content: str
    metadata: dict

class BaseChunk:
    """Document chunk for embedding and search."""
    document_id: str
    chunk_index: int
    content: str
    metadata: dict
```

### Adding New Connectors

See [connector-ingestion-implementation-guide.md](connector-ingestion-implementation-guide.md) for detailed instructions.

## Authentication & Security

### Authentication Providers

**WorkOS AuthKit (Primary):**

- OAuth 2.0 / OIDC authentication
- Dynamic Client Registration
- Organization-based multi-tenancy

**Internal JWT (Service-to-Service):**

- RS256 signed tokens
- Used by Slack bot, internal services
- Configurable via `INTERNAL_JWT_*` environment variables

### Security Model

```
┌─────────────────────────────────────────────────────────────┐
│                      Request Flow                            │
│                                                              │
│  Client → AuthKit OAuth → MCP Server → Tenant Database       │
│              │                │                              │
│              ▼                ▼                              │
│         Verify JWT      Resolve tenant                       │
│         Get org_id      from org_id                          │
│                               │                              │
│                               ▼                              │
│                      Query tenant's data only                │
└─────────────────────────────────────────────────────────────┘
```

### Webhook Security

Each webhook source uses signature verification:

| Source | Signature Method                    |
| ------ | ----------------------------------- |
| GitHub | HMAC-SHA256 (`X-Hub-Signature-256`) |
| Slack  | HMAC-SHA256 (`X-Slack-Signature`)   |
| Linear | HMAC-SHA256                         |
| Notion | (Notification-based, no signature)  |

Signing secrets are stored in AWS SSM Parameter Store:

```
/{tenant_id}/signing-secret/github
/{tenant_id}/signing-secret/slack
/{tenant_id}/signing-secret/linear
```

## Key Design Patterns

### Async-First

All database operations use async/await:

```python
async def get_document(document_id: str) -> Document:
    async with get_db_session() as session:
        result = await session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one()
```

### Type Safety

Strong typing throughout with Pydantic models:

```python
class DocumentMetadata(BaseModel):
    source: str
    source_id: str
    title: str
    author: str | None = None
    created_at: datetime
    updated_at: datetime
```

### Incremental Updates

Documents are updated, not replaced:

```python
# Upsert pattern
INSERT INTO documents (source, source_id, content, ...)
VALUES (...)
ON CONFLICT (source, source_id)
DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
```

### Environment Flexibility

All configuration via environment variables:

```python
# src/utils/config.py
def get_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL is required")
    return url
```

## Related Documentation

- [Self-Hosting Guide](SELF_HOSTING.md) - Deploy Grapevine yourself
- [Connector Implementation Guide](connector-ingestion-implementation-guide.md) - Add new data sources
- [Migrations Guide](migrations.md) - Database schema management
- [Contributing Guide](../CONTRIBUTING.md) - Development workflow
