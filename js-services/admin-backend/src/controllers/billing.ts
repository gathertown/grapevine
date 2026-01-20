import { Router, Request, Response } from 'express';
import axios from 'axios';
import { logger } from '../utils/logger.js';
import { getFrontendUrl, isBillingEnabled } from '../utils/config.js';
import { getOrInitializeStripe } from '../stripe-client.js';
import { getOrInitializeRedis } from '../redis-client.js';
import { requireAdmin } from '../middleware/auth-middleware.js';
import {
  getBillingStatus,
  getBillingProducts,
  calculateRemainingTrialEnd,
  getTenantById,
} from '../services/billing-service.js';
import { getSubscriptionsByTenantId } from '../dal/subscriptions.js';
import { generateInternalJWT } from '../jwt-generator.js';
import { getMCPServerUrl } from './mcp.js';
import { BillingUsageResponse } from '../types/billing.js';

const billingRouter = Router();

/**
 * Invalidate billing limits cache for a tenant
 *
 * This removes the cached billing limits from Redis, forcing the next
 * request to fetch fresh data from the database.
 *
 * @param tenantId The tenant ID to invalidate cache for
 */
async function invalidateBillingCache(tenantId: string): Promise<void> {
  if (!tenantId) {
    logger.warn('Cannot invalidate billing cache: tenant ID is required');
    return;
  }

  try {
    const redis = getOrInitializeRedis();

    if (!redis) {
      logger.debug('Redis not available - skipping billing cache invalidation');
      return;
    }

    const cacheKey = `billing_limits:${tenantId}`;

    // Delete the cache key
    const result = await redis.del(cacheKey);

    if (result === 1) {
      logger.info(`Successfully invalidated billing cache for tenant ${tenantId}`);
    } else {
      logger.debug(`No billing cache found to invalidate for tenant ${tenantId}`);
    }
  } catch (error) {
    // Log error but don't throw - cache invalidation failures shouldn't break subscription updates
    logger.error(`Failed to invalidate billing cache for tenant ${tenantId}:`, {
      error: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}

// Check if billing is enabled for this deployment
// This endpoint is public (no auth required) so the frontend can determine
// whether to show billing UI before the user is authenticated
// Returns true if STRIPE_SECRET_KEY is configured
billingRouter.get('/enabled', async (_req: Request, res: Response) => {
  res.json({ enabled: isBillingEnabled() });
});

/**
 * Middleware to ensure billing is enabled before processing billing routes.
 * Returns 404 with a "feature disabled" message if billing is not enabled.
 */
function requireBillingEnabled(_req: Request, res: Response, next: () => void) {
  if (!isBillingEnabled()) {
    return res.status(404).json({
      error: 'Billing is not enabled for this deployment',
    });
  }
  next();
}

// Get available billing products
billingRouter.get('/products', requireBillingEnabled, async (_req: Request, res: Response) => {
  try {
    const products = getBillingProducts();
    res.json({ products });
  } catch (error) {
    logger.error('Failed to get billing products', {
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    res.status(500).json({
      error: 'Failed to get billing products',
    });
  }
});

// Endpoint for creating a checkout session -
billingRouter.post(
  '/create-subscription',
  requireBillingEnabled,
  requireAdmin,
  async (req: Request, res: Response) => {
    const stripe = getOrInitializeStripe();

    if (!stripe) {
      logger.warn('Stripe client is not initialized');
      return res.status(500).json({ error: 'Stripe client is not initialized' });
    }

    const userId = req.user?.id;
    if (!userId) {
      return res.status(400).json({ error: 'User not authenticated' });
    }

    const tenantId = req.user?.tenantId;
    const organizationId = req.user?.organizationId;
    if (!tenantId || !organizationId) {
      return res.status(400).json({
        error: 'No tenant found for organization',
      });
    }

    // Get the product ID from request body, default to 'team' for backwards compatibility
    const { productId = 'team' } = req.body;

    // Find the product configuration
    const products = getBillingProducts();
    const selectedProduct = products.find((p) => p.id === productId);

    if (!selectedProduct) {
      return res.status(400).json({
        error: `Product '${productId}' not found or not configured`,
      });
    }

    // Get tenant information to calculate remaining trial period
    const tenant = await getTenantById(tenantId);
    if (!tenant) {
      return res.status(400).json({
        error: 'Tenant not found',
      });
    }

    // Calculate remaining trial end date
    const remainingTrialEnd = calculateRemainingTrialEnd(tenant.trial_start_at);

    // Prepare subscription data with trial period if applicable
    const subscriptionData: {
      metadata: Record<string, string>;
      trial_end?: number;
    } = {
      metadata: {
        userId,
        tenantId,
        organizationId,
        email: req.user?.email || '',
        productId: selectedProduct.id,
      },
    };

    // If there's remaining trial time, carry it over to Stripe subscription
    if (remainingTrialEnd) {
      subscriptionData.trial_end = Math.floor(remainingTrialEnd.getTime() / 1000); // Stripe expects Unix timestamp
      logger.info('Carrying over trial period to subscription', {
        tenantId,
        trialEndDate: remainingTrialEnd.toISOString(),
        trialEndUnix: subscriptionData.trial_end,
      });
    }

    // Create the checkout session to start billing for a subscription
    const session = await stripe.checkout.sessions.create({
      mode: 'subscription',
      customer_email: req.user?.email || undefined,
      line_items: [
        {
          price: selectedProduct.stripePriceId,
          quantity: 1,
        },
      ],
      subscription_data: subscriptionData,
      allow_promotion_codes: true,
      cancel_url: `${getFrontendUrl()}/billing`,
      // TODO(AIVP-458): Show a nice UI when the checkout is successful
      success_url: `${getFrontendUrl()}/billing`,
    });

    if (!session.url) {
      logger.error('Failed to create Stripe checkout session');
      return res.status(500).json({ error: 'Failed to create checkout session' });
    }

    res.json({ url: session.url });
  }
);

// Get billing and trial status for the authenticated user's tenant
billingRouter.get(
  '/status',
  requireBillingEnabled,
  requireAdmin,
  async (req: Request, res: Response) => {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for user',
      });
    }

    try {
      const billingStatus = await getBillingStatus(tenantId);
      if (!billingStatus) {
        return res.status(404).json({
          error: 'Tenant not found',
        });
      }

      res.json(billingStatus);
    } catch (error) {
      logger.error('Failed to get billing status', {
        error: error instanceof Error ? error.message : 'Unknown error',
        tenantId,
      });
      res.status(500).json({
        error: 'Failed to get billing status',
      });
    }
  }
);

// Get billing usage from MCP server
billingRouter.get(
  '/usage',
  requireBillingEnabled,
  requireAdmin,
  async (req: Request, res: Response) => {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for user',
      });
    }

    try {
      const mcpServerUrl = getMCPServerUrl();

      // Generate internal JWT for MCP server authentication
      let bearerToken: string;
      try {
        bearerToken = await generateInternalJWT(tenantId, undefined, req.user?.email);
        logger.debug('Generated internal JWT for billing usage request', {
          tenantId,
          email: req.user?.email,
          operation: 'billing-usage-jwt-generation',
        });
      } catch (error) {
        logger.error('Failed to generate internal JWT', error, {
          tenantId,
          operation: 'billing-usage-jwt-generation',
        });
        return res.status(500).json({
          error: 'Failed to generate authentication token',
        });
      }

      // Call MCP server's /billing/usage endpoint
      const response = await axios.get(`${mcpServerUrl}/v1/billing/usage`, {
        headers: {
          Authorization: `Bearer ${bearerToken}`,
        },
        timeout: 10000, // 10 second timeout
      });

      logger.debug('Retrieved billing usage from MCP server', {
        tenantId,
        operation: 'billing-usage-success',
      });

      const usageResponse = response.data as BillingUsageResponse;

      res.json(usageResponse);
    } catch (error) {
      logger.error('Failed to get billing usage', {
        error: error instanceof Error ? error.message : 'Unknown error',
        tenantId,
        operation: 'billing-usage-error',
      });

      // Check if this is an HTTP error from axios
      const httpError = error as { response?: { status?: number; data?: unknown } };
      if (httpError.response) {
        const status = httpError.response.status || 500;
        const errorData = httpError.response.data || (error as Error).message;

        return res.status(status).json({
          error: 'MCP server error',
          details: errorData,
        });
      }

      res.status(500).json({
        error: 'Failed to get billing usage',
      });
    }
  }
);

