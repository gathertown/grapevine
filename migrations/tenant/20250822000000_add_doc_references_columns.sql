-- Add reference tracking columns to documents table
ALTER TABLE documents
ADD COLUMN referrers jsonb DEFAULT '{}',
  ADD COLUMN referenced_docs jsonb DEFAULT '{}',
  ADD COLUMN referrer_score real DEFAULT 0;
-- Create indexes for performance
CREATE INDEX idx_documents_referrers ON documents USING gin (referrers);
CREATE INDEX idx_documents_references ON documents USING gin (referenced_docs);
CREATE INDEX idx_documents_referrer_score ON documents (referrer_score);
