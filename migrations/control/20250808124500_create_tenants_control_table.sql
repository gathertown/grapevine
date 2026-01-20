-- Steward DB: create control tenants table
BEGIN;

-- Ensure the generic updated_at trigger function exists
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Create tenants control table
CREATE TABLE IF NOT EXISTS public.tenants (
  id character varying(255) PRIMARY KEY,
  state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','provisioning','provisioned','error')),
  error_message text NULL,
  provisioned_at timestamp with time zone NULL,
  created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS tenants_state_idx ON tenants(state);

-- Trigger for automatic updated_at timestamp
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'update_tenants_updated_at'
  ) THEN
    CREATE TRIGGER update_tenants_updated_at
      BEFORE UPDATE ON public.tenants
      FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END$$;

COMMIT;
