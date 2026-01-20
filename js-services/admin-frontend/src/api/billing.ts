import { apiClient } from './client';
import type {
  BillingStatusResponse,
  CreateSubscriptionResponse,
  BillingHealthResponse,
  PortalSessionResponse,
  BillingUsageResponse,
} from '../types';

export interface BillingEnabledResponse {
  enabled: boolean;
}

export const billingApi = {
  /**
   * Check if billing is enabled for this deployment.
   * This is a public endpoint (no auth required).
   */
  isEnabled: async (): Promise<BillingEnabledResponse> => {
    return apiClient.get<BillingEnabledResponse>('/api/billing/enabled');
  },

  /**
   * Get billing status for the current tenant
   */
  getStatus: async (): Promise<BillingStatusResponse> => {
    return apiClient.get<BillingStatusResponse>('/api/billing/status');
  },

  /**
   * Get billing usage for the current tenant
   */
  getUsage: async (): Promise<BillingUsageResponse> => {
    return apiClient.get<BillingUsageResponse>('/api/billing/usage');
  },

  /**
   * Create a subscription checkout session
   */
  createSubscription: async (
    subscriptionType: 'basic' | 'team' | 'pro' | 'ultra' = 'team'
  ): Promise<CreateSubscriptionResponse> => {
    return apiClient.post<CreateSubscriptionResponse>('/api/billing/create-subscription', {
      productId: subscriptionType,
    });
  },

  /**
   * Check billing health
   */
  getHealth: async (): Promise<BillingHealthResponse> => {
    return apiClient.get<BillingHealthResponse>('/api/billing/health');
  },

  /**
   * Get Stripe Customer Portal session
   */
  getPortalSession: async (): Promise<PortalSessionResponse> => {
    return apiClient.get<PortalSessionResponse>('/api/billing/portal-session');
  },

  /**
   * Cancel subscription at period end
   */
  cancelSubscription: async () => {
    return apiClient.post('/api/billing/cancel-subscription');
  },

  /**
   * Reactivate subscription (remove cancel at period end)
   */
  reactivateSubscription: async () => {
    return apiClient.post('/api/billing/reactivate-subscription');
  },
};
