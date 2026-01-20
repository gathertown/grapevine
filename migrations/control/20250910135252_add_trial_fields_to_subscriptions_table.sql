-- Control DB Migration: add trial fields to subscriptions table
-- Created: 2025-09-10 13:52:52

BEGIN;

-- Add trial_start and trial_end fields to capture Stripe trial information
ALTER TABLE public.subscriptions 
ADD COLUMN trial_start TIMESTAMP WITH TIME ZONE NULL,
ADD COLUMN trial_end TIMESTAMP WITH TIME ZONE NULL;

-- Add index for trial_end for efficient queries on trial status
CREATE INDEX IF NOT EXISTS subscriptions_trial_end_idx ON public.subscriptions(trial_end);

COMMIT;
