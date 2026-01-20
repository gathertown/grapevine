-- Control DB Migration: add hubspot_installations table
-- Created: 2025-09-25 07:10:14

BEGIN;

-- Create hubspot_installations table
CREATE TABLE IF NOT EXISTS public.hubspot_installations (
portal_id BIGINT PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL UNIQUE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

  -- Foreign key constraint to tenants table
  CONSTRAINT fk_hubspot_installations_tenant_id
    FOREIGN KEY (tenant_id) REFERENCES public.tenants(id)
    ON DELETE CASCADE
);
