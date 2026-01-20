/**
 * Subscription Data Access Layer (DAL)
 *
 * Handles all database operations related to subscriptions table
 */

import { logger, LogContext } from '../utils/logger.js';
import { getControlDbPool } from '../control-db.js';
import Stripe from 'stripe';

export interface SubscriptionRecord {
  id: string;
  tenant_id: string;
  stripe_customer_id: string;
  stripe_subscription_id: string;
  stripe_product_id: string;
  stripe_price_id: string;
  workos_user_id: string | null;
  status: string;
  start_date: Date;
  billing_cycle_anchor: Date;
  cancel_at: Date | null;
  canceled_at: Date | null;
  ended_at: Date | null;
  trial_start: Date | null;
  trial_end: Date | null;
  created_at: Date;
  updated_at: Date;
}

export interface CreateSubscriptionData {
  tenant_id: string;
  stripe_customer_id: string;
  stripe_subscription_id: string;
  stripe_product_id: string;
  stripe_price_id: string;
  workos_user_id?: string | null;
  status: string;
  start_date: Date;
  billing_cycle_anchor: Date;
  cancel_at?: Date | null;
  canceled_at?: Date | null;
  ended_at?: Date | null;
  trial_start?: Date | null;
  trial_end?: Date | null;
}

export interface UpdateSubscriptionData {
  stripe_product_id?: string;
  stripe_price_id?: string;
  status?: string;
  billing_cycle_anchor?: Date;
  cancel_at?: Date | null;
  canceled_at?: Date | null;
  ended_at?: Date | null;
  trial_start?: Date | null;
  trial_end?: Date | null;
}

/**
 * Create a new subscription record
 */
export async function createSubscription(data: CreateSubscriptionData): Promise<boolean> {
  return LogContext.run(
    {
      operation: 'create-subscription',
      stripeSubscriptionId: data.stripe_subscription_id,
      tenantId: data.tenant_id,
    },
    async () => {
      const pool = getControlDbPool();
      if (!pool) {
        logger.error('Control database not available for subscription creation');
        return false;
      }

      try {
        await pool.query(
          `INSERT INTO public.subscriptions (
          tenant_id, stripe_customer_id, stripe_subscription_id, stripe_product_id, stripe_price_id,
          workos_user_id, status, start_date, billing_cycle_anchor,
          cancel_at, canceled_at, ended_at, trial_start, trial_end, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, now(), now())`,
          [
            data.tenant_id,
            data.stripe_customer_id,
            data.stripe_subscription_id,
            data.stripe_product_id,
            data.stripe_price_id,
            data.workos_user_id || null,
            data.status,
            data.start_date,
            data.billing_cycle_anchor,
            data.cancel_at || null,
            data.canceled_at || null,
            data.ended_at || null,
            data.trial_start || null,
            data.trial_end || null,
          ]
        );

        logger.info(`✅ Created subscription record`, {
          stripeSubscriptionId: data.stripe_subscription_id,
          tenantId: data.tenant_id,
          status: data.status,
        });
        return true;
      } catch (error) {
        logger.error('Failed to create subscription record', {
          error: error instanceof Error ? error.message : 'Unknown error',
          stripeSubscriptionId: data.stripe_subscription_id,
        });
        return false;
      }
    }
  );
}

/**
 * Update an existing subscription record by stripe_subscription_id
 */
export async function updateSubscriptionByStripeId(
  stripeSubscriptionId: string,
  data: UpdateSubscriptionData
): Promise<boolean> {
  return LogContext.run(
    {
      operation: 'update-subscription',
      stripeSubscriptionId,
    },
    async () => {
      const pool = getControlDbPool();
      if (!pool) {
        logger.error('Control database not available for subscription update');
        return false;
      }

      const updates: string[] = [];
      const values: Array<string | Date | null> = [];
      let paramIndex = 1;

      if (data.stripe_product_id !== undefined) {
        updates.push(`stripe_product_id = $${paramIndex++}`);
        values.push(data.stripe_product_id);
      }
      if (data.stripe_price_id !== undefined) {
        updates.push(`stripe_price_id = $${paramIndex++}`);
        values.push(data.stripe_price_id);
      }
      if (data.status !== undefined) {
        updates.push(`status = $${paramIndex++}`);
        values.push(data.status);
      }
      if (data.billing_cycle_anchor !== undefined) {
        updates.push(`billing_cycle_anchor = $${paramIndex++}`);
        values.push(data.billing_cycle_anchor);
      }
      if (data.cancel_at !== undefined) {
        updates.push(`cancel_at = $${paramIndex++}`);
        values.push(data.cancel_at);
      }
      if (data.canceled_at !== undefined) {
        updates.push(`canceled_at = $${paramIndex++}`);
        values.push(data.canceled_at);
      }
      if (data.ended_at !== undefined) {
        updates.push(`ended_at = $${paramIndex++}`);
        values.push(data.ended_at);
      }
      if (data.trial_start !== undefined) {
        updates.push(`trial_start = $${paramIndex++}`);
        values.push(data.trial_start);
      }
      if (data.trial_end !== undefined) {
        updates.push(`trial_end = $${paramIndex++}`);
        values.push(data.trial_end);
      }

      if (updates.length === 0) {
        logger.warn('No updates provided for subscription', { stripeSubscriptionId });
        return true;
      }

      updates.push(`updated_at = now()`);
      values.push(stripeSubscriptionId);

      try {
        const result = await pool.query(
          `UPDATE public.subscriptions 
         SET ${updates.join(', ')} 
         WHERE stripe_subscription_id = $${paramIndex}`,
          values
        );

        if (result.rowCount === 0) {
          logger.warn('No subscription found to update', { stripeSubscriptionId });
          return false;
        }

        logger.info(`✅ Updated subscription record`, {
          stripeSubscriptionId,
          updatedFields: Object.keys(data),
        });
        return true;
      } catch (error) {
        logger.error('Failed to update subscription record', {
          error: error instanceof Error ? error.message : 'Unknown error',
          stripeSubscriptionId,
        });
        return false;
      }
    }
  );
}

