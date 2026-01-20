-- Control DB Migration: add slack_installations table
-- Created: 2025-11-06

BEGIN;

-- Create slack_installations table
CREATE TABLE IF NOT EXISTS public.slack_installations (
  team_id VARCHAR(255) PRIMARY KEY,              -- Slack's workspace team ID
  tenant_id VARCHAR(255) NOT NULL UNIQUE,        -- Our internal tenant ID
  bot_user_id VARCHAR(255),                      -- Bot user ID for the workspace
  installer_user_id VARCHAR(255),                -- User who installed the app
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,

  -- Foreign key constraint to tenants table
  CONSTRAINT fk_slack_installations_tenant_id
    FOREIGN KEY (tenant_id) REFERENCES public.tenants(id)
    ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS slack_installations_tenant_id_idx ON public.slack_installations(tenant_id);

-- Trigger for automatic updated_at timestamp
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'update_slack_installations_updated_at'
  ) THEN
    CREATE TRIGGER update_slack_installations_updated_at
      BEFORE UPDATE ON public.slack_installations
      FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END$$;

COMMIT;
