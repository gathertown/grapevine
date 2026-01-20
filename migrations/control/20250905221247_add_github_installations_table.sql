-- Control DB Migration: add github_installations table
-- Created: 2025-09-05 22:12:47

BEGIN;

-- Create github_installations table
CREATE TABLE IF NOT EXISTS public.github_installations (
  installation_id INTEGER PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL UNIQUE,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

  -- Foreign key constraint to tenants table
  CONSTRAINT fk_github_installations_tenant_id
    FOREIGN KEY (tenant_id) REFERENCES public.tenants(id)
    ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS github_installations_tenant_id_idx ON public.github_installations(tenant_id);

-- Trigger for automatic updated_at timestamp
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'update_github_installations_updated_at'
  ) THEN
    CREATE TRIGGER update_github_installations_updated_at
      BEFORE UPDATE ON public.github_installations
      FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END$$;

COMMIT;
