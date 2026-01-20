-- Add bot_response_message_id column to slack_messages table
-- This column stores the bot's response message ID for linking reactions to Q&A interactions

ALTER TABLE public.slack_messages 
ADD COLUMN bot_response_message_id TEXT;