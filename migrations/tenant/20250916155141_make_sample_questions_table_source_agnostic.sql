-- Tenant DB Migration: make sample questions table source agnostic
-- Created: 2025-09-16 15:51:41
--
-- This migration removes Slack-specific columns from the sample_questions table
-- and adds generic source and metadata columns to support multiple sources

BEGIN;

-- Drop existing unique index on source_message_id since we're changing the column
DROP INDEX IF EXISTS idx_sample_questions_unique_message;

-- Remove Slack-specific columns
ALTER TABLE sample_questions
    DROP COLUMN IF EXISTS channel_name,
    DROP COLUMN IF EXISTS channel_id,
    DROP COLUMN IF EXISTS user_id,
    DROP COLUMN IF EXISTS username,
    DROP COLUMN IF EXISTS message_timestamp,
    DROP COLUMN IF EXISTS thread_reply_count,
    DROP COLUMN IF EXISTS reaction_count;

-- Rename source_message_id to source_id for generic use
ALTER TABLE sample_questions
    RENAME COLUMN source_message_id TO source_id;

-- Add new generic columns
ALTER TABLE sample_questions
    ADD COLUMN source VARCHAR(50) NOT NULL DEFAULT 'slack',
    ADD COLUMN metadata JSONB DEFAULT '{}';

-- Remove the default after adding the column
ALTER TABLE sample_questions
    ALTER COLUMN source DROP DEFAULT;

-- Create new indexes for performance
CREATE INDEX idx_sample_questions_source ON sample_questions(source);
CREATE INDEX idx_sample_questions_source_score ON sample_questions(source, score DESC);
CREATE UNIQUE INDEX idx_sample_questions_unique_source_id ON sample_questions(source, source_id);

-- Add constraint to ensure source is not empty
ALTER TABLE sample_questions
    ADD CONSTRAINT sample_questions_source_check CHECK (length(source) > 0);

COMMIT;
