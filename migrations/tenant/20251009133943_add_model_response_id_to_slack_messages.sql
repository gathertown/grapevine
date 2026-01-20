-- Tenant DB Migration: add model_response_id to slack_messages
-- Created: 2025-10-09 13:39:43

BEGIN;

-- Add model_response_id column to slack_messages table
-- This column stores the backend response ID for conversation continuation,
-- allowing us to maintain context across multiple exchanges without parsing message text.
ALTER TABLE public.slack_messages
ADD COLUMN model_response_id TEXT;

-- Add index for efficient lookups by response_id
CREATE INDEX idx_slack_messages_model_response_id
ON public.slack_messages(model_response_id);

-- Add comment explaining the column
COMMENT ON COLUMN public.slack_messages.model_response_id IS
  'Backend response ID for conversation continuation. Used to maintain context across multiple exchanges.';

COMMIT;
