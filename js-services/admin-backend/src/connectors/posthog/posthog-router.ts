import { Router } from 'express';

import { requireAdmin } from '../../middleware/auth-middleware';
import { logger } from '../../utils/logger';
import {
  deletePostHogApiKey,
  deletePostHogHost,
  savePostHogApiKey,
  savePostHogHost,
} from './posthog-config';
import { installPostHogConnector, uninstallPostHogConnector } from './posthog-connector';
import { triggerPostHogBackfill } from './posthog-jobs';
import { fetchPostHogProjects } from './posthog-api';

const posthogRouter = Router();

interface ConnectReq {
  apiKey: string;
  host: string;
  selectedProjectIds?: number[];
}

posthogRouter.post('/connect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  const { apiKey, host, selectedProjectIds } = req.body as ConnectReq;

  if (!apiKey || !host) {
    return res.status(400).json({ error: 'API key and host are required' });
  }

  // Normalize host URL
  const normalizedHost = host.startsWith('http') ? host : `https://${host}`;

  try {
    // Save credentials FIRST - if this fails, we don't want to create an orphan installation
    await savePostHogApiKey(tenantId, apiKey);
    await savePostHogHost(tenantId, normalizedHost);
    await installPostHogConnector({
      tenantId,
      apiKey,
      host: normalizedHost,
      selectedProjectIds,
    });
    await triggerPostHogBackfill(tenantId);
  } catch (error) {
    logger.error('Error connecting PostHog', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error connecting PostHog' });
  }

  logger.info('PostHog API key saved and installed successfully', {
    tenant_id: tenantId,
  });

  res.json({});
});

posthogRouter.post('/disconnect', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    await deletePostHogApiKey(tenantId);
    await deletePostHogHost(tenantId);
    await uninstallPostHogConnector(tenantId);
  } catch (error) {
    logger.error('Error disconnecting PostHog', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error disconnecting PostHog' });
  }

  logger.info('PostHog API key deleted and uninstalled successfully', {
    tenant_id: tenantId,
  });

  res.json({});
});

interface FetchProjectsReq {
  apiKey: string;
  host: string;
}

posthogRouter.post('/projects', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  const { apiKey, host } = req.body as FetchProjectsReq;

  if (!apiKey || !host) {
    return res.status(400).json({ error: 'API key and host are required' });
  }

  // Normalize host URL
  const normalizedHost = host.startsWith('http') ? host : `https://${host}`;

  try {
    const projects = await fetchPostHogProjects(apiKey, normalizedHost);
    res.json({
      projects: projects.map((p) => ({
        id: p.id,
        name: p.name,
        uuid: p.uuid,
      })),
    });
  } catch (error) {
    logger.error('Error fetching PostHog projects', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error fetching PostHog projects' });
  }
});

posthogRouter.post('/sync', requireAdmin, async (req, res) => {
  const tenantId = req.user?.tenantId;
  if (!tenantId) {
    return res.status(400).json({ error: 'No tenant found for organization' });
  }

  try {
    await triggerPostHogBackfill(tenantId);
  } catch (error) {
    logger.error('Error triggering PostHog sync', {
      tenant_id: tenantId,
      error_message: error.message,
    });
    return res.status(500).json({ error: error.message || 'Error triggering PostHog sync' });
  }

  logger.info('PostHog sync triggered successfully', {
    tenant_id: tenantId,
  });

  res.json({ message: 'Sync triggered successfully' });
});

export { posthogRouter };
