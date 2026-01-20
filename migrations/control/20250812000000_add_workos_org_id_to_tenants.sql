-- Add workos_org_id column to tenants table for external ID mapping
ALTER TABLE public.tenants 
  ADD COLUMN IF NOT EXISTS workos_org_id VARCHAR(255) UNIQUE;

CREATE INDEX IF NOT EXISTS tenants_workos_org_id_idx ON public.tenants(workos_org_id);