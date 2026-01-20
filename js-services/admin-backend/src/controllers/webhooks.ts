import { Router, Request, Response } from 'express';
import express from 'express';
import { logger } from '../utils/logger.js';
import { getOrInitializeStripe } from '../stripe-client.js';
import { getOrInitializeRedis } from '../redis-client.js';
import Stripe from 'stripe';
import {
  createSubscription,
  updateSubscriptionByStripeId,
  getSubscriptionByStripeId,
  mapStripeSubscriptionToCreateData,
  mapStripeSubscriptionToUpdateData,
} from '../dal/subscriptions.js';
import { extractTrialDates } from '../utils/stripe-helpers.js';

const webhooksRouter = Router();

// Stripe webhook endpoint for subscription events
webhooksRouter.post(
  '/billing/stripe',
  express.raw({ type: 'application/json' }),
  async (req: Request, res: Response) => {
    const stripe = getOrInitializeStripe();

    if (!stripe) {
      logger.error('Stripe client is not initialized for webhook processing');
      return res.status(500).json({ error: 'Stripe client not available' });
    }

    const sig = req.headers['stripe-signature'] as string;
    const endpointSecret = process.env.STRIPE_WEBHOOK_SECRET;

    if (!endpointSecret) {
      logger.error('STRIPE_WEBHOOK_SECRET is not configured');
      return res.status(500).json({ error: 'Webhook secret not configured' });
    }

    let event: Stripe.Event;

    try {
      // Verify webhook signature
      event = stripe.webhooks.constructEvent(req.body, sig, endpointSecret);
    } catch (err) {
      logger.warn('Webhook signature verification failed', {
        error: err instanceof Error ? err.message : 'Unknown error',
      });
      return res.status(400).json({ error: 'Invalid signature' });
    }

    // Handle subscription events
    try {
      switch (event.type) {
        case 'customer.subscription.created':
          await handleSubscriptionCreated(event.data.object as Stripe.Subscription);
          break;
        case 'customer.subscription.updated':
          await handleSubscriptionUpdated(event.data.object as Stripe.Subscription);
          break;
        case 'customer.subscription.deleted':
          await handleSubscriptionDeleted(event.data.object as Stripe.Subscription);
          break;
        case 'customer.subscription.trial_will_end':
          await handleTrialWillEnd(event.data.object as Stripe.Subscription);
          break;
        case 'invoice.payment_succeeded':
          await handlePaymentSucceeded(event.data.object as Stripe.Invoice);
          break;
        case 'invoice.payment_failed':
          await handlePaymentFailed(event.data.object as Stripe.Invoice);
          break;
        default:
          logger.info(`Unhandled webhook event type: ${event.type}`);
      }

      res.json({ received: true });
    } catch (error) {
      logger.error('Error processing webhook event', {
        eventType: event.type,
        eventId: event.id,
        error: error instanceof Error ? error.message : 'Unknown error',
      });
      res.status(500).json({ error: 'Webhook processing failed' });
    }
  }
);

