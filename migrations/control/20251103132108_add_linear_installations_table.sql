-- Control DB Migration: add linear_installations table
-- Created: 2025-11-03 13:21:08

BEGIN;

-- Create linear_installations table
CREATE TABLE IF NOT EXISTS public.linear_installations (
  organization_id VARCHAR(255) PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL UNIQUE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

  -- Foreign key constraint to tenants table
  CONSTRAINT fk_linear_installations_tenant_id
    FOREIGN KEY (tenant_id) REFERENCES public.tenants(id)
    ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS linear_installations_tenant_id_idx ON public.linear_installations(tenant_id);

-- Trigger for automatic updated_at timestamp
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'update_linear_installations_updated_at'
  ) THEN
    CREATE TRIGGER update_linear_installations_updated_at
      BEFORE UPDATE ON public.linear_installations
      FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END$$;

COMMIT;
