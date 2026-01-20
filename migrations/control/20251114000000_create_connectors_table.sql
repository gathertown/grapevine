-- Create connector_status enum
CREATE TYPE connector_status AS ENUM (
    'pending',      -- Incomplete setup or awaiting configuration
    'active',       -- Connector healthy and syncing
    'error',        -- Runtime error (auth failures, API errors, rate limits, etc.)
    'disconnected'  -- Removed but keeping history
);

-- Create connectors table
CREATE TABLE connectors (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    type VARCHAR(50) NOT NULL,  -- 'slack', 'github', 'linear', etc.
    external_id VARCHAR(255) NOT NULL,  -- installation_id, portal_id, org_id, etc.
    external_metadata JSONB,  -- Connector-specific fields

    -- Health & Status
    status connector_status NOT NULL DEFAULT 'pending',

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT unique_tenant_type_external UNIQUE (tenant_id, type, external_id),
    CONSTRAINT valid_connector_type CHECK (type IN (
        'slack', 'github', 'linear', 'notion', 'google_drive', 'google_email',
        'hubspot', 'salesforce', 'jira', 'confluence', 'gong', 'gather',
        'trello', 'zendesk', 'asana'
    ))
);

-- Indexes for common queries
CREATE INDEX idx_connectors_tenant_id ON connectors(tenant_id);
CREATE INDEX idx_connectors_status ON connectors(status) WHERE status != 'disconnected';

-- Trigger to update updated_at timestamp
CREATE TRIGGER update_connectors_updated_at
    BEFORE UPDATE ON connectors
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
