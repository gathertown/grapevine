import { Router, Request, Response } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { dbMiddleware } from '../../middleware/db-middleware.js';
import { getConfigValue, saveConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { SSMClient } from '@corporate-context/backend-common';
import { randomUUID } from 'crypto';

const jiraRouter = Router();

/**
 * GET /api/jira/status
 * Check Jira integration status (based on Forge app installation and configuration completion)
 */
jiraRouter.get('/status', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    // Check all Jira configuration values
    const [cloudId, webtriggerUrl] = await Promise.all([
      getConfigValue('JIRA_CLOUD_ID', tenantId),
      getConfigValue('JIRA_WEBTRIGGER_BACKFILL_URL', tenantId),
    ]);

    // Check if Jira Forge app is installed (based on having cloud ID from the app)
    const isInstalled = !!cloudId;

    // Check if configuration is complete (has all required config values)
    const isFullyConfigured = !!(cloudId && webtriggerUrl);

    res.json({
      installed: isInstalled,
      type: isInstalled ? 'jira_app' : null,
      fully_configured: isFullyConfigured,
      message: isFullyConfigured
        ? 'Jira integration is fully configured and ready'
        : isInstalled
          ? 'Jira app installed but configuration incomplete'
          : 'Jira app not installed',
    });
  } catch (error) {
    logger.error('Error checking Jira status', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenant_id: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * POST /api/jira/save-site
 * Save Jira site URL for the tenant
 */
jiraRouter.post('/save-site', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const { siteUrl } = req.body;
    if (!siteUrl) {
      return res.status(400).json({ error: 'Site URL is required' });
    }

    // Save the Jira site URL for the tenant
    await saveConfigValue('JIRA_SITE_URL', siteUrl, tenantId);

    logger.info('Jira site URL saved successfully', {
      tenant_id: tenantId,
      site_url: siteUrl,
    });

    res.status(200).json({ success: true });
  } catch (error) {
    logger.error('Error saving Jira site URL', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenant_id: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * GET /api/jira/signing-secret
 * Get or generate Jira signing secret using the SSM client
 */
jiraRouter.get('/signing-secret', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const ssmClient = new SSMClient();

    // Try to get existing signing secret
    let signingSecret = await ssmClient.getSigningSecret(tenantId, 'jira');

    if (!signingSecret) {
      // Generate new signing secret if it doesn't exist
      const uuidStr = randomUUID().replace(/-/g, '');
      signingSecret = `${tenantId}-${uuidStr}`;

      // Store the new signing secret
      const success = await ssmClient.storeSigningSecret(tenantId, 'jira', signingSecret);

      if (!success) {
        logger.error('Failed to store new Jira signing secret', {
          tenant_id: tenantId,
        });
        return res.status(500).json({ error: 'Failed to generate signing secret' });
      }

      logger.info('Generated new Jira signing secret', {
        tenant_id: tenantId,
      });
    } else {
      logger.info('Retrieved existing Jira signing secret', {
        tenant_id: tenantId,
      });
    }

    res.status(200).json({ signingSecret });
  } catch (error) {
    logger.error('Error getting/generating Jira signing secret', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenant_id: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Failed to get signing secret' });
  }
});

// Apply database middleware to all routes
jiraRouter.use(dbMiddleware);

export { jiraRouter };
