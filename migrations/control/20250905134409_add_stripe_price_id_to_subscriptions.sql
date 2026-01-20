-- Control DB Migration: add stripe price id to subscriptions
-- Created: 2025-09-05 13:44:09

BEGIN;

-- Add stripe_price_id column as NULLABLE first to avoid constraint violations
-- This will store the Stripe price ID alongside the existing product ID
-- to support proper tier mapping in the billing system
ALTER TABLE public.subscriptions ADD COLUMN stripe_price_id VARCHAR(255);

-- Add index for performance since we'll be querying by price ID
CREATE INDEX idx_subscriptions_stripe_price_id ON public.subscriptions(stripe_price_id);

COMMIT;
