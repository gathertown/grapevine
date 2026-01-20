-- Control DB Migration: add has_salesforce_connected
-- Created: 2025-09-17 22:17:01

BEGIN;

-- Add has_salesforce_connected column to track Salesforce connection status
ALTER TABLE public.tenants
  ADD COLUMN IF NOT EXISTS has_salesforce_connected BOOLEAN NOT NULL DEFAULT false;

-- Create index for efficient queries on Salesforce connection status
CREATE INDEX IF NOT EXISTS tenants_has_salesforce_connected_idx
  ON public.tenants(has_salesforce_connected);

COMMIT;
