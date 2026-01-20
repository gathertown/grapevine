-- Control DB Migration: test migration system deployment
-- Created: 2025-09-02 16:18:42

BEGIN;

-- No-op migration to test end-to-end deployment system
-- This migration verifies that:
-- 1. CI/CD properly runs migrations before deployment
-- 2. Migration tracking works correctly in production
-- 3. The migration system handles control database properly

-- Simple query to verify database connectivity
SELECT 1 AS migration_test;

-- Verify tenants table exists (should always be true)
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'tenants'
) AS tenants_table_exists;

COMMIT;
