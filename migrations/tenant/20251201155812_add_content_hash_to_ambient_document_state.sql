-- Migration: add_content_hash_to_ambient_document_state
-- Created: 2025-12-01 15:58:12

-- Add content_hash column to track document changes
-- Add content column to store document content for diff generation
-- Allows reprocessing when document content changes and showing agent what changed
ALTER TABLE ambient_document_state 
ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64),
ADD COLUMN IF NOT EXISTS content TEXT;

-- Add index for efficient lookups by document_id and content_hash
CREATE INDEX IF NOT EXISTS idx_ambient_document_state_content_hash 
    ON ambient_document_state(document_id, content_hash);
