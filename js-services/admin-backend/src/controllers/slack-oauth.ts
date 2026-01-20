/* eslint-disable @typescript-eslint/no-explicit-any */
import { Router } from 'express';
import crypto from 'crypto';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { dbMiddleware } from '../middleware/db-middleware.js';
import { getConfigValue, saveConfigValue, deleteConfigValue } from '../config/index.js';
import { getSqsClient } from '../jobs/sqs-client.js';
import { logger } from '../utils/logger.js';
import { getFrontendUrl } from '../utils/config.js';
import { updateSlackBotStatus } from '../utils/notion-crm.js';
import { updateSlackbotConfigured } from '../services/marketing-hubspot/company.service.js';
import { ssmConfigManager } from '../config/ssm-config-manager.js';
import { getAnalyticsService } from '@corporate-context/backend-common';
import { installConnector, uninstallConnector } from '../dal/connector-utils.js';
import { ConnectorType } from '../types/connector.js';
import { ConnectorInstallationsRepository } from '../dal/connector-installations.js';

const slackOAuthRouter = Router();

// Helper functions for global Slack OAuth credentials
function getSlackClientId(): string | null {
  const value = process.env.SLACK_CLIENT_ID;
  if (!value) {
    logger.warn('SLACK_CLIENT_ID environment variable not configured');
    return null;
  }
  return value;
}

function getSlackAppId(): string | null {
  const value = process.env.SLACK_APP_ID;
  if (!value) {
    logger.warn('SLACK_APP_ID environment variable not configured');
    return null;
  }
  return value;
}

function getSlackClientSecret(): string | null {
  const value = process.env.SLACK_CLIENT_SECRET;
  if (!value) {
    logger.warn('SLACK_CLIENT_SECRET environment variable not configured');
    return null;
  }
  return value;
}

function getSlackSigningSecret(): string | null {
  const value = process.env.SLACK_SIGNING_SECRET;
  if (!value) {
    logger.warn('SLACK_SIGNING_SECRET environment variable not configured');
    return null;
  }
  return value;
}

/**
 * Check if tenant uses legacy per-tenant Slack app
 */
async function usesLegacySlackApp(tenantId: string): Promise<boolean> {
  const clientId = await getConfigValue('SLACK_CLIENT_ID', tenantId);
  return !!clientId;
}

// Required scopes for Slack bot
const SLACK_SCOPES = [
  'channels:join',
  'channels:history',
  'channels:read',
  'chat:write.public',
  'chat:write',
  'groups:read',
  'reactions:read',
  'reactions:write',
  'im:read',
  'team:read',
  'users:read',
  'users:read.email',
  'users.profile:read',
  'im:history',
  'im:write',
  'files:read',
  'groups:history',
  'mpim:history',
  'mpim:read',
].join(',');

/**
 * GET /api/slack/install
 * Get OAuth URL for starting Slack authorization flow
 * Supports both centralized OAuth (new) and per-tenant apps (legacy)
 */
slackOAuthRouter.get('/install', requireAdmin, dbMiddleware, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    let clientId: string | null = null;
    let clientSecret: string | null = null;
    let isLegacy = false;

    // Check if tenant uses legacy per-tenant app
    const legacyClientIdRaw = await getConfigValue('SLACK_CLIENT_ID', tenantId);
    if (legacyClientIdRaw && typeof legacyClientIdRaw === 'string') {
      // Legacy per-tenant app
      const legacyClientSecretRaw = await getConfigValue('SLACK_CLIENT_SECRET', tenantId);
      clientId = legacyClientIdRaw;
      clientSecret = typeof legacyClientSecretRaw === 'string' ? legacyClientSecretRaw : null;
      isLegacy = true;
      logger.info('Using legacy per-tenant Slack app credentials', { tenant_id: tenantId });
    } else {
      // New centralized OAuth app
      clientId = getSlackClientId();
      clientSecret = getSlackClientSecret();
      logger.info('Using centralized Slack OAuth app credentials', { tenant_id: tenantId });
    }

    if (!clientId || !clientSecret) {
      logger.error('Missing Slack OAuth credentials', {
        tenant_id: tenantId,
        is_legacy: isLegacy,
        has_client_id: !!clientId,
        has_client_secret: !!clientSecret,
      });
      return res.status(400).json({
        error:
          'Slack OAuth credentials not configured. Please configure Client ID and Client Secret first.',
      });
    }

    // Generate CSRF state token with tenant ID
    const state = `${crypto.randomUUID()}_${tenantId}`;

    // Get redirect URI from FRONTEND_URL
    const frontendUrl = getFrontendUrl();
    const redirectUri = `${frontendUrl}/api/slack/oauth/callback`;

    logger.info('Slack OAuth redirect URI', {
      tenant_id: tenantId,
      redirect_uri: redirectUri,
    });

    // Construct Slack authorization URL
    const authUrl = new URL('https://slack.com/oauth/v2/authorize');
    authUrl.searchParams.set('client_id', clientId);
    authUrl.searchParams.set('scope', SLACK_SCOPES);
    authUrl.searchParams.set('redirect_uri', redirectUri);
    authUrl.searchParams.set('state', state);

    logger.info('Generated Slack OAuth URL', {
      tenant_id: tenantId,
      redirect_uri: redirectUri,
      is_legacy: isLegacy,
    });

    // Return OAuth URL as JSON
    res.json({ url: authUrl.toString() });
  } catch (error) {
    logger.error('Error generating Slack OAuth URL', {
      error,
      tenant_id: tenantId,
    });
    res.status(500).json({ error: 'Failed to start OAuth flow' });
  }
});

