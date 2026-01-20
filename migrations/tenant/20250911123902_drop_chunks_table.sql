-- Tenant DB Migration: drop chunks table
-- Created: 2025-09-11 12:39:02

BEGIN;

-- Drop legacy `chunks` table as part of AIVP-488. Chunks have been migrated to Turbopuffer.
-- Dropping this table should also clean up the indexes on it.
DROP TABLE IF EXISTS public.chunks;

COMMIT;
