-- Tenant DB Migration: backfill null bot_response_message_id values
-- Created: 2025-09-03 17:57:37
--
-- This migration backfills NULL bot_response_message_id values in the slack_messages table
-- by finding corresponding bot messages in the ingest_artifact table.
--
-- Background: The bot_response_message_id column was added in 20250825000000_add_bot_response_message_id.sql
-- but existing records have NULL values, causing reaction tracking to miss bot responses.
-- This causes reactions to show in expanded thread view but not in thread headers.

BEGIN;

-- First, let's log the current state for tracking
DO $$
DECLARE
    null_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO null_count 
    FROM public.slack_messages 
    WHERE bot_response_message_id IS NULL;
    
    RAISE NOTICE 'Starting backfill migration: % records have NULL bot_response_message_id', null_count;
END $$;

-- Update NULL bot_response_message_id values by finding corresponding bot messages
-- in the ingest_artifact table
UPDATE public.slack_messages 
SET bot_response_message_id = (
    SELECT ia.content ->> 'ts' 
    FROM public.ingest_artifact ia 
    WHERE ia.entity = 'slack_message'
      AND ia.content ->> 'channel' = slack_messages.channel_id
      AND (
        -- Bot message in same thread as the question
        ia.content ->> 'thread_ts' = slack_messages.message_id 
        OR 
        -- Bot message is direct response when no thread exists
        (ia.content ->> 'thread_ts' IS NULL AND ia.content ->> 'ts' = slack_messages.message_id)
      )
      AND (
        -- Identify bot messages by bot_id or subtype
        ia.content ->> 'bot_id' IS NOT NULL 
        OR ia.content ->> 'subtype' = 'bot_message'
      )
    -- Order by timestamp to get the earliest bot response (most reliable)
    ORDER BY (ia.content ->> 'ts')::double precision ASC
    LIMIT 1
)
WHERE bot_response_message_id IS NULL
  AND EXISTS (
    -- Only update records where we can find a corresponding bot message
    SELECT 1 FROM public.ingest_artifact ia 
    WHERE ia.entity = 'slack_message'
      AND ia.content ->> 'channel' = slack_messages.channel_id
      AND (
        ia.content ->> 'thread_ts' = slack_messages.message_id 
        OR (ia.content ->> 'thread_ts' IS NULL AND ia.content ->> 'ts' = slack_messages.message_id)
      )
      AND (
        ia.content ->> 'bot_id' IS NOT NULL 
        OR ia.content ->> 'subtype' = 'bot_message'
      )
  );

-- Log the results
DO $$
DECLARE
    updated_count INTEGER;
    remaining_null_count INTEGER;
BEGIN
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    
    SELECT COUNT(*) INTO remaining_null_count 
    FROM public.slack_messages 
    WHERE bot_response_message_id IS NULL;
    
    RAISE NOTICE 'Migration complete: Updated % records, % records still have NULL bot_response_message_id', 
                 updated_count, remaining_null_count;
    
    IF remaining_null_count > 0 THEN
        RAISE NOTICE 'Remaining NULL records may be questions without corresponding bot responses in ingest_artifact';
    END IF;
END $$;

COMMIT;