/**
 * GET /api/slack/oauth/callback
 * Handle OAuth callback from Slack
 */
slackOAuthRouter.get('/oauth/callback', dbMiddleware, async (req, res) => {
  const frontendUrl = getFrontendUrl();
  const { code, state, error, error_description } = req.query;

  // Extract tenant ID from state parameter
  const tenantId = state ? String(state).split('_')[1] : undefined;

  if (error) {
    logger.error('Slack OAuth error from provider', {
      error: String(error),
      error_description: String(error_description || 'No description provided'),
      tenant_id: tenantId,
    });
    return res.redirect(
      `${frontendUrl}/slack/oauth/complete?error=${encodeURIComponent(String(error_description || error))}`
    );
  }

  if (!code || !state || !tenantId) {
    logger.error('Missing required OAuth callback parameters', {
      has_code: !!code,
      has_state: !!state,
      has_tenant_id: !!tenantId,
      tenant_id: tenantId,
    });
    return res.redirect(`${frontendUrl}/slack/oauth/complete?error=Missing required parameters`);
  }

  try {
    await exchangeCodeForTokens(String(code), tenantId);
    logger.info('Slack OAuth flow completed successfully', { tenant_id: tenantId });
    return res.redirect(`${frontendUrl}/slack/oauth/complete?success=true`);
  } catch (error) {
    logger.error('Error in Slack OAuth callback', {
      error: error instanceof Error ? error.message : String(error),
      error_stack: error instanceof Error ? error.stack : undefined,
      tenant_id: tenantId,
    });
    const errorMessage = error instanceof Error ? error.message : 'OAuth exchange failed';
    return res.redirect(
      `${frontendUrl}/slack/oauth/complete?error=${encodeURIComponent(errorMessage)}`
    );
  }
});

/**
 * Exchange authorization code for tokens and store them
 * Supports both centralized OAuth (new) and per-tenant apps (legacy)
 */
