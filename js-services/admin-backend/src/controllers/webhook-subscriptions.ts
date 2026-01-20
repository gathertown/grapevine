import { Router, Request, Response } from 'express';
import crypto from 'crypto';
import { z } from 'zod';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { dbMiddleware } from '../middleware/db-middleware.js';
import { logger } from '../utils/logger.js';
import { getGrapevineEnv } from '@corporate-context/backend-common';

const webhookSubscriptionsRouter = Router();

// Apply database middleware to all routes
webhookSubscriptionsRouter.use(dbMiddleware);

// Validation schemas
const CreateWebhookSubscriptionSchema = z.object({
  url: z.string().url('Invalid webhook URL format'),
});

const UpdateWebhookSubscriptionSchema = z.object({
  active: z.boolean().optional(),
});

// Types for better type safety
interface WebhookSubscription {
  id: string;
  url: string;
  active: boolean;
  created_at: Date;
  updated_at: Date;
  created_by: string;
}

interface WebhookSubscriptionWithSecret extends WebhookSubscription {
  secret: string; // Only included in create response
}

/**
 * Generate a cryptographically secure webhook secret
 * Format: wh_ + 20 random alphanumeric characters
 */
function generateWebhookSecret(): string {
  const randomBytes = crypto.randomBytes(15); // 15 bytes = 20 base64url chars
  const randomString = randomBytes.toString('base64url').substring(0, 20);
  return `wh_${randomString}`;
}

/**
 * Validate webhook URL for security
 */
function validateWebhookUrl(url: string): { valid: boolean; error?: string } {
  try {
    const parsedUrl = new URL(url);

    // Must use HTTPS in production
    const grapevineEnv = getGrapevineEnv();
    if (grapevineEnv === 'production' && parsedUrl.protocol !== 'https:') {
      return { valid: false, error: 'Webhook URL must use HTTPS in production' };
    }

    // Allow localhost and http for development
    if (grapevineEnv !== 'production') {
      if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
        return { valid: false, error: 'Webhook URL must use HTTP or HTTPS' };
      }
    }

    // Block private IP addresses
    const hostname = parsedUrl.hostname.toLowerCase();
    if (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname.startsWith('10.') ||
      hostname.startsWith('192.168.') ||
      (hostname.startsWith('172.') &&
        parseInt(hostname.split('.')[1] || '0', 10) >= 16 &&
        parseInt(hostname.split('.')[1] || '0', 10) <= 31)
    ) {
      // Allow localhost only in development
      if (grapevineEnv === 'production') {
        return {
          valid: false,
          error: 'Private IP addresses and localhost are not allowed in production',
        };
      }
    }

    return { valid: true };
  } catch (error) {
    logger.error('Error validating webhook URL', {
      url,
      error: error instanceof Error ? error.message : 'Unknown error',
    });
    return { valid: false, error: 'Invalid URL format' };
  }
}

/**
 * GET /api/webhook-subscriptions
 * List all webhook subscriptions for the authenticated tenant
 */
webhookSubscriptionsRouter.get('/', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const query = `
      SELECT id, url, active, created_at, updated_at, created_by
      FROM webhook_subscriptions
      ORDER BY created_at DESC
    `;

    const result = await req.db.query(query);

    res.json({
      subscriptions: result.rows as WebhookSubscription[],
      count: result.rows.length,
    });
  } catch (error) {
    logger.error('Error fetching webhook subscriptions', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Failed to fetch webhook subscriptions' });
  }
});

/**
 * GET /api/webhook-subscriptions/:id
 * Get a specific webhook subscription by ID
 */
webhookSubscriptionsRouter.get('/:id', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const { id } = req.params;

    const query = `
      SELECT id, url, active, created_at, updated_at, created_by
      FROM webhook_subscriptions
      WHERE id = $1
    `;

    const result = await req.db.query(query, [id]);

    if (result.rows.length === 0) {
      return res.status(404).json({ error: 'Webhook subscription not found' });
    }

    res.json(result.rows[0] as WebhookSubscription);
  } catch (error) {
    logger.error('Error fetching webhook subscription', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      subscriptionId: req.params.id,
    });
    res.status(500).json({ error: 'Failed to fetch webhook subscription' });
  }
});

/**
 * POST /api/webhook-subscriptions
 * Create a new webhook subscription with auto-generated secret
 */
