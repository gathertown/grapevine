/**
 * Billing Types
 *
 * TypeScript interfaces for billing and subscription management
 */

export interface TrialStatus {
  isInTrial: boolean;
  trialStartDate: string;
  trialEndDate: string;
  daysRemaining: number;
  hasSubscription: boolean;
}

export interface SubscriptionStatus {
  hasActiveSubscription: boolean;
  subscriptionId: string | null;
  status: string | null;
  currentPeriodStart: string | null;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
  plan: string | null;
  trialStart: string | null;
  trialEnd: string | null;
}

export interface BillingStatusResponse {
  tenantId: string;
  billingMode: 'gather_managed' | 'grapevine_managed';
  trial: TrialStatus;
  subscription: SubscriptionStatus;
  billingRequired: boolean;

  // Feature flag to indicate if billing UI should be enabled
  // Controlled by ENABLE_BILLING_USAGE_UI environment variable
  enableBillingUsageUI: boolean;
}

export interface CreateSubscriptionResponse {
  url: string;
}

export interface BillingHealthResponse {
  status: 'ok';
}

export interface BillingErrorResponse {
  error: string;
}

/**
 * IMPORTANT: This type must be kept in sync with the response structure
 * from src/mcp/api/billing_endpoint.py:billing_usage_endpoint
 *
 * The Python endpoint returns camelCase JSON directly for TypeScript consumers.
 */
export interface BillingUsageResponse {
  tenantId: string;
  requestsUsed: number;
  requestsAvailable: number;
  tier: string;
  isTrial: boolean;
  isGatherManaged: boolean;
  billingCycleAnchor?: string;
  trialStartAt?: string;
}

export interface ProductLimits {
  maxRequests?: number;
}

export interface BillingProduct {
  id: string;
  stripePriceId: string;
  price: number;
  currency: string;
  interval: 'month' | 'year';
  limits: ProductLimits;
}

export interface ProductsResponse {
  products: BillingProduct[];
}
