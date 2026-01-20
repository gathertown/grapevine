-- Migration: add_ambient_document_state_and_source_config_tables
-- Created: 2025-11-25 17:11:59

-- Table for tracking ambient document processing state (meetings, GitHub PRs)
CREATE TABLE IF NOT EXISTS ambient_document_state (
    document_id VARCHAR(512) PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'queued',
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Index for querying by source and status
CREATE INDEX IF NOT EXISTS idx_ambient_document_state_source_status 
    ON ambient_document_state(source, status);

-- Index for cleanup queries
CREATE INDEX IF NOT EXISTS idx_ambient_document_state_processed_at 
    ON ambient_document_state(processed_at);

-- Table for configuring Linear team resolution per source type
CREATE TABLE IF NOT EXISTS ambient_source_config (
    id SERIAL PRIMARY KEY,
    source_type VARCHAR(50) NOT NULL,
    linear_team_id VARCHAR(255) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(source_type)
);

-- Index for looking up config by source type
CREATE INDEX IF NOT EXISTS idx_ambient_source_config_source_type 
    ON ambient_source_config(source_type) WHERE enabled = true;

-- Add updated_at trigger for ambient_document_state
CREATE OR REPLACE FUNCTION update_ambient_document_state_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ambient_document_state_updated_at
    BEFORE UPDATE ON ambient_document_state
    FOR EACH ROW
    EXECUTE FUNCTION update_ambient_document_state_updated_at();

-- Add updated_at trigger for ambient_source_config
CREATE OR REPLACE FUNCTION update_ambient_source_config_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER ambient_source_config_updated_at
    BEFORE UPDATE ON ambient_source_config
    FOR EACH ROW
    EXECUTE FUNCTION update_ambient_source_config_updated_at();
