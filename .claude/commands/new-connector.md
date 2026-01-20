---
description: Initialize a new connector with wizard to gather API docs, auth info, and logo
allowed-tools: Read, Write, Bash, WebFetch, AskUserQuestion, Task, Glob, Grep
argument-hint: [connector-name]
---

# New Connector Wizard

You are initializing a new connector.

## Step 1: Gather Information

Gather information from the user by asking ONE question at a time. Wait for the user's response before asking the next question.

**If no connector name was provided as argument ($1 is empty)**, start by asking:
> What is the name of the connector? (e.g., "hubspot", "canva", "asana")

After receiving the connector name, continue with the next questions.

**If connector name was provided ($1 is not empty)**, the connector name is **$1**, skip to the next question.

Then ask each of these questions ONE AT A TIME, waiting for the response before proceeding:

1. > What is the URL to the API documentation?

2. > What is the URL to the authentication documentation?

3. > What is the URL to download the connector logo? (PNG or SVG preferred)

**IMPORTANT**: Ask only ONE question per message. Wait for the user's answer before asking the next question. Do NOT ask all questions at once.

## Step 2: Download Logo

After getting the logo URL:
1. Use WebFetch or Bash with curl to download the logo
2. Save it to `js-services/admin-frontend/src/assets/integration_logos/{connector_name}.png` (or .svg based on URL)
3. If the download fails, ask the user for an alternative URL or local file path

## Step 3: Create Checklist File

Create a checklist file at `docs/connectors/{connector_name}-checklist.md` with:

```markdown
# {Connector Name} Connector Implementation Checklist

## Documentation Links
- API Docs: [URL from wizard]
- Auth Docs: [URL from wizard]

## Pre-Implementation Research
- [ ] Review API documentation
- [ ] Identify available endpoints and rate limits
- [ ] Determine authentication method from auth docs (OAuth vs API Key)
- [ ] Check for webhook support
- [ ] Check for incremental sync support (updated_after, modified_since params)
- [ ] Verify citation URL patterns from the LIVE APP

## Implementation Checklist

### Database & Configuration
- [ ] Add `{connector}` to Python `ConnectorType` enum in `src/database/connector_installations.py`
- [ ] Add `{Connector}` to TypeScript `ConnectorType` enum in `js-services/admin-backend/src/types/connector.ts`
- [ ] Create database migration for `valid_connector_type` constraint
- [ ] Register config keys in `js-services/admin-backend/src/config/configKeys.ts`

### Feature Flags
- [ ] Add `CONNECTOR_{CONNECTOR}` to `js-services/admin-backend/src/features/feature-definitions.ts`
- [ ] Add `connector:{connector}` to `js-services/admin-frontend/src/api/features.ts`

### OAuth/Auth Backend
- [ ] Create `js-services/admin-backend/src/connectors/{connector}/` directory
- [ ] Implement OAuth routes or API key handling
- [ ] Store tokens in SSM with tenant-specific paths
- [ ] Create config keys file (`{connector}-config.ts`)

### Frontend
- [ ] Import logo in `js-services/admin-frontend/src/assets/icons/index.tsx`
- [ ] Create integration page component
- [ ] Add to `IntegrationsContext.tsx`
- [ ] Add route to `IntegrationCard.tsx` routeMap

### Python Client
- [ ] Create `connectors/{connector}/client/` directory
- [ ] Implement client with rate limiting and pagination
- [ ] Add token refresh if OAuth with short-lived tokens

### Artifacts & Documents
- [ ] Create `connectors/{connector}/{connector}_models.py` (artifacts, backfill configs)
- [ ] Create `connectors/{connector}/{connector}_documents.py` (documents, chunks)
- [ ] Add to `ArtifactEntity` enum in `connectors/base/base_ingest_artifact.py`
- [ ] Add to `DocumentSource` enum in `connectors/base/document_source.py`
- [ ] Add to `ExternalSource` in `connectors/base/external_source.py`

### Transformer
- [ ] Create `connectors/{connector}/{connector}_transformer.py`
- [ ] Register in `src/ingest/services/index_job_handler.py`

### Extractors
- [ ] Create `connectors/{connector}/extractors/` directory
- [ ] Implement root, batch, and incremental extractors
- [ ] Register in `src/jobs/ingest_job_worker.py`
- [ ] Register in `scripts/backfill_cli.py`

### Sync Service
- [ ] Create `connectors/{connector}/{connector}_sync_service.py`
- [ ] Implement cursor persistence

### Citation Resolver
- [ ] Create `connectors/{connector}/{connector}_citation_resolver.py`
- [ ] VERIFY URL patterns from LIVE APP
- [ ] Register in `src/mcp/api/citation_resolver.py`

### Search Integration
- [ ] Add `DocumentSource.{CONNECTOR}_*` case to `src/mcp/tools/keyword_search.py`
- [ ] Ensure metadata field names match document metadata exactly

### Registrations
- [ ] Add to `connector-store.ts` (allConnectors array)
- [ ] Add source mapping in `stats.ts` (getConnectorKeyFromType)

### Cron Jobs (if using incremental sync)
- [ ] Create `src/cron/jobs/{connector}_incremental_sync.py`
- [ ] Use deduplication ID pattern

### Tests
- [ ] `tests/connectors/{connector}/test_{connector}_artifacts.py`
- [ ] `tests/connectors/{connector}/test_{connector}_documents.py`
- [ ] `tests/connectors/{connector}/test_{connector}_sync_service.py`

## Post-Implementation Verification
- [ ] Run `uv run ruff check && uv run mypy`
- [ ] Run `yarn lint && yarn type-check && yarn build`
- [ ] Test OAuth/API Key flow manually
- [ ] Verify logo displays correctly
- [ ] Test full backfill
- [ ] Test incremental sync
- [ ] Verify citation URLs work
```

## Step 4: Update Icon Index

Add the logo import to `js-services/admin-frontend/src/assets/icons/index.tsx`:
- Add import statement for the logo file
- Add export for the icon component following existing patterns

## Step 5: Launch Connector Architect

After gathering information and creating the checklist, invoke the connector-architect agent using the Task tool with:

```
Please implement the {connector_name} connector.

Documentation:
- API Docs: [URL from wizard]
- Auth Docs: [URL from wizard]

The logo has been downloaded to js-services/admin-frontend/src/assets/integration_logos/{connector_name}.png
The implementation checklist is at docs/connectors/{connector_name}-checklist.md

Please:
1. First, research the auth docs to determine if this uses OAuth or API Key authentication
2. Follow the checklist and implement all required components
3. Mark items complete as you go
```

## Important Notes

- If connector name contains hyphens, convert to underscores for Python (e.g., `my-connector` -> `my_connector`)
- Logo should be PNG format preferably, with dimensions around 48x48 or larger
- The agent will determine OAuth vs API Key from the auth documentation
- Always verify OAuth response structures by reading the actual API documentation