/**
 * Get subscription record by stripe_subscription_id
 */
export async function getSubscriptionByStripeId(
  stripeSubscriptionId: string
): Promise<SubscriptionRecord | null> {
  return LogContext.run(
    {
      operation: 'get-subscription',
      stripeSubscriptionId,
    },
    async () => {
      const pool = getControlDbPool();
      if (!pool) {
        logger.error('Control database not available for subscription lookup');
        return null;
      }

      try {
        const result = await pool.query(
          `SELECT * FROM public.subscriptions WHERE stripe_subscription_id = $1`,
          [stripeSubscriptionId]
        );

        if (result.rows.length > 0) {
          return result.rows[0] as SubscriptionRecord;
        }

        return null;
      } catch (error) {
        logger.error('Failed to get subscription record', {
          error: error instanceof Error ? error.message : 'Unknown error',
          stripeSubscriptionId,
        });
        return null;
      }
    }
  );
}

/**
 * Get subscriptions by tenant_id
 */
export async function getSubscriptionsByTenantId(tenantId: string): Promise<SubscriptionRecord[]> {
  return LogContext.run(
    {
      operation: 'get-subscriptions-by-tenant',
      tenantId,
    },
    async () => {
      const pool = getControlDbPool();
      if (!pool) {
        logger.error('Control database not available for subscription lookup');
        return [];
      }

      try {
        const result = await pool.query(
          `SELECT * FROM public.subscriptions WHERE tenant_id = $1 ORDER BY created_at DESC`,
          [tenantId]
        );

        return result.rows as SubscriptionRecord[];
      } catch (error) {
        logger.error('Failed to get subscriptions by tenant', {
          error: error instanceof Error ? error.message : 'Unknown error',
          tenantId,
        });
        return [];
      }
    }
  );
}

/**
 * Helper to convert Stripe subscription to our CreateSubscriptionData format
 */
export function mapStripeSubscriptionToCreateData(
  subscription: Stripe.Subscription,
  tenantId: string,
  workosUserId?: string | null
): CreateSubscriptionData {
  const productId =
    typeof subscription.items.data[0]?.price.product === 'string'
      ? subscription.items.data[0].price.product
      : subscription.items.data[0]?.price.product?.id || '';

  const priceId = subscription.items.data[0]?.price.id;

  if (!priceId) {
    throw new Error('Stripe subscription missing required price ID');
  }

  return {
    tenant_id: tenantId,
    stripe_customer_id:
      typeof subscription.customer === 'string'
        ? subscription.customer
        : subscription.customer?.id || '',
    stripe_subscription_id: subscription.id,
    stripe_product_id: productId,
    stripe_price_id: priceId,
    workos_user_id: workosUserId,
    status: subscription.status,
    start_date: new Date(subscription.start_date * 1000),
    billing_cycle_anchor: new Date(subscription.billing_cycle_anchor * 1000),
    cancel_at: subscription.cancel_at ? new Date(subscription.cancel_at * 1000) : null,
    canceled_at: subscription.canceled_at ? new Date(subscription.canceled_at * 1000) : null,
    ended_at: subscription.ended_at ? new Date(subscription.ended_at * 1000) : null,
    trial_start: subscription.trial_start ? new Date(subscription.trial_start * 1000) : null,
    trial_end: subscription.trial_end ? new Date(subscription.trial_end * 1000) : null,
  };
}

/**
 * Helper to convert Stripe subscription to our UpdateSubscriptionData format
 */
export function mapStripeSubscriptionToUpdateData(
  subscription: Stripe.Subscription
): UpdateSubscriptionData {
  const productId =
    typeof subscription.items.data[0]?.price.product === 'string'
      ? subscription.items.data[0].price.product
      : subscription.items.data[0]?.price.product?.id || '';

  const priceId = subscription.items.data[0]?.price.id;

  return {
    stripe_product_id: productId,
    stripe_price_id: priceId,
    status: subscription.status,
    billing_cycle_anchor: new Date(subscription.billing_cycle_anchor * 1000),
    cancel_at: subscription.cancel_at ? new Date(subscription.cancel_at * 1000) : null,
    canceled_at: subscription.canceled_at ? new Date(subscription.canceled_at * 1000) : null,
    ended_at: subscription.ended_at ? new Date(subscription.ended_at * 1000) : null,
    trial_start: subscription.trial_start ? new Date(subscription.trial_start * 1000) : null,
    trial_end: subscription.trial_end ? new Date(subscription.trial_end * 1000) : null,
  };
}
