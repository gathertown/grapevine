/**
 * Figma OAuth Router
 *
 * Handles OAuth authorization flow and connector management.
 */

import { Router } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { logger } from '../../utils/logger.js';
import { getFrontendUrl } from '../../utils/config.js';
import { FigmaService } from './figma-service.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { getConfigValue, deleteConfigValue } from '../../config/index.js';
import {
  FIGMA_CONFIG_KEYS,
  FIGMA_ACCESS_TOKEN_KEY,
  FIGMA_USER_ID_KEY,
  FIGMA_USER_EMAIL_KEY,
  FIGMA_USER_HANDLE_KEY,
} from './figma-config.js';
import { uninstallConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { ConnectorInstallationsRepository } from '../../dal/connector-installations.js';

const figmaRouter = Router();
const figmaService = new FigmaService();

const FIGMA_INTEGRATION_PATH = '/integrations/figma';

/**
 * GET /api/figma/install
 *
 * Returns the OAuth authorization URL for connecting Figma.
 * Requires admin authentication.
 */
figmaRouter.get('/install', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const authUrl = figmaService.buildOAuthUrl(tenantId);
    res.json({ url: authUrl });
  } catch (error) {
    logger.error('Failed to build Figma OAuth URL', error);
    return res.status(500).json({ error: 'Failed to build OAuth URL' });
  }
});

/**
 * GET /api/figma/oauth/callback
 *
 * OAuth callback handler for Figma.
 * Exchanges authorization code for access token and stores credentials.
 *
 * IMPORTANT: Figma auth codes expire in 30 seconds, so exchange must happen immediately!
 *
 * Query Parameters:
 * - code: Authorization code from Figma
 * - state: State parameter containing tenant ID (base64url encoded)
 * - error: Error code if authorization failed
 * - error_description: Human-readable error description
 */