async function exchangeCodeForTokens(code: string, tenantId: string): Promise<void> {
  logger.info('Exchanging Slack authorization code', {
    tenant_id: tenantId,
  });

  let clientId: string | null = null;
  let clientSecret: string | null = null;
  let isLegacy = false;

  // Check if tenant uses legacy per-tenant app
  const legacyClientIdRaw = await getConfigValue('SLACK_CLIENT_ID', tenantId);
  if (legacyClientIdRaw && typeof legacyClientIdRaw === 'string') {
    // Legacy per-tenant app
    const legacyClientSecretRaw = await getConfigValue('SLACK_CLIENT_SECRET', tenantId);
    clientId = legacyClientIdRaw;
    clientSecret = typeof legacyClientSecretRaw === 'string' ? legacyClientSecretRaw : null;
    isLegacy = true;
    logger.info('Using legacy per-tenant Slack app credentials for token exchange', {
      tenant_id: tenantId,
    });
  } else {
    // New centralized OAuth app
    clientId = getSlackClientId();
    clientSecret = getSlackClientSecret();
    logger.info('Using centralized Slack OAuth app credentials for token exchange', {
      tenant_id: tenantId,
      has_client_id: !!clientId,
      has_client_secret: !!clientSecret,
      client_id_length: clientId?.length || 0,
    });
  }

  if (!clientId || !clientSecret) {
    const missingCreds = [];
    if (!clientId) missingCreds.push('SLACK_CLIENT_ID');
    if (!clientSecret) missingCreds.push('SLACK_CLIENT_SECRET');
    throw new Error(`Missing Slack OAuth credentials: ${missingCreds.join(', ')}`);
  }

  // Construct the redirect URI (must match the one used in authorization)
  const frontendUrl = getFrontendUrl();
  const redirectUri = `${frontendUrl}/api/slack/oauth/callback`;

  // Exchange code for tokens
  const response = await fetch('https://slack.com/api/oauth.v2.access', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      code,
      redirect_uri: redirectUri,
    }),
  });

  const data = await response.json();

  if (!response.ok || !data.ok) {
    const errorMsg = `Slack OAuth failed: ${data.error || 'Unknown error'}${data.error_description ? ` - ${data.error_description}` : ''}`;

    // Log to console as fallback
    console.error('Slack OAuth token exchange failed:', {
      tenant_id: tenantId,
      error_code: data.error,
      error_description: data.error_description,
      status: response.status,
      response_ok: data.ok,
      full_response: data,
    });

    logger.error('Slack OAuth token exchange failed', {
      tenant_id: tenantId,
      error_code: data.error,
      error_description: data.error_description,
      status: response.status,
      response_ok: data.ok,
      full_response: JSON.stringify(data),
    });
    throw new Error(errorMsg);
  }

  logger.info('Slack tokens received successfully', {
    tenant_id: tenantId,
    team_id: data.team?.id,
    team_name: data.team?.name,
    user_id: data.authed_user?.id,
    bot_user_id: data.bot_user_id,
    is_legacy: isLegacy,
  });

  // Fetch team info to get domain (not included in oauth.v2.access response)
  let teamDomain = '';
  try {
    const teamInfoResponse = await fetch('https://slack.com/api/team.info', {
      headers: {
        Authorization: `Bearer ${data.access_token}`,
      },
    });
    const teamInfo = await teamInfoResponse.json();
    if (teamInfo.ok && teamInfo.team?.domain) {
      teamDomain = teamInfo.team.domain;
      logger.info('Fetched team domain from team.info', {
        tenant_id: tenantId,
        domain: teamDomain,
      });
    } else {
      logger.warn('Failed to fetch team domain from team.info', {
        tenant_id: tenantId,
        team_info_response: JSON.stringify(teamInfo),
      });
    }
  } catch (error) {
    logger.error('Error fetching team info', {
      error: error instanceof Error ? error.message : String(error),
      tenant_id: tenantId,
    });
  }

  // Store bot token, installer user ID, team domain, and team name
  await Promise.all([
    saveConfigValue('SLACK_BOT_TOKEN', data.access_token, tenantId),
    saveConfigValue('SLACK_INSTALLER_USER_ID', data.authed_user?.id || '', tenantId),
    saveConfigValue('SLACK_TEAM_DOMAIN', teamDomain, tenantId),
    saveConfigValue('SLACK_TEAM_NAME', data.team?.name || '', tenantId),
  ]);

  logger.info('Slack tokens saved successfully', {
    tenant_id: tenantId,
    installer_user_id: data.authed_user?.id,
  });

  // For centralized OAuth, save installation mapping to control DB and copy signing secret to SSM
  if (!isLegacy) {
    const teamId = data.team?.id;
    const botUserId = data.bot_user_id || '';
    const installerUserId = data.authed_user?.id || '';

    if (teamId) {
      // Check if team is already installed for a different tenant
      const connectorsRepo = new ConnectorInstallationsRepository();
      const existingConnectorInstallation = await connectorsRepo.getByTypeAndExternalId(
        ConnectorType.Slack,
        teamId
      );
      if (existingConnectorInstallation && existingConnectorInstallation.tenant_id !== tenantId) {
        logger.error('Slack team already installed for different tenant', {
          teamId,
          requestingTenantId: tenantId,
          existingTenantId: existingConnectorInstallation.tenant_id,
        });
        throw new Error(
          'This Slack workspace is already connected to another organization. Please disconnect it from the other organization before connecting it here.'
        );
      }

      // Create or update connector record
      await installConnector({
        tenantId,
        type: ConnectorType.Slack,
        externalId: teamId,
        externalMetadata: {
          team_name: data.team?.name,
          team_domain: teamDomain,
          bot_user_id: botUserId,
          installer_user_id: installerUserId,
        },
        updateMetadataOnExisting: true,
      });
      logger.info('Saved Slack connector installation', {
        tenantId,
        teamId,
        botUserId,
        installerUserId,
      });
    } else {
      logger.warn('No team ID in Slack OAuth response', { tenantId });
    }

    // Copy global signing secret to tenant's SSM
    const globalSigningSecret = getSlackSigningSecret();
    if (globalSigningSecret) {
      const signingSaved = await ssmConfigManager.saveConfigValue(
        'SLACK_SIGNING_SECRET',
        globalSigningSecret,
        tenantId
      );
      if (signingSaved) {
        logger.info('Saved Slack signing secret to tenant SSM', { tenantId });
      } else {
        logger.warn('Failed to save Slack signing secret to tenant SSM', { tenantId });
      }
    } else {
      logger.warn('SLACK_SIGNING_SECRET not configured in environment', { tenantId });
    }
  }

  // Update Notion CRM - Slack bot configured
  await updateSlackBotStatus(tenantId, true);

  // Update HubSpot - Slackbot configured (fire and forget)
  updateSlackbotConfigured(tenantId, true).catch((error) => {
    logger.warn('Failed to update Slackbot status in HubSpot', { error, tenantId });
  });

  // Track slackbot_setup_complete event
  try {
    const analyticsService = getAnalyticsService();

    if (analyticsService) {
      await analyticsService.trackEvent('slackbot_setup_complete', {
        tenant_id: tenantId,
      });

      logger.info('Tracked slackbot_setup_complete event', {
        tenant_id: tenantId,
      });
    }
  } catch (error) {
    logger.error('Error tracking slackbot_setup_complete event', {
      error: error instanceof Error ? error.message : String(error),
      tenant_id: tenantId,
    });
  }

  // Send welcome message immediately
  try {
    const sqsClient = getSqsClient();
    await sqsClient.sendSlackBotWelcomeMessage(tenantId);
    logger.info('Welcome message sent', {
      tenant_id: tenantId,
    });
  } catch (error) {
    logger.error('Failed to send welcome message', error, {
      tenant_id: tenantId,
    });
    // Don't throw - we don't want to fail OAuth if welcome message fails
  }
}

