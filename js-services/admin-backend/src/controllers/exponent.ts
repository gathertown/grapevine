/**
 * Exponent Controller
 * Handles both external API endpoints and admin dashboard endpoints for Exponent bug triager integration
 */

import { Router, Request, Response } from 'express';
import { logger } from '../utils/logger.js';
import { requireApiKey } from '../middleware/requireApiKey.js';
import { requireAdmin } from '../middleware/auth-middleware.js';
import { getConfigValue, saveConfigValue } from '../config/index.js';
import { getSqsClient } from '../jobs/sqs-client.js';

export const exponentRouter = Router();

interface LinearTeam {
  id: string;
  name: string;
}

interface LinearTeamMapping {
  linearTeam: LinearTeam;
  channels: string[];
}

// ============================================================================
// EXTERNAL API ENDPOINTS (API Key Authentication)
// ============================================================================

/**
 * Get Linear team to Slack channel mappings (API key protected)
 * External endpoint for 3rd party integrations
 */
exponentRouter.get('/linear-team-mappings', requireApiKey, async (req: Request, res: Response) => {
  const tenantId = req.tenantId;
  if (!tenantId) {
    return res.status(400).json({
      error: 'No tenant found for API key',
    });
  }

  try {
    const mappingsJson = (await getConfigValue('LINEAR_TEAM_SLACK_CHANNEL_MAPPINGS', tenantId)) as
      | string
      | null;

    if (!mappingsJson) {
      // No mappings saved yet, return empty array
      logger.debug('No Linear team mappings found', {
        tenantId,
        operation: 'exponent-external-mappings-get',
      });
      return res.json({ mappings: [] });
    }

    const mappings: LinearTeamMapping[] = JSON.parse(mappingsJson);

    logger.info('Retrieved Linear team mappings via API key', {
      tenantId,
      mappingCount: mappings.length,
      operation: 'exponent-external-mappings-get',
    });

    res.json({ mappings });
  } catch (error) {
    logger.error('Failed to get Linear team mappings via API key', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenantId,
      operation: 'exponent-external-mappings-get-error',
    });

    res.status(500).json({
      error: 'Failed to get Linear team mappings',
    });
  }
});

// ============================================================================
// ADMIN DASHBOARD ENDPOINTS (Admin User Authentication)
// ============================================================================

// Note: Linear teams are now fetched directly from the frontend using the Linear GraphQL API

/**
 * Get Linear team to Slack channel mappings (Admin protected)
 * Internal endpoint for admin dashboard configuration
 */
exponentRouter.get(
  '/admin/linear-team-mappings',
  requireAdmin,
  async (req: Request, res: Response) => {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for user',
      });
    }

    try {
      const mappingsJson = (await getConfigValue(
        'LINEAR_TEAM_SLACK_CHANNEL_MAPPINGS',
        tenantId
      )) as string | null;

      if (!mappingsJson) {
        // No mappings saved yet, return empty array
        return res.json({ mappings: [] });
      }

      const mappings: LinearTeamMapping[] = JSON.parse(mappingsJson);

      logger.debug('Retrieved Linear team mappings for admin dashboard', {
        tenantId,
        mappingCount: mappings.length,
        operation: 'exponent-admin-mappings-get',
      });

      res.json({ mappings });
    } catch (error) {
      logger.error('Failed to get Linear team mappings for admin dashboard', {
        error: error instanceof Error ? error.message : 'Unknown error',
        tenantId,
        operation: 'exponent-admin-mappings-get-error',
      });

      res.status(500).json({
        error: 'Failed to get Linear team mappings',
      });
    }
  }
);

/**
 * Save Linear team to Slack channel mappings (Admin protected)
 * Internal endpoint for admin dashboard configuration
 */