figmaRouter.get('/oauth/callback', async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description } = req.query;

  // Parse tenant ID from state
  let tenantId: string | undefined;
  try {
    if (state) {
      const parsed = figmaService.parseOAuthState(String(state));
      tenantId = parsed.tenantId;
    }
  } catch {
    logger.error('Invalid Figma OAuth state', undefined, { state });
    return res.redirect(`${frontendUrl}${FIGMA_INTEGRATION_PATH}?error=invalid_state`);
  }

  if (error) {
    logger.error('Figma OAuth error from provider', undefined, {
      error: String(error),
      error_description: String(error_description || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}${FIGMA_INTEGRATION_PATH}?error=true`);
  }

  if (!code || !tenantId) {
    return res.redirect(`${frontendUrl}${FIGMA_INTEGRATION_PATH}?error=missing_params`);
  }

  try {
    await figmaService.exchangeCodeForTokens(String(code), tenantId);
    await handleFigmaConnected(tenantId);
    return res.redirect(`${frontendUrl}${FIGMA_INTEGRATION_PATH}?success=true`);
  } catch (err) {
    logger.error('Error in Figma OAuth callback', err);
    return res.redirect(`${frontendUrl}${FIGMA_INTEGRATION_PATH}?error=true`);
  }
});

/**
 * Handle post-OAuth connection tasks
 * - Register webhooks for previously selected teams (reconnection scenario)
 * - Trigger initial data backfill via SQS
 */
async function handleFigmaConnected(tenantId: string): Promise<void> {
  try {
    logger.info('Figma OAuth successful, triggering initial ingest', { tenant_id: tenantId });

    // Check if there are previously selected teams (reconnection scenario)
    // If so, register webhooks for them
    const connectorRepo = new ConnectorInstallationsRepository();
    const connector = await connectorRepo.getByTenantAndType(tenantId, ConnectorType.Figma);

    if (connector?.external_metadata?.selected_team_ids) {
      const selectedTeamIds = connector.external_metadata.selected_team_ids as string[];
      if (selectedTeamIds.length > 0) {
        logger.info('Found previously selected teams, registering webhooks', {
          tenant_id: tenantId,
          team_count: selectedTeamIds.length,
        });

        const allWebhookIds: string[] = [];
        for (const teamId of selectedTeamIds) {
          try {
            const webhookIds = await figmaService.registerWebhooksForTeam(tenantId, teamId);
            allWebhookIds.push(...webhookIds);
          } catch (error) {
            logger.error(
              'Failed to register webhooks for team during reconnection',
              error instanceof Error ? error : new Error(String(error)),
              {
                tenant_id: tenantId,
                team_id: teamId,
              }
            );
          }
        }

        // Update webhook IDs in metadata
        if (allWebhookIds.length > 0) {
          const updatedMetadata = {
            ...connector.external_metadata,
            webhook_ids: allWebhookIds,
          };
          await connectorRepo.updateMetadata(connector.id, updatedMetadata);
          logger.info('Registered webhooks for previously selected teams', {
            tenant_id: tenantId,
            webhook_count: allWebhookIds.length,
          });
        }
      }
    }

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering Figma backfill job', { tenant_id: tenantId });
      await sqsClient.sendFigmaBackfillIngestJob(tenantId);
      logger.info('Figma backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.warn('SQS not configured - skipping Figma backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Failed to handle Figma connection', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the OAuth flow if post-processing fails
  }
}

/**
 * GET /api/figma/status
 * Check Figma integration status
 */
figmaRouter.get('/status', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    // Use unified config manager - it auto-routes to SSM for sensitive keys
    const accessToken = await getConfigValue(FIGMA_ACCESS_TOKEN_KEY, tenantId);
    const userId = await getConfigValue(FIGMA_USER_ID_KEY, tenantId);
    const userEmail = await getConfigValue(FIGMA_USER_EMAIL_KEY, tenantId);
    const userHandle = await getConfigValue(FIGMA_USER_HANDLE_KEY, tenantId);

    return res.json({
      connected: !!accessToken,
      configured: !!accessToken,
      access_token_present: !!accessToken,
      user_id: userId || null,
      user_email: userEmail || null,
      user_handle: userHandle || null,
    });
  } catch (error) {
    logger.error('Failed to fetch Figma status', error);
    return res.status(500).json({ error: 'Failed to fetch Figma status' });
  }
});

/**
 * DELETE /api/figma/disconnect
 * Disconnect Figma integration by removing all config keys and webhooks
 */
figmaRouter.delete('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    // Get existing webhooks to delete them
    const connectorRepo = new ConnectorInstallationsRepository();
    const connector = await connectorRepo.getByTenantAndType(tenantId, ConnectorType.Figma);

    // Delete webhooks if any exist
    if (connector?.external_metadata?.webhook_ids) {
      const webhookIds = connector.external_metadata.webhook_ids as string[];
      logger.info('Deleting Figma webhooks', {
        tenant_id: tenantId,
        webhook_count: webhookIds.length,
      });
      await figmaService.deleteWebhooks(tenantId, webhookIds);
    }

    // Delete all Figma config keys using unified config manager
    // Sensitive keys auto-route to SSM, non-sensitive to DB
    await Promise.all(FIGMA_CONFIG_KEYS.map((key) => deleteConfigValue(key, tenantId)));

    // Mark connector as disconnected
    await uninstallConnector(tenantId, ConnectorType.Figma);

    logger.info('Disconnected Figma', { tenant_id: tenantId });
    return res.json({ success: true });
  } catch (error) {
    logger.error('Error disconnecting Figma', error);
    return res.status(500).json({ error: 'Failed to disconnect Figma' });
  }
});

/**
 * POST /api/figma/refresh-token
 * Manually refresh the Figma access token
 */
figmaRouter.post('/refresh-token', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    await figmaService.refreshAccessToken(tenantId);
    return res.json({ success: true });
  } catch (error) {
    logger.error('Failed to refresh Figma token', error);
    return res.status(500).json({ error: 'Failed to refresh token' });
  }
});

/**
 * GET /api/figma/teams
 * Get selected team IDs from connector_installations.external_metadata
 */
figmaRouter.get('/teams', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    const connectorRepo = new ConnectorInstallationsRepository();
    const connector = await connectorRepo.getByTenantAndType(tenantId, ConnectorType.Figma);

    if (!connector) {
      return res.json({ team_ids: [] });
    }

    const teamIds = (connector.external_metadata?.selected_team_ids as string[]) || [];
    return res.json({ team_ids: teamIds });
  } catch (error) {
    logger.error('Failed to get Figma team IDs', error);
    return res.status(500).json({ error: 'Failed to get team IDs' });
  }
});

/**
 * POST /api/figma/teams
 * Save selected team IDs to connector_installations.external_metadata and trigger backfill.
 * Only triggers backfill for newly added teams (not already synced).
 */
figmaRouter.post('/teams', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  const { team_ids } = req.body;
  if (!Array.isArray(team_ids)) {
    return res.status(400).json({ error: 'team_ids must be an array' });
  }

  // Validate team IDs (should be numeric strings)
  const validTeamIds = team_ids
    .filter((id) => typeof id === 'string' && id.trim() && /^\d+$/.test(id.trim()))
    .map((id) => id.trim());

  try {
    const connectorRepo = new ConnectorInstallationsRepository();
    const connector = await connectorRepo.getByTenantAndType(tenantId, ConnectorType.Figma);

    if (!connector) {
      return res
        .status(404)
        .json({ error: 'Figma connector not found. Please connect Figma first.' });
    }

    // Get already synced team IDs from external_metadata
    const syncedTeamIds = (connector.external_metadata?.synced_team_ids as string[]) || [];

    // Determine which teams are new (not yet synced)
    const newTeamIds = validTeamIds.filter((id) => !syncedTeamIds.includes(id));

    // Update external_metadata with selected team IDs
    const updatedMetadata = {
      ...connector.external_metadata,
      selected_team_ids: validTeamIds,
    };
    await connectorRepo.updateMetadata(connector.id, updatedMetadata);

    logger.info('Updated Figma team IDs in external_metadata', {
      tenant_id: tenantId,
      connector_id: connector.id,
      selected_team_ids: validTeamIds,
      new_team_ids: newTeamIds,
      synced_team_ids: syncedTeamIds,
    });

    // Only trigger backfill for new teams (not already synced)
    if (newTeamIds.length > 0 && isSqsConfigured()) {
      const sqsClient = getSqsClient();
      await sqsClient.sendFigmaBackfillIngestJob(tenantId, newTeamIds);
      logger.info('Triggered Figma backfill for new teams only', {
        tenant_id: tenantId,
        new_team_ids: newTeamIds,
      });
    } else if (newTeamIds.length === 0 && validTeamIds.length > 0) {
      logger.info('No new teams to sync - all selected teams already synced', {
        tenant_id: tenantId,
        synced_team_ids: syncedTeamIds,
      });
    }

    // Register webhooks for all selected teams
    // The service handles deduplication - it checks existing webhooks by endpoint URL
    // and only creates new ones if needed
    const allWebhookIds: string[] = [];

    for (const teamId of validTeamIds) {
      try {
        const webhookIds = await figmaService.registerWebhooksForTeam(tenantId, teamId);
        allWebhookIds.push(...webhookIds);
      } catch (error) {
        // Log error but don't fail the request - webhooks are optional
        logger.error(
          'Failed to register Figma webhooks for team',
          error instanceof Error ? error : new Error(String(error)),
          {
            tenant_id: tenantId,
            team_id: teamId,
          }
        );
      }
    }

    // Store webhook IDs in metadata
    if (allWebhookIds.length > 0) {
      const metadataWithWebhooks = {
        ...connector.external_metadata,
        selected_team_ids: validTeamIds,
        webhook_ids: allWebhookIds,
      };
      await connectorRepo.updateMetadata(connector.id, metadataWithWebhooks);
    }

    return res.json({
      success: true,
      team_ids: validTeamIds,
      new_team_ids: newTeamIds,
      already_synced_team_ids: syncedTeamIds.filter((id) => validTeamIds.includes(id)),
      webhook_count: allWebhookIds.length,
    });
  } catch (error) {
    logger.error('Failed to set Figma team IDs', error);
    return res.status(500).json({ error: 'Failed to set team IDs' });
  }
});

export { figmaRouter };
