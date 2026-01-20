-- Tenant DB Migration: test migration system deployment
-- Created: 2025-09-02 16:19:20

BEGIN;

-- No-op migration to test end-to-end deployment system
-- This migration verifies that:
-- 1. CI/CD properly runs migrations before deployment
-- 2. Migration tracking works correctly in production for all tenants
-- 3. The migration system handles tenant databases properly
-- 4. Steward service correctly applies migrations during provisioning

-- Simple query to verify database connectivity
SELECT 1 AS migration_test;

-- Verify documents table exists (should always be true in tenant DBs)
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'documents'
) AS documents_table_exists;

-- Verify vector extension is installed (required for embeddings)
SELECT EXISTS (
    SELECT FROM pg_extension 
    WHERE extname = 'vector'
) AS vector_extension_exists;

COMMIT;
