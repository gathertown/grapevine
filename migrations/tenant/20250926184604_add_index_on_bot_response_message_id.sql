-- Tenant DB Migration: add index on bot_response_message_id
-- Created: 2025-09-26 18:46:04
--
-- Add index on bot_response_message_id to optimize reaction handling lookups
-- The Slack bot queries this column to determine if a reacted message was a bot response

BEGIN;

CREATE INDEX idx_slack_messages_bot_response_message_id ON public.slack_messages USING btree (bot_response_message_id);

COMMIT;