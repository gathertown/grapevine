-- Add is_proactive column to slack_messages table to track proactive responses
-- Defaults to FALSE for all existing records
-- Use scripts/backfill_proactive_responses.py to backfill historical data
ALTER TABLE public.slack_messages
ADD COLUMN is_proactive BOOLEAN NOT NULL DEFAULT FALSE;

-- Add index for filtering by proactive responses
CREATE INDEX idx_slack_messages_is_proactive ON public.slack_messages USING btree (is_proactive);

-- Add comment to document the column
COMMENT ON COLUMN public.slack_messages.is_proactive IS 'True if this was a proactive response (not a DM/mention), false otherwise';
