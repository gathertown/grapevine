-- Add API keys table for REST API authentication
-- API keys are stored in AWS SSM, this table only stores metadata
BEGIN;

CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    prefix VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITH TIME ZONE,
    created_by VARCHAR(255)
);

-- Index for listing keys by creation date
CREATE INDEX IF NOT EXISTS idx_api_keys_created_at ON api_keys(created_at DESC);

-- Unique index for fast O(1) verification lookups by prefix
CREATE UNIQUE INDEX IF NOT EXISTS idx_api_keys_prefix ON api_keys(prefix);

COMMIT;
