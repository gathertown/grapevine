-- Tenant DB Migration: add last_seen_backfill_id to track stale entities
-- Created: 2025-11-16 20:09:58
--
-- This migration adds last_seen_backfill_id columns to ingest_artifact and documents tables
-- to enable efficient stale entity detection during full syncs at scale.
--
-- The system uses these columns to:
-- 1. Mark entities/documents with the current backfill_id when they are seen
-- 2. Query for entities/documents NOT marked with the current backfill_id (stale)
-- 3. Delete stale entities across all data stores (PostgreSQL, OpenSearch, Turbopuffer)

BEGIN;

-- Add the column to track which backfill last saw this artifact
ALTER TABLE public.ingest_artifact
ADD COLUMN last_seen_backfill_id VARCHAR(255);

-- Add the column to track which backfill last saw this document
ALTER TABLE public.documents
ADD COLUMN last_seen_backfill_id VARCHAR(255);

-- Create index on last_seen_backfill_id for efficient queries during pruning (artifacts)
CREATE INDEX idx_ingest_artifact_last_seen_backfill 
ON public.ingest_artifact(last_seen_backfill_id);

-- Create composite index on entity + last_seen_backfill_id for efficient source-specific queries (artifacts)
CREATE INDEX idx_ingest_artifact_entity_last_seen 
ON public.ingest_artifact(entity, last_seen_backfill_id);

-- Create index on last_seen_backfill_id for efficient queries during pruning (documents)
CREATE INDEX idx_documents_last_seen_backfill 
ON public.documents(last_seen_backfill_id);

-- Create composite index on source + last_seen_backfill_id for efficient source-specific queries (documents)
CREATE INDEX idx_documents_source_last_seen 
ON public.documents(source, last_seen_backfill_id);

-- Add helpful comments
COMMENT ON COLUMN public.ingest_artifact.last_seen_backfill_id IS 'Backfill ID that last saw/updated this artifact. Used for efficient stale entity detection during full syncs.';
COMMENT ON COLUMN public.documents.last_seen_backfill_id IS 'Backfill ID that last saw/updated this document. Used for efficient stale entity detection during full syncs.';

COMMIT;

