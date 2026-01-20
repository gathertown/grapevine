-- Control DB Migration: add subscriptions table
-- Created: 2025-09-04 08:22:18

BEGIN;

-- Create subscriptions table
CREATE TABLE IF NOT EXISTS public.subscriptions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  tenant_id VARCHAR(255) NOT NULL,
  stripe_customer_id VARCHAR(255) NOT NULL,
  stripe_subscription_id VARCHAR(255) NOT NULL UNIQUE,
  stripe_product_id VARCHAR(255) NOT NULL,
  workos_user_id VARCHAR(255) NULL,
  status VARCHAR(50) NOT NULL,
  start_date TIMESTAMP WITH TIME ZONE NOT NULL,
  billing_cycle_anchor TIMESTAMP WITH TIME ZONE NOT NULL,
  cancel_at TIMESTAMP WITH TIME ZONE NULL,
  canceled_at TIMESTAMP WITH TIME ZONE NULL,
  ended_at TIMESTAMP WITH TIME ZONE NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
  
  -- Foreign key constraint to tenants table
  CONSTRAINT fk_subscriptions_tenant_id 
    FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) 
    ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS subscriptions_tenant_id_idx ON public.subscriptions(tenant_id);
CREATE INDEX IF NOT EXISTS subscriptions_stripe_customer_id_idx ON public.subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS subscriptions_workos_user_id_idx ON public.subscriptions(workos_user_id);
CREATE INDEX IF NOT EXISTS subscriptions_status_idx ON public.subscriptions(status);

-- Trigger for automatic updated_at timestamp
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'update_subscriptions_updated_at'
  ) THEN
    CREATE TRIGGER update_subscriptions_updated_at
      BEFORE UPDATE ON public.subscriptions
      FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();
  END IF;
END$$;

COMMIT;
