-- Drop the unused GIN index on chunks.metadata
DROP INDEX IF EXISTS idx_chunks_metadata;
