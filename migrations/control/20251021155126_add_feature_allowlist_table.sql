-- Control DB: create feature_allowlist table
BEGIN;

-- Create feature_allowlist table to store per-tenant feature flags
CREATE TABLE IF NOT EXISTS public.feature_allowlist (
  tenant_id character varying(255) NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  feature_key character varying(255) NOT NULL,
  created_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp with time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (tenant_id, feature_key)
);

-- Index for querying by tenant
CREATE INDEX IF NOT EXISTS feature_allowlist_tenant_id_idx ON public.feature_allowlist(tenant_id);

-- Trigger for automatic updated_at timestamp
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'update_feature_allowlist_updated_at'
  ) THEN
    CREATE TRIGGER update_feature_allowlist_updated_at
      BEFORE UPDATE ON public.feature_allowlist
      FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END$$;



COMMIT;
