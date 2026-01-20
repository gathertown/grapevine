-- Control DB Migration: add trello_installations table
-- Created: 2025-11-11
--
-- This table tracks which Trello member (authenticated user) is connected to which tenant.
-- Used for GDPR compliance to efficiently target personal data cleanup to specific tenants.

BEGIN;

-- Create trello_installations table
CREATE TABLE IF NOT EXISTS public.trello_installations (
  member_id VARCHAR(255) PRIMARY KEY,            -- Trello member ID (authenticated user)
  tenant_id VARCHAR(255) NOT NULL,               -- Our internal tenant ID
  member_username VARCHAR(255),                  -- Trello username for reference
  webhook_id VARCHAR(255),                       -- Associated webhook ID
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

  -- Foreign key constraint to tenants table
  CONSTRAINT fk_trello_installations_tenant_id
    FOREIGN KEY (tenant_id) REFERENCES public.tenants(id)
    ON DELETE CASCADE
);

-- Index for looking up by tenant_id (less common but useful for debugging)
CREATE INDEX IF NOT EXISTS trello_installations_tenant_id_idx ON public.trello_installations(tenant_id);

-- Trigger for automatic updated_at timestamp
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'update_trello_installations_updated_at'
  ) THEN
    CREATE TRIGGER update_trello_installations_updated_at
      BEFORE UPDATE ON public.trello_installations
      FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END$$;

COMMIT;
