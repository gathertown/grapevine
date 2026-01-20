-- Increase documents.id field from VARCHAR(255) to VARCHAR(2048) to support long GitHub file paths
-- GitHub file paths in monorepos can exceed 255 characters with deeply nested structures

ALTER TABLE public.documents
ALTER COLUMN id TYPE VARCHAR(2048);
