-- Drop indices first
DROP INDEX IF EXISTS idx_documents_num_references;
DROP INDEX IF EXISTS idx_documents_num_references_updated_at;
-- Drop columns
ALTER TABLE documents DROP COLUMN IF EXISTS num_references;
ALTER TABLE documents DROP COLUMN IF EXISTS num_references_updated_at;
