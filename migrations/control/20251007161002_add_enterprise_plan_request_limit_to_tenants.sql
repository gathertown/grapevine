-- Control DB Migration: add enterprise_plan_request_limit to tenants
-- Created: 2025-10-07 16:10:02

BEGIN;

-- Add enterprise_plan_request_limit column to tenants table
-- NULL = no enterprise plan, >0 = custom monthly request limit for enterprise customers
ALTER TABLE public.tenants ADD COLUMN enterprise_plan_request_limit INTEGER NULL
    CHECK (enterprise_plan_request_limit IS NULL OR enterprise_plan_request_limit > 0);

-- Add comment to explain the column
COMMENT ON COLUMN public.tenants.enterprise_plan_request_limit IS
    'Monthly request limit for enterprise plans. NULL = no enterprise plan, >0 = custom limit. When set, this takes precedence over Stripe subscriptions and trial limits.';

COMMIT;
