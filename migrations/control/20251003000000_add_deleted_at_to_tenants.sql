-- Add deleted_at column to tenants table for soft deletion
BEGIN;

-- Add deleted_at column to track when a tenant was deleted
ALTER TABLE public.tenants ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE NULL;

-- Add index for efficient filtering of deleted tenants
CREATE INDEX IF NOT EXISTS tenants_deleted_at_idx ON public.tenants(deleted_at);

-- Add comment to document the column's purpose
COMMENT ON COLUMN public.tenants.deleted_at IS 'Timestamp when the tenant was marked as deleted. NULL means tenant is active.';

COMMIT;
