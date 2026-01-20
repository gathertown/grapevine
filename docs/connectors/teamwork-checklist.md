# Teamwork Connector Implementation Checklist

## Documentation Links
- API Docs: https://apidocs.teamwork.com/docs/teamwork
- Auth Docs: https://apidocs.teamwork.com/guides/teamwork/authentication

## Pre-Implementation Research
- [ ] Review API documentation
- [ ] Identify available endpoints and rate limits
- [ ] Determine authentication method from auth docs (OAuth vs API Key)
- [ ] Check for webhook support
- [ ] Check for incremental sync support (updated_after, modified_since params)
- [ ] Verify citation URL patterns from the LIVE APP

## Implementation Checklist

### Database & Configuration
- [ ] Add `teamwork` to Python `ConnectorType` enum in `src/database/connector_installations.py`
- [ ] Add `Teamwork` to TypeScript `ConnectorType` enum in `js-services/admin-backend/src/types/connector.ts`
- [ ] Create database migration for `valid_connector_type` constraint
- [ ] Register config keys in `js-services/admin-backend/src/config/configKeys.ts`

### Feature Flags
- [ ] Add `CONNECTOR_TEAMWORK` to `js-services/admin-backend/src/features/feature-definitions.ts`
- [ ] Add `connector:teamwork` to `js-services/admin-frontend/src/api/features.ts`

### OAuth/Auth Backend
- [ ] Create `js-services/admin-backend/src/connectors/teamwork/` directory
- [ ] Implement OAuth routes or API key handling
- [ ] Store tokens in SSM with tenant-specific paths
- [ ] Create config keys file (`teamwork-config.ts`)

### Frontend
- [ ] Import logo in `js-services/admin-frontend/src/assets/icons/index.tsx`
- [ ] Create integration page component
- [ ] Add to `IntegrationsContext.tsx`
- [ ] Add route to `IntegrationCard.tsx` routeMap

### Python Client
- [ ] Create `connectors/teamwork/client/` directory
- [ ] Implement client with rate limiting and pagination
- [ ] Add token refresh if OAuth with short-lived tokens

### Artifacts & Documents
- [ ] Create `connectors/teamwork/teamwork_models.py` (artifacts, backfill configs)
- [ ] Create `connectors/teamwork/teamwork_documents.py` (documents, chunks)
- [ ] Add to `ArtifactEntity` enum in `connectors/base/base_ingest_artifact.py`
- [ ] Add to `DocumentSource` enum in `connectors/base/document_source.py`
- [ ] Add to `ExternalSource` in `connectors/base/external_source.py`

### Transformer
- [ ] Create `connectors/teamwork/teamwork_transformer.py`
- [ ] Register in `src/ingest/services/index_job_handler.py`

### Extractors
- [ ] Create `connectors/teamwork/extractors/` directory
- [ ] Implement root, batch, and incremental extractors
- [ ] Register in `src/jobs/ingest_job_worker.py`
- [ ] Register in `scripts/backfill_cli.py`

### Sync Service
- [ ] Create `connectors/teamwork/teamwork_sync_service.py`
- [ ] Implement cursor persistence

### Citation Resolver
- [ ] Create `connectors/teamwork/teamwork_citation_resolver.py`
- [ ] VERIFY URL patterns from LIVE APP
- [ ] Register in `src/mcp/api/citation_resolver.py`

### Search Integration
- [ ] Add `DocumentSource.TEAMWORK_*` case to `src/mcp/tools/keyword_search.py`
- [ ] Ensure metadata field names match document metadata exactly

### Registrations
- [ ] Add to `connector-store.ts` (allConnectors array)
- [ ] Add source mapping in `stats.ts` (getConnectorKeyFromType)

### Cron Jobs (if using incremental sync)
- [ ] Create `src/cron/jobs/teamwork_incremental_sync.py`
- [ ] Use deduplication ID pattern

### Tests
- [ ] `tests/connectors/teamwork/test_teamwork_artifacts.py`
- [ ] `tests/connectors/teamwork/test_teamwork_documents.py`
- [ ] `tests/connectors/teamwork/test_teamwork_sync_service.py`

## Post-Implementation Verification
- [ ] Run `uv run ruff check && uv run mypy`
- [ ] Run `yarn lint && yarn type-check && yarn build`
- [ ] Test OAuth/API Key flow manually
- [ ] Verify logo displays correctly
- [ ] Test full backfill
- [ ] Test incremental sync
- [ ] Verify citation URLs work
