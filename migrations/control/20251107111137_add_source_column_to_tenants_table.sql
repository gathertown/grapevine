-- Control DB Migration: add source column to tenants table
-- Created: 2025-11-07 11:11:37

BEGIN;

-- Add source column to tenants table
-- This column tracks where the tenant originated from (landing page or docs)
ALTER TABLE tenants ADD COLUMN source TEXT CHECK (source IN ('landing_page', 'docs'));

COMMIT;
