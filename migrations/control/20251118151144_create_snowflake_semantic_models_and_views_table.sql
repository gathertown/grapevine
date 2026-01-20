-- Control DB Migration: create snowflake semantic models and views table
-- Created: 2025-11-18 15:11:44
--
-- This migration creates a unified table for both Snowflake semantic models and views.
-- Semantic models are YAML files stored in Snowflake stages (identified by stage_path).
-- Semantic views are database objects (identified by database_name, schema_name, name).

BEGIN;

-- Drop existing table if it exists (for clean slate)
DROP TABLE IF EXISTS snowflake_semantic_models CASCADE;

-- Create the unified table for both semantic models and views
CREATE TABLE snowflake_semantic_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(255) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type VARCHAR(50) NOT NULL DEFAULT 'model' CHECK (type IN ('model', 'view')),

    -- Fields for semantic models (stage-based YAML files)
    stage_path TEXT,

    -- Fields for semantic views (database objects)
    database_name VARCHAR(255),
    schema_name VARCHAR(255),

    -- Common fields
    description TEXT,
    warehouse TEXT,
    state VARCHAR(50) NOT NULL DEFAULT 'enabled' CHECK (state IN ('enabled', 'disabled', 'deleted', 'error')),
    status_description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Create partial unique index for semantic models (stage-based)
-- Ensures unique (tenant_id, stage_path) for models
CREATE UNIQUE INDEX idx_snowflake_semantic_models_model_unique
ON snowflake_semantic_models (tenant_id, stage_path)
WHERE type = 'model' AND stage_path IS NOT NULL;

-- Create partial unique index for semantic views (database objects)
-- Ensures unique (tenant_id, database_name, schema_name, name) for views
CREATE UNIQUE INDEX idx_snowflake_semantic_models_view_unique
ON snowflake_semantic_models (tenant_id, database_name, schema_name, name)
WHERE type = 'view' AND database_name IS NOT NULL AND schema_name IS NOT NULL;

-- Index for listing semantic models/views by tenant with creation order
CREATE INDEX idx_snowflake_semantic_models_tenant_created
ON snowflake_semantic_models (tenant_id, created_at DESC);

-- Index for filtering by type
CREATE INDEX idx_snowflake_semantic_models_type
ON snowflake_semantic_models (type);

-- Index for filtering by state
CREATE INDEX idx_snowflake_semantic_models_state
ON snowflake_semantic_models (state);

-- Check constraint to ensure models have stage_path
ALTER TABLE snowflake_semantic_models
ADD CONSTRAINT snowflake_semantic_models_model_requires_stage_path
CHECK (type != 'model' OR stage_path IS NOT NULL);

-- Check constraint to ensure views have database_name and schema_name
ALTER TABLE snowflake_semantic_models
ADD CONSTRAINT snowflake_semantic_models_view_requires_db_schema
CHECK (type != 'view' OR (database_name IS NOT NULL AND schema_name IS NOT NULL));

-- Trigger for automatic updated_at timestamp
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'update_snowflake_semantic_models_updated_at'
  ) THEN
    CREATE TRIGGER update_snowflake_semantic_models_updated_at
      BEFORE UPDATE ON snowflake_semantic_models
      FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END $$;

COMMIT;
