-- Drop unused authority_multiplier column and its index from chunks table
-- Drop the index first (if it exists)
DROP INDEX IF EXISTS idx_chunks_authority_multiplier;
-- Drop the authority_multiplier column
ALTER TABLE chunks DROP COLUMN IF EXISTS authority_multiplier;