/**
 * GET /api/slack/channels
 * Fetch all Slack channels (public and private) that the bot has access to
 */
slackOAuthRouter.get('/channels', requireAdmin, dbMiddleware, async (req, res) => {
  const allChannels: Array<{ id: string; name: string }> = [];
  let cursor: string | undefined;

  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant ID found' });
    }

    const botToken = await getConfigValue('SLACK_BOT_TOKEN', tenantId);
    if (!botToken) {
      return res.status(400).json({ error: 'Slack bot not configured' });
    }

    // Paginate through all channels
    do {
      const params = new URLSearchParams({
        types: 'public_channel,private_channel',
        exclude_archived: 'true',
        limit: '1000',
      });
      if (cursor) {
        params.set('cursor', cursor);
      }

      const response = await fetch(
        `https://slack.com/api/users.conversations?${params.toString()}`,
        {
          method: 'GET',
          headers: {
            Authorization: `Bearer ${botToken}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (!response.ok) {
        const errorText = await response.text();

        const errorData = {
          status: response.status,
          statusText: response.statusText,
          responseBody: errorText,
          tenantId,
          cursor,
          channelsFetchedSoFar: allChannels.length,
        };
        logger.error(`Failed to fetch Slack channels - HTTP error ${JSON.stringify(errorData)}`);
        return res.status(500).json({ error: 'Failed to fetch Slack channels', ...errorData });
      }

      const data = await response.json();

      if (!data.ok) {
        logger.error('Slack API error when fetching channels', {
          error: data.error,
          warning: data.warning,
          tenantId,
          cursor,
          channelsFetchedSoFar: allChannels.length,
        });
        return res.status(500).json({ error: `Slack API error: ${data.error}` });
      }

      if (data.channels) {
        const validChannels = data.channels
          .filter((ch: any) => ch.id && ch.name)
          .map((ch: any) => ({ id: ch.id, name: ch.name }));
        allChannels.push(...validChannels);
      }

      cursor = data.response_metadata?.next_cursor;
    } while (cursor);

    return res.json({ channels: allChannels });
  } catch (error) {
    logger.error('Failed to fetch Slack channels', error, {
      tenantId: req.user?.tenantId,
      channelsFetchedSoFar: allChannels.length,
      cursor,
      errorMessage: error instanceof Error ? error.message : String(error),
      errorStack: error instanceof Error ? error.stack : undefined,
    });
    return res.status(500).json({ error: 'Failed to fetch Slack channels' });
  }
});

/**
 * DELETE /api/slack/disconnect
 * Disconnect Slack workspace from tenant
 */
slackOAuthRouter.delete('/disconnect', requireAdmin, dbMiddleware, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found' });
  }

  try {
    logger.info('Disconnecting Slack workspace', { tenantId });

    // Delete all Slack configuration values
    const configKeys = [
      'SLACK_BOT_TOKEN',
      'SLACK_CLIENT_ID',
      'SLACK_CLIENT_SECRET',
      'SLACK_INSTALLER_USER_ID',
      'SLACK_TEAM_DOMAIN',
      'SLACK_TEAM_NAME',
      'SLACK_BOT_NAME',
      'SLACK_BOT_QA_CHANNELS',
      'SLACK_BOT_GENERAL_CHANNELS',
      'SLACK_BOT_RESPOND_TO_QUESTIONS_AS_GENERAL',
      'SLACK_BOT_ANSWER_DMS',
      'SLACK_BOT_RESPOND_TO_ANSWERS_IN_SLACK',
      'SLACK_BOT_ANSWER_THREADS',
      'SLACK_ONBOARDING_THREAD_TS',
      'SLACK_ONBOARDING_CHANNEL_ID',
    ];

    await Promise.all(configKeys.map((key) => deleteConfigValue(key, tenantId)));

    // Delete from tenant SSM if using centralized OAuth
    const isLegacy = await usesLegacySlackApp(tenantId);
    if (!isLegacy) {
      await ssmConfigManager.deleteConfigValue('SLACK_SIGNING_SECRET', tenantId);
    }

    // Mark connector as disconnected
    await uninstallConnector(tenantId, ConnectorType.Slack);
    logger.info('Marked Slack connector as disconnected', { tenantId });

    // Update Notion CRM - Slack bot disconnected
    await updateSlackBotStatus(tenantId, false);

    // Update HubSpot - Slackbot disconnected (fire and forget)
    updateSlackbotConfigured(tenantId, false).catch((error) => {
      logger.warn('Failed to update Slackbot status in HubSpot', { error, tenantId });
    });

    // Track slackbot_disconnected event
    (async () => {
      try {
        const analyticsService = getAnalyticsService();
        if (analyticsService) {
          await analyticsService.trackEvent('slackbot_disconnected', {
            tenant_id: tenantId,
          });
          logger.info('Tracked slackbot_disconnected event', { tenant_id: tenantId });
        }
      } catch (error) {
        logger.error('Error tracking slackbot_disconnected event', {
          error: error instanceof Error ? error.message : String(error),
          tenant_id: tenantId,
        });
      }
    })();

    logger.info('Slack disconnected successfully', { tenantId });
    return res.json({ success: true });
  } catch (error) {
    logger.error('Failed to disconnect Slack', {
      error: error instanceof Error ? error.message : String(error),
      tenantId,
    });
    return res.status(500).json({ error: 'Failed to disconnect Slack workspace' });
  }
});

/**
 * GET /api/slack/app-info
 * Get Slack app information for the tenant
 * Returns whether tenant uses legacy app and the centralized app ID
 */
slackOAuthRouter.get('/app-info', requireAdmin, dbMiddleware, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found' });
  }

  try {
    const isLegacy = await usesLegacySlackApp(tenantId);
    const slackAppId = isLegacy ? null : getSlackAppId();
    const teamDomain = await getConfigValue('SLACK_TEAM_DOMAIN', tenantId);

    return res.json({
      isLegacy,
      slackAppId,
      teamDomain: typeof teamDomain === 'string' ? teamDomain : null,
    });
  } catch (error) {
    logger.error('Failed to get Slack app info', {
      error: error instanceof Error ? error.message : String(error),
      tenantId,
    });
    return res.status(500).json({ error: 'Failed to get Slack app info' });
  }
});

export { slackOAuthRouter, usesLegacySlackApp };
