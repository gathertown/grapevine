-- Control DB Migration: Add 'deactivating' state to tenants table
-- Created: 2025-12-08
--
-- This migration adds a new 'deactivating' state to the tenants table.
-- Tenants in this state are in the process of being deleted/pruned and
-- should be excluded from migration runs.

BEGIN;

-- Update the CHECK constraint to include 'deactivating' state
ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_state_check;
ALTER TABLE tenants ADD CONSTRAINT tenants_state_check
  CHECK (state IN ('pending', 'provisioning', 'provisioned', 'error', 'deactivating'));

COMMIT;