webhookSubscriptionsRouter.post('/', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    // Validate request body
    const parsed = CreateWebhookSubscriptionSchema.safeParse(req.body);
    if (!parsed.success) {
      const firstError = parsed.error.issues[0];
      return res.status(400).json({ error: firstError?.message || 'Invalid request body' });
    }

    const { url } = parsed.data;

    // Validate URL for security
    const urlValidation = validateWebhookUrl(url);
    if (!urlValidation.valid) {
      return res.status(400).json({ error: urlValidation.error });
    }

    // Check subscription limit (max 10 per tenant)
    const countQuery = 'SELECT COUNT(*) as count FROM webhook_subscriptions';
    const countResult = await req.db.query(countQuery);
    const currentCount = parseInt(countResult.rows[0].count, 10);

    if (currentCount >= 10) {
      return res.status(429).json({
        error: 'Maximum of 10 webhook subscriptions allowed per tenant',
      });
    }

    // Generate secure webhook secret
    const secret = generateWebhookSecret();

    // Insert subscription into database
    const insertQuery = `
      INSERT INTO webhook_subscriptions (url, secret, created_by)
      VALUES ($1, $2, $3)
      RETURNING id, url, active, created_at, updated_at, created_by
    `;

    // For now, we'll store the secret directly in the database
    // In a production system, this should be encrypted using the config system
    const insertResult = await req.db.query(insertQuery, [
      url,
      secret, // TODO: Encrypt this using the config system
      req.user?.email || 'unknown',
    ]);

    const subscription = insertResult.rows[0] as WebhookSubscription;

    // Return subscription with secret (only shown once)
    const response: WebhookSubscriptionWithSecret = {
      ...subscription,
      secret,
    };

    logger.info('Webhook subscription created', {
      tenantId,
      subscriptionId: subscription.id,
      url: subscription.url,
      createdBy: subscription.created_by,
    });

    res.status(201).json(response);
  } catch (error) {
    // Handle unique constraint violation (duplicate URL)
    if (error && typeof error === 'object' && 'code' in error && error.code === '23505') {
      return res.status(409).json({
        error: 'A webhook subscription already exists for this URL',
      });
    }

    logger.error('Error creating webhook subscription', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      url: req.body?.url,
    });
    res.status(500).json({ error: 'Failed to create webhook subscription' });
  }
});

/**
 * PUT /api/webhook-subscriptions/:id
 * Update a webhook subscription (currently only active status)
 */
webhookSubscriptionsRouter.put('/:id', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const { id } = req.params;

    // Validate request body
    const parsed = UpdateWebhookSubscriptionSchema.safeParse(req.body);
    if (!parsed.success) {
      const firstError = parsed.error.issues[0];
      return res.status(400).json({ error: firstError?.message || 'Invalid request body' });
    }

    const { active } = parsed.data;

    // Update subscription in a single operation
    let updateQuery = 'UPDATE webhook_subscriptions SET updated_at = CURRENT_TIMESTAMP';
    const values: (boolean | string | undefined)[] = [];
    let valueIndex = 1;

    if (active !== undefined) {
      updateQuery += `, active = $${valueIndex}`;
      values.push(active);
      valueIndex++;
    }

    updateQuery += ` WHERE id = $${valueIndex} RETURNING id, url, active, created_at, updated_at, created_by`;
    values.push(id);

    const updateResult = await req.db.query(updateQuery, values);

    if (updateResult.rows.length === 0) {
      return res.status(404).json({ error: 'Webhook subscription not found' });
    }

    const subscription = updateResult.rows[0] as WebhookSubscription;

    logger.info('Webhook subscription updated', {
      tenantId,
      subscriptionId: id,
      changes: { active },
    });

    res.json(subscription);
  } catch (error) {
    logger.error('Error updating webhook subscription', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      subscriptionId: req.params.id,
    });
    res.status(500).json({ error: 'Failed to update webhook subscription' });
  }
});

/**
 * DELETE /api/webhook-subscriptions/:id
 * Delete a webhook subscription
 */
webhookSubscriptionsRouter.delete('/:id', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'Tenant ID is required' });
    }

    if (!req.db) {
      return res.status(500).json({ error: 'Database connection unavailable' });
    }

    const { id } = req.params;

    const deleteQuery = `
      DELETE FROM webhook_subscriptions
      WHERE id = $1
      RETURNING id, url
    `;

    const deleteResult = await req.db.query(deleteQuery, [id]);

    if (deleteResult.rows.length === 0) {
      return res.status(404).json({ error: 'Webhook subscription not found' });
    }

    const deletedSubscription = deleteResult.rows[0];

    logger.info('Webhook subscription deleted', {
      tenantId,
      subscriptionId: id,
      url: deletedSubscription.url,
    });

    res.json({
      message: 'Webhook subscription deleted successfully',
      id: deletedSubscription.id,
    });
  } catch (error) {
    logger.error('Error deleting webhook subscription', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId: req.user?.tenantId,
      subscriptionId: req.params.id,
    });
    res.status(500).json({ error: 'Failed to delete webhook subscription' });
  }
});

export { webhookSubscriptionsRouter };
