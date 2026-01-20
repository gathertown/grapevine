-- Migration: update_ambient_source_config_for_pattern_based_routing
-- Created: 2025-11-26 15:26:24

-- Drop the old UNIQUE constraint on source_type (we'll have multiple rows per source now)
ALTER TABLE ambient_source_config DROP CONSTRAINT IF EXISTS ambient_source_config_source_type_key;

-- Add pattern column for matching (meeting title or repo name)
ALTER TABLE ambient_source_config ADD COLUMN IF NOT EXISTS pattern VARCHAR(512);

-- Add priority column for ordering when multiple patterns match
ALTER TABLE ambient_source_config ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 0;

-- Add linear_team_name for display purposes
ALTER TABLE ambient_source_config ADD COLUMN IF NOT EXISTS linear_team_name VARCHAR(255);

-- Update indexes - remove old unique index, add new compound index
DROP INDEX IF EXISTS idx_ambient_source_config_source_type;

-- Index for looking up configs by source type (ordered by priority)
CREATE INDEX IF NOT EXISTS idx_ambient_source_config_lookup 
    ON ambient_source_config(source_type, priority DESC) WHERE enabled = true;

-- Index for pattern matching
CREATE INDEX IF NOT EXISTS idx_ambient_source_config_pattern 
    ON ambient_source_config(source_type, pattern) WHERE enabled = true AND pattern IS NOT NULL;

-- Add comments for clarity
COMMENT ON COLUMN ambient_source_config.pattern IS 'Pattern to match against (meeting title for gather, repo name for github). NULL means match all.';
COMMENT ON COLUMN ambient_source_config.priority IS 'Higher priority patterns are matched first. Use for specific matches before wildcards.';
COMMENT ON COLUMN ambient_source_config.linear_team_name IS 'Display name of Linear team (for UI)';
