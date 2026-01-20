-- Drop priority column from ambient_source_config table
-- Reason: Multiple patterns can now match and route to all matching teams

ALTER TABLE ambient_source_config DROP COLUMN IF EXISTS priority;
