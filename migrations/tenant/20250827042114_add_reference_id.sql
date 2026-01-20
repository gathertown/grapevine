-- Add reference_id column to documents table
ALTER TABLE documents
ADD COLUMN reference_id TEXT;
-- Add index on reference_id
CREATE INDEX idx_documents_reference_id ON documents(reference_id);
