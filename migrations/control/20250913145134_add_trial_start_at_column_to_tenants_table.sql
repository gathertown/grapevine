-- Control DB Migration: add trial_start_at column to tenants table
-- Created: 2025-09-13 14:51:34

BEGIN;

-- Add trial_start_at column to tenants table, defaulting to created_at value
ALTER TABLE public.tenants ADD COLUMN trial_start_at TIMESTAMP WITH TIME ZONE;

-- Update existing rows to set trial_start_at to created_at
UPDATE public.tenants SET trial_start_at = created_at WHERE trial_start_at IS NULL;

-- Set the default for future inserts
ALTER TABLE public.tenants ALTER COLUMN trial_start_at SET DEFAULT CURRENT_TIMESTAMP;

-- Make the column NOT NULL after setting values for existing rows
ALTER TABLE public.tenants ALTER COLUMN trial_start_at SET NOT NULL;

COMMIT;
