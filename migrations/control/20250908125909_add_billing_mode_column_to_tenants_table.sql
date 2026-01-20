-- Control DB Migration: add billing_mode column to tenants table
-- Created: 2025-09-08 12:59:09

BEGIN;

-- Add billing_mode column to tenants table
ALTER TABLE public.tenants ADD COLUMN billing_mode VARCHAR(50) DEFAULT 'grapevine_managed'
    CHECK (billing_mode IN ('grapevine_managed', 'gather_managed'));

-- Add index for billing_mode queries
CREATE INDEX IF NOT EXISTS tenants_billing_mode_idx ON public.tenants(billing_mode);

COMMIT;
