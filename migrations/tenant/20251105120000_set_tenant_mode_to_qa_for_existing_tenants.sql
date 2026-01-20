-- Tenant DB Migration: set tenant mode to qa for existing tenants
-- Created: 2025-11-05 12:00:00
--
-- This migration sets TENANT_MODE='qa' for all existing tenants.
-- This is done as part of introducing the tenant mode tracking feature.
-- Existing tenants should default to 'qa', while new tenants will default to 'dev_platform'.

BEGIN;

-- Insert or update the TENANT_MODE config value to 'qa' for existing tenants
-- Use ON CONFLICT to handle the case where the key already exists
INSERT INTO config (key, value, created_at, updated_at)
VALUES ('TENANT_MODE', 'qa', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (key)
DO UPDATE SET
    value = 'qa',
    updated_at = CURRENT_TIMESTAMP;

COMMIT;
