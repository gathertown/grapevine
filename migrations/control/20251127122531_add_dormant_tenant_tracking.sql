-- Control DB Migration: Add dormant tenant tracking columns
-- Created: 2025-11-27
-- Description: Add columns to track dormant tenants for cleanup purposes

BEGIN;

-- Add is_dormant flag to mark tenants that have never set up anything
ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS is_dormant BOOLEAN DEFAULT FALSE;

-- Add timestamp for when the tenant was first detected as dormant
-- This is used to calculate grace period before deletion
ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS dormant_detected_at TIMESTAMP WITH TIME ZONE;

-- Create partial index for efficient queries on dormant tenants
CREATE INDEX IF NOT EXISTS idx_tenants_dormant ON public.tenants(is_dormant) WHERE is_dormant = TRUE;

-- Create index for querying by dormant_detected_at for grace period calculations
CREATE INDEX IF NOT EXISTS idx_tenants_dormant_detected_at ON public.tenants(dormant_detected_at) WHERE dormant_detected_at IS NOT NULL;

COMMIT;

