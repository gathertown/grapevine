-- Set default value for deleted_at column
BEGIN;

-- Set default to NULL for deleted_at column (NULL means tenant is active)
ALTER TABLE public.tenants ALTER COLUMN deleted_at SET DEFAULT NULL;

COMMIT;