// Endpoint for creating a Stripe Customer Portal session
billingRouter.get(
  '/portal-session',
  requireBillingEnabled,
  requireAdmin,
  async (req: Request, res: Response) => {
    const stripe = getOrInitializeStripe();

    if (!stripe) {
      logger.warn('Stripe client is not initialized');
      return res.status(500).json({ error: 'Stripe client is not initialized' });
    }

    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for user',
      });
    }

    try {
      // Get the active subscription for this tenant to find the customer
      const subscriptions = await getSubscriptionsByTenantId(tenantId);
      const activeSubscription = subscriptions.find((sub) =>
        ['active', 'trialing', 'past_due'].includes(sub.status)
      );

      if (!activeSubscription) {
        logger.warn('No active subscription found for portal session', { tenantId });
        return res.status(400).json({
          error: 'No active subscription found. Please subscribe first.',
        });
      }

      // Create the customer portal session
      const session = await stripe.billingPortal.sessions.create({
        customer: activeSubscription.stripe_customer_id,
        return_url: `${getFrontendUrl()}/billing?from=stripe-portal`,
      });

      if (!session.url) {
        logger.error('Failed to create Stripe portal session');
        return res.status(500).json({ error: 'Failed to create portal session' });
      }

      res.json({ url: session.url });
    } catch (error) {
      // Check for specific Stripe portal configuration error
      const isPortalConfigError =
        error?.type === 'StripeInvalidRequestError' &&
        error?.message?.includes('No configuration provided');

      if (isPortalConfigError) {
        logger.error('Stripe Customer Portal not configured', {
          tenantId,
          message: 'Customer Portal must be configured in Stripe Dashboard',
          setupUrl: 'https://dashboard.stripe.com/test/settings/billing/portal',
        });
      } else {
        logger.error('Error creating portal session', {
          error: error instanceof Error ? error.message : 'Unknown error',
          tenantId,
        });
      }

      return res.status(500).json({ error: 'Failed to create portal session' });
    }
  }
);