// Subscription event handlers
async function handleSubscriptionCreated(subscription: Stripe.Subscription): Promise<void> {
  logger.info('Subscription created', {
    subscriptionId: subscription.id,
    customerId: subscription.customer,
    status: subscription.status,
    ...extractTrialDates(subscription),
  });

  // Extract tenant and user information from metadata
  const tenantId = subscription.metadata?.tenantId;
  const userId = subscription.metadata?.userId;

  if (!tenantId) {
    logger.error('No tenantId found in subscription metadata', {
      subscriptionId: subscription.id,
      metadata: subscription.metadata,
    });
    return;
  }

  try {
    const subscriptionData = mapStripeSubscriptionToCreateData(subscription, tenantId, userId);
    const success = await createSubscription(subscriptionData);

    logger.info(
      `Successfully created subscription in database ${subscription.id} for tenant ${tenantId}`
    );

    if (!success) {
      logger.error('Failed to create subscription in database', {
        subscriptionId: subscription.id,
        tenantId,
      });
    } else {
      // Invalidate billing limits cache since subscription tier may have changed
      await invalidateBillingCache(tenantId);
    }
  } catch (error) {
    logger.error('Error creating subscription in database', {
      subscriptionId: subscription.id,
      tenantId,
      error: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}

async function handleSubscriptionUpdated(subscription: Stripe.Subscription): Promise<void> {
  logger.info('Subscription updated', {
    subscriptionId: subscription.id,
    customerId: subscription.customer,
    status: subscription.status,
    ...extractTrialDates(subscription),
  });

  try {
    // Check if subscription exists in our database
    const existingSubscription = await getSubscriptionByStripeId(subscription.id);

    if (!existingSubscription) {
      logger.warn('Received update for subscription not in database, attempting to create', {
        subscriptionId: subscription.id,
      });

      // If subscription doesn't exist, try to create it using metadata
      const tenantId = subscription.metadata?.tenantId;
      const userId = subscription.metadata?.userId;

      if (!tenantId) {
        logger.error('No tenantId found in subscription metadata for creation', {
          subscriptionId: subscription.id,
          metadata: subscription.metadata,
        });
        return;
      }

      const subscriptionData = mapStripeSubscriptionToCreateData(subscription, tenantId, userId);
      const createSuccess = await createSubscription(subscriptionData);
      if (createSuccess) {
        // Invalidate billing limits cache since subscription was created
        await invalidateBillingCache(tenantId);
      }
      return;
    }

    // Update existing subscription
    const updateData = mapStripeSubscriptionToUpdateData(subscription);
    const success = await updateSubscriptionByStripeId(subscription.id, updateData);

    if (!success) {
      logger.error('Failed to update subscription in database', {
        subscriptionId: subscription.id,
      });
    } else {
      // Invalidate billing limits cache since subscription details may have changed
      await invalidateBillingCache(existingSubscription.tenant_id);
    }
  } catch (error) {
    logger.error('Error updating subscription in database', {
      subscriptionId: subscription.id,
      error: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}

async function handleSubscriptionDeleted(subscription: Stripe.Subscription): Promise<void> {
  logger.info('Subscription deleted', {
    subscriptionId: subscription.id,
    customerId: subscription.customer,
    status: subscription.status,
  });

  try {
    // Get existing subscription to find tenant ID for cache invalidation
    const existingSubscription = await getSubscriptionByStripeId(subscription.id);

    // Update the subscription with canceled/ended dates
    const updateData = mapStripeSubscriptionToUpdateData(subscription);
    const success = await updateSubscriptionByStripeId(subscription.id, updateData);

    if (!success) {
      logger.warn(
        'Failed to update subscription deletion in database - subscription may not exist',
        {
          subscriptionId: subscription.id,
        }
      );
    } else {
      logger.info('Successfully marked subscription as deleted', {
        subscriptionId: subscription.id,
        status: subscription.status,
      });

      // Invalidate billing limits cache since subscription was deleted
      if (existingSubscription) {
        await invalidateBillingCache(existingSubscription.tenant_id);
      }
    }
  } catch (error) {
    logger.error('Error marking subscription as deleted in database', {
      subscriptionId: subscription.id,
      error: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}

async function handlePaymentSucceeded(invoice: Stripe.Invoice): Promise<void> {
  logger.info('Payment succeeded', {
    invoiceId: invoice.id,
    amount: invoice.amount_paid,
  });

  // TODO: Implement database update logic for successful payment
}

async function handlePaymentFailed(invoice: Stripe.Invoice): Promise<void> {
  logger.info('Payment failed', {
    invoiceId: invoice.id,
    amount: invoice.amount_due,
  });

  // TODO: Implement database update logic for failed payment
}

async function handleTrialWillEnd(subscription: Stripe.Subscription): Promise<void> {
  logger.info('Trial will end', {
    subscriptionId: subscription.id,
    customerId: subscription.customer,
    status: subscription.status,
    ...extractTrialDates(subscription),
  });

  // Update subscription with current trial information
  try {
    const updateData = mapStripeSubscriptionToUpdateData(subscription);
    const success = await updateSubscriptionByStripeId(subscription.id, updateData);

    if (!success) {
      logger.warn('Failed to update subscription with trial information', {
        subscriptionId: subscription.id,
      });
    } else {
      logger.info('Successfully updated subscription trial information', {
        subscriptionId: subscription.id,
      });
    }
  } catch (error) {
    logger.error('Error updating subscription with trial information', {
      subscriptionId: subscription.id,
      error: error instanceof Error ? error.message : 'Unknown error',
    });
  }
}

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

export { webhooksRouter };
