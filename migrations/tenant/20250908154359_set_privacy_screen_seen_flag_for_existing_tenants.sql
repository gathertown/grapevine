-- Tenant DB Migration: set privacy screen seen flag for existing tenants
-- Created: 2025-09-08 15:43:59
--
-- This migration sets HAS_SEEN_DATA_PRIVACY_SCREEN=true for all existing tenants
-- so they don't get blocked by the new privacy consent screen that was added.
-- New tenants will still see the privacy screen on first login.

BEGIN;

-- Insert or update the HAS_SEEN_DATA_PRIVACY_SCREEN config value for existing tenants
-- Use ON CONFLICT to handle the case where the key already exists
INSERT INTO config (key, value, created_at, updated_at)
VALUES ('HAS_SEEN_DATA_PRIVACY_SCREEN', 'true', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT (key) 
DO UPDATE SET 
    value = 'true',
    updated_at = CURRENT_TIMESTAMP;

COMMIT;
