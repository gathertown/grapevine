-- Control DB Migration: drop snowflake_semantic_models table
-- Created: 2025-11-19 15:21:24
--
-- This migration drops the snowflake_semantic_models table from the control database.
-- The table is being moved to tenant databases for better data isolation and
-- architectural consistency with other tenant-specific operational data.

BEGIN;

-- Drop the table (CASCADE will drop dependent objects like indexes)
DROP TABLE IF EXISTS snowflake_semantic_models CASCADE;

COMMIT;
