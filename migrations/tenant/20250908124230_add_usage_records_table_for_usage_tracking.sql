-- Tenant DB Migration: add usage_records table for usage tracking
-- Created: 2025-09-08 12:42:30

BEGIN;

-- Create usage_records table for per-tenant usage tracking
-- Stores individual usage records (requests, tokens, etc.) for billing and reporting
CREATE TABLE usage_records (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    metric_type VARCHAR(50) NOT NULL, -- 'requests', 'input_tokens', 'output_tokens', 'embedding_tokens'
    metric_value BIGINT NOT NULL,
    source_type VARCHAR(50) NOT NULL, -- 'ask_agent', 'ingest_embedding', 'search'
    source_details JSONB, -- Additional context (model, endpoint, etc.)
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast queries within tenant database
CREATE INDEX usage_records_metric_time_idx ON usage_records(metric_type, recorded_at DESC);
CREATE INDEX usage_records_source_time_idx ON usage_records(source_type, recorded_at DESC);

-- Add constraints for data integrity
ALTER TABLE usage_records ADD CONSTRAINT usage_records_metric_type_check 
    CHECK (metric_type IN ('requests', 'input_tokens', 'output_tokens', 'embedding_tokens'));

-- Note: source_type intentionally not constrained to allow for dynamic source types

ALTER TABLE usage_records ADD CONSTRAINT usage_records_metric_value_positive 
    CHECK (metric_value >= 0);

COMMIT;
