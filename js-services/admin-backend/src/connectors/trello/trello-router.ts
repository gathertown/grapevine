import { Router } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { logger } from '../../utils/logger.js';
import { getConfigValue } from '../../config/index.js';
import { TRELLO_CONFIG_KEY_ACCESS_TOKEN, TRELLO_CONFIG_KEY_WEBHOOKS } from './trello-constants.js';

export const trelloRouter = Router();

/**
 * GET /api/trello/status
 * Check Trello integration status
 */
trelloRouter.get('/status', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const accessToken = await getConfigValue(TRELLO_CONFIG_KEY_ACCESS_TOKEN, tenantId);
    const webhooksConfig = await getConfigValue(TRELLO_CONFIG_KEY_WEBHOOKS, tenantId);

    let webhookInfo = null;
    if (typeof webhooksConfig === 'string' && webhooksConfig.length > 0) {
      try {
        const parsed = JSON.parse(webhooksConfig);
        webhookInfo = {
          webhook_id: parsed.webhook_id ?? null,
          member_id: parsed.member_id ?? null,
          member_username: parsed.member_username ?? null,
          created_at: parsed.created_at ?? null,
        };
      } catch (error) {
        logger.error('Failed to parse Trello webhook config', error);
      }
    }

    return res.json({
      configured: !!accessToken,
      access_token_present: !!accessToken,
      webhook_registered: !!webhookInfo,
      webhook_info: webhookInfo,
    });
  } catch (error) {
    logger.error('Failed to fetch Trello status', error);
    return res.status(500).json({ error: 'Failed to fetch Trello status' });
  }
});