exponentRouter.post(
  '/admin/linear-team-mappings',
  requireAdmin,
  async (req: Request, res: Response) => {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for user',
      });
    }

    const { mappings } = req.body;

    // Validate mappings format
    if (!Array.isArray(mappings)) {
      return res.status(400).json({
        error: 'Mappings must be an array',
      });
    }

    // Validate each mapping has required fields
    for (const mapping of mappings) {
      if (!mapping.linearTeam || !mapping.linearTeam.id || !mapping.linearTeam.name) {
        return res.status(400).json({
          error: 'Each mapping must have a linearTeam with id and name',
        });
      }
      if (!Array.isArray(mapping.channels)) {
        return res.status(400).json({
          error: 'Each mapping must have a channels array',
        });
      }
    }

    try {
      // Get existing mappings to detect newly added channels
      const oldMappingsJson = await getConfigValue('LINEAR_TEAM_SLACK_CHANNEL_MAPPINGS', tenantId);
      const oldMappings: LinearTeamMapping[] = oldMappingsJson
        ? JSON.parse(oldMappingsJson as string)
        : [];

      // Extract all old channel IDs
      const oldChannelIds = new Set(oldMappings.flatMap((m: LinearTeamMapping) => m.channels));

      // Extract all new channel IDs
      const newChannelIds = mappings.flatMap((m: LinearTeamMapping) => m.channels);

      // Find newly mapped channels (channels in new but not in old) and deduplicate
      const newlyMappedChannels = Array.from(
        new Set(newChannelIds.filter((id: string) => !oldChannelIds.has(id)))
      );

      // Save the new mappings
      const mappingsJson = JSON.stringify(mappings);
      await saveConfigValue('LINEAR_TEAM_SLACK_CHANNEL_MAPPINGS', mappingsJson, tenantId);

      logger.info('Saved Linear team mappings from admin dashboard', {
        tenantId,
        mappingCount: mappings.length,
        newlyMappedCount: newlyMappedChannels.length,
        operation: 'exponent-admin-mappings-save',
      });

      // If there are newly mapped channels, send welcome messages
      if (newlyMappedChannels.length > 0) {
        const sqsClient = getSqsClient();
        await sqsClient.sendTriageChannelWelcomeMessage(tenantId, newlyMappedChannels);

        logger.info('Queued triage channel welcome messages', {
          tenantId,
          channelCount: newlyMappedChannels.length,
          operation: 'exponent-admin-mappings-welcome-queued',
        });
      }

      res.json({ success: true, mappings });
    } catch (error) {
      logger.error('Failed to save Linear team mappings from admin dashboard', {
        error: error instanceof Error ? error.message : 'Unknown error',
        tenantId,
        operation: 'exponent-admin-mappings-save-error',
      });

      res.status(500).json({
        error: 'Failed to save Linear team mappings',
      });
    }
  }
);

/**
 * Get triage bot proactive mode setting (Admin protected)
 * Internal endpoint for admin dashboard configuration
 */
exponentRouter.get(
  '/admin/triage-proactive-mode',
  requireAdmin,
  async (req: Request, res: Response) => {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for user',
      });
    }

    try {
      const value = (await getConfigValue('TRIAGE_BOT_PROACTIVE_MODE', tenantId)) as
        | string
        | boolean
        | null;

      let enabled = true; // Default to proactive mode

      if (typeof value === 'string') {
        enabled = value.toLowerCase() === 'true';
      } else if (typeof value === 'boolean') {
        enabled = value;
      }

      logger.debug('Retrieved triage proactive mode setting', {
        tenantId,
        enabled,
        operation: 'exponent-admin-proactive-mode-get',
      });

      res.json({ enabled });
    } catch (error) {
      logger.error('Failed to get triage proactive mode setting', {
        error: error instanceof Error ? error.message : 'Unknown error',
        tenantId,
        operation: 'exponent-admin-proactive-mode-get-error',
      });

      res.status(500).json({
        error: 'Failed to get triage proactive mode setting',
      });
    }
  }
);

/**
 * Set triage bot proactive mode setting (Admin protected)
 * Internal endpoint for admin dashboard configuration
 */
exponentRouter.post(
  '/admin/triage-proactive-mode',
  requireAdmin,
  async (req: Request, res: Response) => {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for user',
      });
    }

    const { enabled } = req.body;

    // Validate enabled is boolean
    if (typeof enabled !== 'boolean') {
      return res.status(400).json({
        error: 'enabled must be a boolean',
      });
    }

    try {
      await saveConfigValue('TRIAGE_BOT_PROACTIVE_MODE', String(enabled), tenantId);

      logger.info('Saved triage proactive mode setting', {
        tenantId,
        enabled,
        operation: 'exponent-admin-proactive-mode-save',
      });

      res.json({ success: true, enabled });
    } catch (error) {
      logger.error('Failed to save triage proactive mode setting', {
        error: error instanceof Error ? error.message : 'Unknown error',
        tenantId,
        operation: 'exponent-admin-proactive-mode-save-error',
      });

      res.status(500).json({
        error: 'Failed to save triage proactive mode setting',
      });
    }
  }
);
