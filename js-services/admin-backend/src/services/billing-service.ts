/**
 * Billing Service
 *
 * Core business logic for billing operations including trial period management
 * and subscription status resolution
 */

import { logger, LogContext } from '../utils/logger.js';
import { getControlDbPool } from '../control-db.js';
import { getSubscriptionsByTenantId, SubscriptionRecord } from '../dal/subscriptions.js';
import {
  TrialStatus,
  SubscriptionStatus,
  BillingStatusResponse,
  BillingProduct,
} from '../types/billing.js';

interface TenantRecord {
  id: string;
  workos_org_id: string | null;
  state: string;
  error_message: string | null;
  provisioned_at: Date | null;
  created_at: Date;
  updated_at: Date;
  trial_start_at: Date;
  billing_mode: string;
  enterprise_plan_request_limit: number | null;
}

/**
 * Get tenant information by tenant ID
 */
export async function getTenantById(tenantId: string): Promise<TenantRecord | null> {
  return LogContext.run(
    {
      operation: 'get-tenant-by-id',
      tenantId,
    },
    async () => {
      const pool = getControlDbPool();
      if (!pool) {
        logger.error('Control database not available for tenant lookup');
        return null;
      }

      try {
        const result = await pool.query(
          `SELECT id, workos_org_id, state, error_message, provisioned_at, created_at, updated_at, trial_start_at, billing_mode, enterprise_plan_request_limit
           FROM public.tenants WHERE id = $1`,
          [tenantId]
        );

        if (result.rows.length > 0) {
          return result.rows[0] as TenantRecord;
        }

        return null;
      } catch (error) {
        logger.error('Failed to get tenant record', {
          error: error instanceof Error ? error.message : 'Unknown error',
          tenantId,
        });
        return null;
      }
    }
  );
}

/**
 * Calculate trial status based on tenant trial start date
 */
export function calculateTrialStatus(
  trialStartedAt: Date,
  subscriptions: SubscriptionRecord[]
): TrialStatus {
  const TRIAL_DURATION_DAYS = 30;
  const now = new Date();

  // Trial starts based on trial_start_at timestamp
  const trialStartDate = new Date(trialStartedAt);
  const trialEndDate = new Date(trialStartDate);
  trialEndDate.setDate(trialEndDate.getDate() + TRIAL_DURATION_DAYS);

  const isInTrial = now < trialEndDate;
  const timeDiff = trialEndDate.getTime() - now.getTime();
  const daysRemaining = Math.max(0, Math.ceil(timeDiff / (1000 * 3600 * 24)));

  const hasSubscription = subscriptions.length > 0;

  return {
    isInTrial,
    trialStartDate: trialStartDate.toISOString(),
    trialEndDate: trialEndDate.toISOString(),
    daysRemaining,
    hasSubscription,
  };
}

/**
 * Calculate remaining trial period end date for new subscriptions
 * Returns a Date object representing when the trial should end,
 * or null if the trial has already expired
 */
export function calculateRemainingTrialEnd(tenantCreatedAt: Date): Date | null {
  const TRIAL_DURATION_DAYS = 30;
  const now = new Date();

  // Calculate original trial end date
  const trialStartDate = new Date(tenantCreatedAt);
  const trialEndDate = new Date(trialStartDate);
  trialEndDate.setDate(trialEndDate.getDate() + TRIAL_DURATION_DAYS);

  // If trial has already expired, return null
  if (now >= trialEndDate) {
    return null;
  }

  // Return the trial end date, rounded up to the next day at 23:59:59
  // This ensures users get the full benefit of their remaining trial
  const roundedTrialEnd = new Date(trialEndDate);
  roundedTrialEnd.setHours(23, 59, 59, 999);

  return roundedTrialEnd;
}

/**
 * Get the current active subscription from a list of subscriptions
 */
export function getActiveSubscription(
  subscriptions: SubscriptionRecord[]
): SubscriptionRecord | null {
  // Find the most recent active subscription
  const activeSubscriptions = subscriptions.filter(
    (sub) => sub.status === 'active' || sub.status === 'trialing' || sub.status === 'past_due'
  );

  if (activeSubscriptions.length === 0) {
    return null;
  }

  // Return the most recently created active subscription
  const sorted = activeSubscriptions.sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
  return sorted[0] || null;
}

/**
 * Format subscription status for API response
 */
export function formatSubscriptionStatus(
  subscription: SubscriptionRecord | null
): SubscriptionStatus {
  if (!subscription) {
    return {
      hasActiveSubscription: false,
      subscriptionId: null,
      status: null,
      currentPeriodStart: null,
      currentPeriodEnd: null,
      cancelAtPeriodEnd: false,
      plan: null,
      trialStart: null,
      trialEnd: null,
    };
  }

  // Calculate current period end based on billing cycle anchor
  const currentPeriodStart = new Date(subscription.billing_cycle_anchor);
  const currentPeriodEnd = new Date(currentPeriodStart);
  currentPeriodEnd.setMonth(currentPeriodEnd.getMonth() + 1);

  // Map price ID to tier name for frontend compatibility
  const planTierName = subscription.stripe_price_id
    ? mapPriceIdToTierName(subscription.stripe_price_id)
    : null;

  return {
    hasActiveSubscription: subscription.status === 'active' || subscription.status === 'trialing',
    subscriptionId: subscription.stripe_subscription_id,
    status: subscription.status,
    currentPeriodStart: currentPeriodStart.toISOString(),
    currentPeriodEnd: currentPeriodEnd.toISOString(),
    cancelAtPeriodEnd: !!subscription.cancel_at,
    plan: planTierName || 'unknown', // Fall back to 'unknown' if mapping fails
    trialStart: subscription.trial_start ? subscription.trial_start.toISOString() : null,
    trialEnd: subscription.trial_end ? subscription.trial_end.toISOString() : null,
  };
}