// Cancel subscription at period end
billingRouter.post(
  '/cancel-subscription',
  requireBillingEnabled,
  requireAdmin,
  async (req: Request, res: Response) => {
    const stripe = getOrInitializeStripe();

    if (!stripe) {
      logger.warn('Stripe client is not initialized');
      return res.status(500).json({ error: 'Stripe client is not initialized' });
    }

    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for user',
      });
    }

    try {
      // Get the active subscription for this tenant
      const subscriptions = await getSubscriptionsByTenantId(tenantId);
      const activeSubscription = subscriptions.find((sub) =>
        ['active', 'trialing', 'past_due'].includes(sub.status)
      );

      if (!activeSubscription) {
        logger.warn('No active subscription found for cancellation', { tenantId });
        return res.status(400).json({
          error: 'No active subscription found',
        });
      }

      // Cancel the subscription at period end
      const subscription = await stripe.subscriptions.update(
        activeSubscription.stripe_subscription_id,
        {
          cancel_at_period_end: true,
        }
      );

      // Invalidate billing limits cache since subscription status changed
      await invalidateBillingCache(tenantId);

      res.json({
        success: true,
        subscription: {
          id: subscription.id,
          cancelAtPeriodEnd: subscription.cancel_at_period_end,
        },
      });
    } catch (error) {
      logger.error('Error canceling subscription', {
        error: error instanceof Error ? error.message : 'Unknown error',
        tenantId,
      });
      return res.status(500).json({ error: 'Failed to cancel subscription' });
    }
  }
);

// Reactivate subscription (remove cancel at period end)
billingRouter.post(
  '/reactivate-subscription',
  requireBillingEnabled,
  requireAdmin,
  async (req: Request, res: Response) => {
    const stripe = getOrInitializeStripe();

    if (!stripe) {
      logger.warn('Stripe client is not initialized');
      return res.status(500).json({ error: 'Stripe client is not initialized' });
    }

    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for user',
      });
    }

    try {
      // Get subscriptions for this tenant - be more permissive for reactivation
      const subscriptions = await getSubscriptionsByTenantId(tenantId);
      // For reactivation, allow any subscription that hasn't ended yet
      const reactivatableSubscription = subscriptions.find(
        (sub) =>
          ['active', 'trialing', 'past_due', 'canceled'].includes(sub.status) && !sub.ended_at
      );

      if (!reactivatableSubscription) {
        logger.warn('No reactivatable subscription found', { tenantId });
        return res.status(400).json({
          error: 'No subscription found that can be reactivated',
        });
      }

      // Reactivate the subscription by removing cancel_at_period_end
      const subscription = await stripe.subscriptions.update(
        reactivatableSubscription.stripe_subscription_id,
        {
          cancel_at_period_end: false,
        }
      );

      // Invalidate billing limits cache since subscription status changed
      await invalidateBillingCache(tenantId);

      res.json({
        success: true,
        subscription: {
          id: subscription.id,
          cancelAtPeriodEnd: subscription.cancel_at_period_end,
          status: subscription.status,
        },
      });
    } catch (error) {
      logger.error('Error reactivating subscription', {
        error: error instanceof Error ? error.message : 'Unknown error',
        tenantId,
      });
      return res.status(500).json({ error: 'Failed to reactivate subscription' });
    }
  }
);

// Test endpoint to verify Stripe SDK is initialized
// This is overly conservative, but since we don't have E2E tests,
// want to make sure I'm not breaking the BE with Stripe integration.
// Note: No requireBillingEnabled middleware - health checks should always respond
billingRouter.get('/health', requireAdmin, async (_req: Request, res: Response) => {
  // If billing is disabled, report healthy but indicate billing is off
  if (!isBillingEnabled()) {
    res.json({
      status: 'ok',
      billing: 'disabled',
    });
    return;
  }

  const stripe = getOrInitializeStripe();

  if (!stripe) {
    res.status(500).json({
      error: 'Failed to initialize Stripe',
    });
    return;
  }

  try {
    // Try a simple call to make sure it's wired up correctly
    await stripe.products.list({ limit: 1 });
    res.json({
      status: 'ok',
    });
  } catch (err) {
    logger.warn('Stripe health check failed', err);
    res.status(500).json({ error: 'Failed to call Stripe' });
  }
});

export { billingRouter };
