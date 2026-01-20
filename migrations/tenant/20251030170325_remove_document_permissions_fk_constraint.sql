-- Remove FK constraint between document_permissions and documents
-- This allows writing permissions before documents are written

-- Drop the foreign key constraint if it exists
ALTER TABLE IF EXISTS document_permissions
DROP CONSTRAINT IF EXISTS document_permissions_document_id_fkey;

-- Add index on document_id to maintain query performance
CREATE INDEX IF NOT EXISTS idx_document_permissions_document_id
ON document_permissions(document_id);