/**
 * Determine if billing is required for a tenant
 */
export function isBillingRequired(trial: TrialStatus, subscription: SubscriptionStatus): boolean {
  // No billing required if in trial period
  if (trial.isInTrial) {
    return false;
  }

  // Billing required if trial expired and no active subscription
  if (!trial.isInTrial && !subscription.hasActiveSubscription) {
    return true;
  }

  // No billing required if has active subscription
  return false;
}

/**
 * Get complete billing status for a tenant
 */
export async function getBillingStatus(tenantId: string): Promise<BillingStatusResponse | null> {
  return LogContext.run(
    {
      operation: 'get-billing-status',
      tenantId,
    },
    async () => {
      // Get tenant information
      const tenant = await getTenantById(tenantId);
      if (!tenant) {
        logger.warn('Tenant not found for billing status', { tenantId });
        return null;
      }

      // Get subscription information
      const subscriptions = await getSubscriptionsByTenantId(tenantId);
      const activeSubscription = getActiveSubscription(subscriptions);

      // Calculate trial status
      const trial = calculateTrialStatus(tenant.trial_start_at, subscriptions);

      // Format subscription status
      const subscription = formatSubscriptionStatus(activeSubscription);

      // Override subscription plan if enterprise plan is set
      if (
        tenant.enterprise_plan_request_limit !== null &&
        tenant.enterprise_plan_request_limit > 0
      ) {
        subscription.plan = 'enterprise';
        subscription.hasActiveSubscription = true;
      }

      // Determine if billing is required
      const billingRequired = isBillingRequired(trial, subscription);

      // Read ENABLE_BILLING_USAGE_UI flag from environment
      const enableBillingUsageUI = process.env.ENABLE_BILLING_USAGE_UI === 'true';

      return {
        tenantId,
        billingMode: tenant.billing_mode as 'gather_managed' | 'grapevine_managed',
        trial,
        subscription,
        billingRequired,
        enableBillingUsageUI,
      };
    }
  );
}

/**
 * Get all available billing products
 * Product configuration is stored in environment variables for flexibility
 *
 * NOTE: Prices are currently hardcoded in this function. When updating prices:
 * 1. Update the price values in this function
 * 2. Update the corresponding documentation in docs/billing.md
 * 3. Update any frontend tier definitions if display formatting changes
 *
 * FUTURE ENHANCEMENT: Consider fetching prices from Stripe as the source of truth
 * rather than hardcoding them here. This would require caching and error handling
 * for when Stripe API is unavailable.
 */
export function getBillingProducts(): BillingProduct[] {
  const products: BillingProduct[] = [];

  // Basic plan
  if (process.env.STRIPE_PRICE_ID_BASIC_MONTHLY) {
    products.push({
      id: 'basic',
      stripePriceId: process.env.STRIPE_PRICE_ID_BASIC_MONTHLY,
      price: 15000,
      currency: 'usd',
      interval: 'month',
      limits: {
        maxRequests: 200,
      },
    });
  }

  // Team plan
  if (process.env.STRIPE_PRICE_ID_TEAM_MONTHLY) {
    products.push({
      id: 'team',
      stripePriceId: process.env.STRIPE_PRICE_ID_TEAM_MONTHLY,
      price: 300,
      currency: 'usd',
      interval: 'month',
      limits: {
        maxRequests: 500,
      },
    });
  }

  // Pro plan
  if (process.env.STRIPE_PRICE_ID_PRO_MONTHLY) {
    products.push({
      id: 'pro',
      stripePriceId: process.env.STRIPE_PRICE_ID_PRO_MONTHLY,
      price: 1500,
      currency: 'usd',
      interval: 'month',
      limits: {
        maxRequests: 4000,
      },
    });
  }

  // Ultra plan (renamed from Ultimate)
  if (process.env.STRIPE_PRICE_ID_ULTRA_MONTHLY) {
    products.push({
      id: 'ultra',
      stripePriceId: process.env.STRIPE_PRICE_ID_ULTRA_MONTHLY,
      price: 5000,
      currency: 'usd',
      interval: 'month',
      limits: {
        maxRequests: 15000,
      },
    });
  }

  return products;
}

/**
 * Get a specific product by ID
 */
export function getBillingProduct(id: string): BillingProduct | null {
  const products = getBillingProducts();
  return products.find((product) => product.id === id) || null;
}

/**
 * Map Stripe price ID to tier name
 * Uses environment variables to create reverse lookup from price ID to tier name
 */
export function mapPriceIdToTierName(stripePriceId: string): string | null {
  // Create reverse mapping from environment variables
  const priceEnvVars = {
    STRIPE_PRICE_ID_BASIC_MONTHLY: 'basic',
    STRIPE_PRICE_ID_TEAM_MONTHLY: 'team',
    STRIPE_PRICE_ID_PRO_MONTHLY: 'pro',
    STRIPE_PRICE_ID_ULTRA_MONTHLY: 'ultra',
  };

  // Check each environment variable to find matching price ID
  for (const [envVar, tierName] of Object.entries(priceEnvVars)) {
    const envPriceId = process.env[envVar];
    if (envPriceId && envPriceId === stripePriceId) {
      return tierName;
    }
  }

  // If no match found, return null
  return null;
}
