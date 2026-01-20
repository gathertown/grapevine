import { Router, Request, Response } from 'express';
import { requireAdmin } from '../middleware/auth-middleware.js';
import {
  getConfigValue,
  saveConfigValue,
  deleteConfigValue,
  getAllConfigValues,
} from '../config/index.js';
import { getSqsClient, isSqsConfigured } from '../jobs/sqs-client.js';
import { logger } from '../utils/logger.js';
import { getAnalyticsService, GATHER_API_URL } from '@corporate-context/backend-common';
import { updateIntegrationStatus } from '../utils/notion-crm.js';
import {
  TRELLO_CONFIG_KEY_ACCESS_TOKEN,
  TRELLO_CONFIG_KEY_WEBHOOK_SECRET,
  TRELLO_INTEGRATION_NAME,
} from '../connectors/trello/trello-constants.js';
import { handleGitHubTokenSaved } from '../connectors/github/github-config.js';
import { installConnector, uninstallConnector } from '../dal/connector-utils.js';
import { ConnectorType } from '../types/connector.js';

const companyRouter = Router();

// In-memory storage for demo purposes
interface CompanyData {
  companyName?: string;
  createdAt?: string;
}
let companyData: CompanyData | null = null;

// Company information endpoints
companyRouter.post('/company', requireAdmin, async (req: Request, res: Response) => {
  try {
    const { companyName } = req.body;

    // Basic validation
    if (!companyName) {
      return res.status(400).json({
        error: 'Company name is required',
      });
    }

    // Get tenant ID from authenticated user
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for organization',
      });
    }

    // Save company data to memory (for backward compatibility)
    companyData = {
      companyName: companyName.trim(),
      createdAt: new Date().toISOString(),
    };

    // Save company name (automatically routed to database as non-sensitive)
    await saveConfigValue('COMPANY_NAME', companyName.trim(), tenantId)
      .then((success: boolean) => {
        if (success) {
          logger.info('Company name saved successfully');
        } else {
          logger.warn('Failed to save company name');
        }
      })
      .catch((_error: Error) => {
        logger.warn(
          'Config storage not accessible - company name only available in current session'
        );
      });

    logger.info('Company data saved', { companyData });

    res.json({
      success: true,
      message: 'Company information saved successfully',
      data: companyData,
    });
  } catch (error) {
    logger.error('Error saving company data', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

companyRouter.get('/company', requireAdmin, async (req: Request, res: Response) => {
  try {
    // Get tenant ID from authenticated user
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      // TODO: Decide if we should return empty data or error for missing tenant ID
      // For now, return empty data to avoid breaking frontend
      return res.json({
        success: true,
        data: {
          companyName: '',
          createdAt: null,
        },
      });
    }

    // Load company data (automatically routed from appropriate backends)
    const [companyName] = await Promise.all([getConfigValue('COMPANY_NAME', tenantId)]);

    // Build response data
    const responseData = {
      companyName: companyName || '',
      // Don't return the API key for security reasons
      createdAt: null, // TODO: Consider storing creation timestamp in SSM if needed
    };

    res.json({
      success: true,
      data: responseData,
    });
  } catch (error) {
    logger.error('Error getting company data from SSM', error);
    // Return empty data on error to avoid breaking frontend
    res.json({
      success: true,
      data: {
        companyName: '',
        createdAt: null,
      },
    });
  }
});

// Generic config endpoint to get multiple config values - now uses SSM
companyRouter.post('/config/get', requireAdmin, async (req, res) => {
  try {
    const { keys } = req.body;

    if (!keys || !Array.isArray(keys)) {
      return res.status(400).json({
        error: 'Keys array is required',
      });
    }

    // Get tenant ID from authenticated user
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for organization',
      });
    }

    // Get all requested config values (automatically routed to appropriate backends)
    // TODO - batch these requests together, especially the DB ones. This uses a ton of connections right now
    const configPromises = keys.map((key: string) =>
      getConfigValue(key, tenantId).then((value: unknown) => ({ key, value }))
    );

    const results = await Promise.all(configPromises);

    // Convert to key-value object
    const configData: Record<string, unknown> = {};
    results.forEach(({ key, value }: { key: string; value: unknown }) => {
      configData[key] = value;
    });

    res.json({
      success: true,
      data: configData,
    });
  } catch (error) {
    logger.error('Error getting config values', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Get all config values endpoint - now uses SSM
companyRouter.get('/config/all', requireAdmin, async (req, res) => {
  try {
    // Get tenant ID from authenticated user
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for organization',
      });
    }

    // Get all config values (from both backends)
    const configData = await getAllConfigValues(tenantId);

    res.json({
      success: true,
      data: configData,
    });
  } catch (error) {
    logger.error('Error getting all config values', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

/**
 * Handle Linear API key save event by triggering initial data ingestion
 * @param tenantId - The tenant/organization ID
 * @param linearApiKey - The Linear API key
 */
async function handleLinearApiKeySaved(tenantId: string, _linearApiKey: string): Promise<void> {
  try {
    logger.info('Linear API key saved, triggering initial ingest', { tenant_id: tenantId });

    // Update Notion CRM - Linear integration connected
    await updateIntegrationStatus(tenantId, 'linear', true);

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering Linear API backfill job', { tenant_id: tenantId });

      // Trigger Linear API ingestion to pull existing data
      await sqsClient.sendLinearApiIngestJob(tenantId);

      logger.info('Linear API backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.error('SQS not configured - skipping Linear API backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Error handling Linear API key save', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the config save if post-processing fails
  }
}

/**
 * Fetch Trello member information using the access token
 * @param accessToken - Trello access token
 * @returns Object with member ID and username, or null if failed
 */
async function fetchTrelloMemberInfo(
  accessToken: string
): Promise<{ memberId: string; username: string } | null> {
  try {
    const apiKey = process.env.TRELLO_POWER_UP_API_KEY;
    if (!apiKey) {
      logger.error('TRELLO_POWER_UP_API_KEY not configured');
      return null;
    }

    const response = await fetch(
      `https://api.trello.com/1/members/me?key=${apiKey}&token=${accessToken}`
    );

    if (!response.ok) {
      logger.error('Failed to fetch Trello member info', {
        status: response.status,
        statusText: response.statusText,
      });
      return null;
    }

    const memberData = (await response.json()) as { id: string; username: string };
    if (!memberData.id || !memberData.username) {
      logger.error('Invalid member data from Trello API', { memberData });
      return null;
    }

    return { memberId: memberData.id, username: memberData.username };
  } catch (error) {
    logger.error('Error fetching Trello member info', error);
    return null;
  }
}

/**
 * Handle Trello access token save event by triggering initial data ingestion
 * and storing installation info for GDPR compliance
 * @param tenantId - The tenant/organization ID
 * @param accessToken - The Trello access token
 */
async function handleTrelloAccessTokenSaved(tenantId: string, accessToken: string): Promise<void> {
  try {
    if (!accessToken || accessToken.trim() === '') {
      logger.info('Trello access token cleared (disconnect)', { tenant_id: tenantId });
      await deleteConfigValue(TRELLO_CONFIG_KEY_WEBHOOK_SECRET, tenantId);
      await updateIntegrationStatus(tenantId, TRELLO_INTEGRATION_NAME, false);

      // Mark connector as disconnected
      await uninstallConnector(tenantId, ConnectorType.Trello);

      return;
    }

    logger.info('Trello access token saved, triggering initial ingest', { tenant_id: tenantId });

    // Fetch member info from Trello API for GDPR compliance tracking
    const memberInfo = await fetchTrelloMemberInfo(accessToken);
    if (memberInfo) {
      await installConnector({
        tenantId,
        type: ConnectorType.Trello,
        externalId: memberInfo.memberId,
        externalMetadata: {
          member_username: memberInfo.username,
        },
      });
      logger.info('Trello connector installation saved', {
        tenant_id: tenantId,
        member_id: memberInfo.memberId,
        username: memberInfo.username,
      });
    } else {
      logger.warn('Failed to fetch Trello member info for installation tracking', {
        tenant_id: tenantId,
      });
    }

    const globalWebhookSecret = process.env.TRELLO_POWER_UP_SECRET;
    if (globalWebhookSecret) {
      logger.info('Storing Trello webhook secret for tenant', { tenant_id: tenantId });
      await saveConfigValue(TRELLO_CONFIG_KEY_WEBHOOK_SECRET, globalWebhookSecret, tenantId);
    } else {
      logger.warn('TRELLO_POWER_UP_SECRET not configured - webhook verification will fail', {
        tenant_id: tenantId,
      });
    }

    // Update Notion CRM - Trello integration connected
    await updateIntegrationStatus(tenantId, TRELLO_INTEGRATION_NAME, true);

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering Trello API backfill job', { tenant_id: tenantId });

      // Trigger Trello API ingestion to pull existing data
      await sqsClient.sendTrelloApiIngestJob(tenantId);

      logger.info('Trello API backfill job queued successfully', { tenant_id: tenantId });
    } else {
      logger.error('SQS not configured - skipping Trello API backfill', { tenant_id: tenantId });
    }
  } catch (error) {
    logger.error('Error handling Trello access token save', error, { tenant_id: tenantId });
  }
}

/**
 * Handle Slack secret save event by checking if all secrets are available
 * and triggering the bot to join all channels
 * @param tenantId - The tenant/organization ID
 * @param savedKey - The key that was just saved (SLACK_BOT_TOKEN or SLACK_SIGNING_SECRET)
 */
async function handleSlackSecretSaved(tenantId: string, savedKey: string): Promise<void> {
  try {
    logger.info('Slack secret saved, checking if all secrets are available', {
      tenant_id: tenantId,
      savedKey,
    });

    // Check if we have both Slack secrets
    const [botToken, signingSecret] = await Promise.all([
      getConfigValue('SLACK_BOT_TOKEN', tenantId),
      getConfigValue('SLACK_SIGNING_SECRET', tenantId),
    ]);

    if (botToken && signingSecret) {
      logger.info('All Slack secrets available, sending control messages', { tenant_id: tenantId });

      if (isSqsConfigured()) {
        const sqsClient = getSqsClient();

        try {
          // Send control messages sequentially to ensure proper order:
          // 1. First refresh bot credentials (restart TenantSlackApp)
          // 2. Then join channels (using the fresh app instance)

          // Send control message to refresh bot credentials (bot will restart and get fresh bot ID)
          try {
            await sqsClient.sendSlackBotRefreshCredentials(tenantId);
            logger.info('Bot credentials refresh control message sent', { tenant_id: tenantId });
          } catch (error) {
            logger.error('Error sending bot credentials refresh control message', error, {
              tenant_id: tenantId,
            });
            // Continue to try joining channels even if refresh fails
          }

          // Send control message to Slack bot to join all channels (after refresh)
          try {
            await sqsClient.sendSlackBotJoinAllChannels(tenantId);
            logger.info('Join all channels control message sent', { tenant_id: tenantId });
          } catch (error) {
            logger.error('Error sending join all channels control message', error, {
              tenant_id: tenantId,
            });
          }
        } catch (error) {
          logger.error('Error sending control messages', error, { tenant_id: tenantId });
        }
      } else {
        logger.error('SQS not configured - skipping Slack bot control messages', {
          tenant_id: tenantId,
        });
      }
    } else {
      const missingSecrets = [];
      if (!botToken) missingSecrets.push('SLACK_BOT_TOKEN');
      if (!signingSecret) missingSecrets.push('SLACK_SIGNING_SECRET');
      logger.info('Waiting for additional Slack secrets', {
        tenant_id: tenantId,
        missingSecrets,
      });
    }
  } catch (error) {
    logger.error('Error handling Slack secret save', error, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the config save if post-processing fails
  }
}

/**
 * Handle organization name update by updating user properties in analytics
 * @param tenantId - The tenant/organization ID
 * @param organizationName - The new organization name
 * @param userId - The user ID who made the change (optional)
 */
async function handleOrganizationNameUpdate(
  tenantId: string,
  organizationName: string,
  userId?: string
): Promise<void> {
  try {
    const analyticsService = getAnalyticsService();

    if (!analyticsService.isInitialized) {
      logger.warn('Analytics service not initialized, skipping organization name update', {
        tenant_id: tenantId,
      });
      return;
    }

    logger.info('Updating organization name in analytics user properties', {
      tenant_id: tenantId,
      organization_name: organizationName,
      user_id: userId,
    });

    // Update tenant identification with new organization name
    await analyticsService.identify(tenantId, {
      org_name: organizationName,
      last_updated_by: userId,
      last_updated_at: new Date().toISOString(),
    });

    logger.info('Successfully updated organization name in analytics', {
      tenant_id: tenantId,
      organization_name: organizationName,
    });
  } catch (error) {
    logger.error('Error updating organization name in analytics', error, {
      tenant_id: tenantId,
      organization_name: organizationName,
    });
    // Don't throw - we don't want to fail the config save if tracking fails
  }
}

/**
 * Handle data sharing setting update by updating user properties in analytics
 * @param tenantId - The tenant/organization ID
 * @param enabled - Whether data sharing is enabled
 * @param userId - The user ID who made the change (optional)
 */
async function handleDataSharingUpdate(
  tenantId: string,
  enabled: boolean,
  userId?: string
): Promise<void> {
  try {
    const analyticsService = getAnalyticsService();

    if (!analyticsService.isInitialized) {
      logger.warn('Analytics service not initialized, skipping data sharing update', {
        tenant_id: tenantId,
      });
      return;
    }

    logger.info('Updating data sharing setting in analytics user properties', {
      tenant_id: tenantId,
      data_sharing_enabled: enabled,
      user_id: userId,
    });

    // Update tenant identification with new data sharing setting
    await analyticsService.identify(tenantId, {
      data_sharing_enabled: enabled,
      last_updated_by: userId,
      last_updated_at: new Date().toISOString(),
    });

    logger.info('Successfully updated data sharing setting in analytics', {
      tenant_id: tenantId,
      data_sharing_enabled: enabled,
    });
  } catch (error) {
    logger.error('Error updating data sharing setting in analytics', error, {
      tenant_id: tenantId,
      data_sharing_enabled: enabled,
    });
    // Don't throw - we don't want to fail the config save if tracking fails
  }
}

/**
 * Handle proactivity setting update by updating user properties in analytics
 * @param tenantId - The tenant/organization ID
 * @param enabled - Whether proactivity is enabled
 * @param userId - The user ID who made the change (optional)
 */
async function handleProactivityUpdate(
  tenantId: string,
  enabled: boolean,
  userId?: string
): Promise<void> {
  try {
    const analyticsService = getAnalyticsService();

    if (!analyticsService.isInitialized) {
      logger.warn('Analytics service not initialized, skipping proactivity update', {
        tenant_id: tenantId,
      });
      return;
    }

    logger.info('Updating proactivity setting in analytics user properties', {
      tenant_id: tenantId,
      proactivity_enabled: enabled,
      user_id: userId,
    });

    // Update tenant identification with new proactivity setting
    await analyticsService.identify(tenantId, {
      proactivity_enabled: enabled,
      last_updated_by: userId,
      last_updated_at: new Date().toISOString(),
    });

    logger.info('Successfully updated proactivity setting in analytics', {
      tenant_id: tenantId,
      proactivity_enabled: enabled,
    });
  } catch (error) {
    logger.error('Error updating proactivity setting in analytics', error, {
      tenant_id: tenantId,
      proactivity_enabled: enabled,
    });
    // Don't throw - we don't want to fail the config save if tracking fails
  }
}

/**
 * Handle skip external guests setting update by updating user properties in analytics
 * @param tenantId - The tenant/organization ID
 * @param skipEnabled - Whether skipping external guest channels is enabled
 * @param userId - The user ID who made the change (optional)
 */
async function handleExternalGuestsUpdate(
  tenantId: string,
  skipEnabled: boolean,
  userId?: string
): Promise<void> {
  try {
    const analyticsService = getAnalyticsService();

    if (!analyticsService.isInitialized) {
      logger.warn('Analytics service not initialized, skipping external guests update', {
        tenant_id: tenantId,
      });
      return;
    }

    logger.info('Updating skip external guests setting in analytics user properties', {
      tenant_id: tenantId,
      skip_external_guests: skipEnabled,
      user_id: userId,
    });

    // Update tenant identification with new skip external guests setting
    await analyticsService.identify(tenantId, {
      skip_external_guests: skipEnabled,
      last_updated_by: userId,
      last_updated_at: new Date().toISOString(),
    });

    logger.info('Successfully updated skip external guests setting in analytics', {
      tenant_id: tenantId,
      skip_external_guests: skipEnabled,
    });
  } catch (error) {
    logger.error('Error updating skip external guests setting in analytics', error, {
      tenant_id: tenantId,
      skip_external_guests: skipEnabled,
    });
    // Don't throw - we don't want to fail the config save if tracking fails
  }
}

/**
 * Handle Gather API Key save event by retrieving space Id and firing backfill
 * @param tenantId - The tenant/organization ID
 * @param apiKey - the saved api key
 */
async function handleGatherWebhookUpdate(tenantId: string): Promise<void> {
  try {
    logger.info('Gather API key saved, triggering setup', { tenant_id: tenantId });
    const apiKey = await getConfigValue('GATHER_API_KEY', tenantId);

    const response = await fetch(GATHER_API_URL, {
      method: 'GET',
      headers: {
        'x-api-key': apiKey as string,
      },
    });
    const data = await response.json();
    if (!response.ok) {
      logger.error('Error [handleGatherWebhookUpdate]: Gather API key validation failed', {
        tenant_id: tenantId,
        status: response.status,
      });
      throw new Error('Failed to get Gather space ID');
    }
    const sqsClient = getSqsClient();
    await sqsClient.sendGatherApiIngestJob(tenantId, data.spaceId);
  } catch (error) {
    logger.error('Error [handleGatherWebhookUpdate]:', error.message, { tenant_id: tenantId });
    // Don't throw - we don't want to fail the config save if post-processing fails
  }
}

/**
 * Validate configuration values before saving
 * @param key - Configuration key
 * @param value - Configuration value
 * @returns Validation result with error message if invalid
 */
function validateConfigValue(key: string, value: string): { valid: boolean; error?: string } {
  if (key === 'SLACK_BOT_NAME') {
    const trimmed = value.trim();

    // Check length (max 35 chars for Slack manifest)
    if (trimmed.length === 0) {
      return { valid: false, error: 'Bot name is required' };
    }
    if (trimmed.length > 35) {
      return { valid: false, error: 'Bot name must be 35 characters or less' };
    }

    // Check characters - allow alphanumeric, spaces, hyphens, underscores, and periods
    if (!/^[a-zA-Z0-9\s\-_.]+$/.test(trimmed)) {
      return {
        valid: false,
        error:
          'Bot name must contain only letters, numbers, spaces, hyphens, underscores, and periods',
      };
    }
  } else if (key === 'SLACK_BOT_QA_CONFIDENCE_THRESHOLD') {
    const numValue = parseFloat(value);

    if (isNaN(numValue) || numValue < 0 || numValue > 100) {
      return { valid: false, error: 'Confidence threshold must be a number between 0 and 100' };
    }
  }

  return { valid: true };
}

// Generic config save endpoint
// TODO we should not allow arbitrary config keys to be saved
companyRouter.post('/config/save', requireAdmin, async (req, res) => {
  const { key, value } = req.body;

  if (!key || value === undefined) {
    return res.status(400).json({
      error: 'Key and value are required',
    });
  }

  // Validate the configuration value
  const validation = validateConfigValue(key, value);
  if (!validation.valid) {
    return res.status(400).json({
      error: validation.error,
    });
  }

  // Get tenant ID from authenticated user
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({
      error: 'Organization not provisioned yet',
    });
  }

  try {
    logger.info('Saving config value', { key, tenant_id: tenantId });

    // Save the config value (automatically routed to appropriate backend)
    const success = await saveConfigValue(key, value, tenantId);
    if (success) {
      // Handle special post-save actions for specific config keys
      if (key === 'GITHUB_TOKEN') {
        // Trigger GitHub-specific setup after PAT is saved
        handleGitHubTokenSaved(tenantId, value as string);
      } else if (key === 'LINEAR_API_KEY') {
        // Trigger Linear API ingest after API key is saved
        handleLinearApiKeySaved(tenantId, value as string);
      } else if (key === TRELLO_CONFIG_KEY_ACCESS_TOKEN) {
        // Trigger Trello API ingest after access token is saved
        handleTrelloAccessTokenSaved(tenantId, value as string);
      } else if (key === 'SLACK_BOT_TOKEN' || key === 'SLACK_SIGNING_SECRET') {
        // Check if we have both Slack secrets and trigger channel join
        await handleSlackSecretSaved(tenantId, key);
      } else if (key === 'COMPANY_NAME') {
        // Track organization name update in analytics
        await handleOrganizationNameUpdate(tenantId, value as string, req.user?.id);
      } else if (key === 'ALLOW_DATA_SHARING_FOR_IMPROVEMENTS') {
        // Track data sharing setting update in analytics
        const enabled = value === 'true';
        handleDataSharingUpdate(tenantId, enabled, req.user?.id);
      } else if (key === 'SLACK_BOT_QA_ALL_CHANNELS') {
        // Track proactivity setting update in analytics
        const enabled = value === 'true';
        await handleProactivityUpdate(tenantId, enabled, req.user?.id);
      } else if (key === 'SLACK_BOT_QA_SKIP_CHANNELS_WITH_EXTERNAL_GUESTS') {
        // Track skip external guests setting update in analytics
        const skipEnabled = value === 'true';
        await handleExternalGuestsUpdate(tenantId, skipEnabled, req.user?.id);
      } else if (key === 'GATHER_WEBHOOK_SECRET') {
        // Track Gather API key update in analytics
        await handleGatherWebhookUpdate(tenantId);
      }

      res.json({
        success: true,
        message: 'Config value saved successfully',
      });
    } else {
      res.status(500).json({
        error: 'Failed to save config value to SSM',
      });
    }
  } catch (error) {
    logger.error('Error saving config value', error, { key, tenant_id: tenantId });
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Delete config value endpoint
companyRouter.delete('/config/:key', requireAdmin, async (req, res) => {
  try {
    const { key } = req.params;
    const tenantId = req.user?.tenantId;

    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    if (!key) {
      return res.status(400).json({ error: 'Missing required field: key' });
    }

    // Delete the config value
    const success = await deleteConfigValue(key, tenantId);

    if (success) {
      // Handle Trello-specific cleanup and webhook triggering
      if (key === TRELLO_CONFIG_KEY_ACCESS_TOKEN) {
        await handleTrelloAccessTokenSaved(tenantId, '');
      }

      res.json({
        success: true,
        message: `Config value deleted: ${key}`,
      });
    } else {
      res.status(500).json({
        error: 'Failed to delete config value',
      });
    }
  } catch (error) {
    logger.error('Error deleting config value', error, {
      key: req.params.key,
      tenant_id: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Internal server error' });
  }
});

export { companyRouter };
