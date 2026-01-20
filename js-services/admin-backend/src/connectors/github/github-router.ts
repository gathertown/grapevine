import { Router, Request, Response } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { getConfigValue, saveConfigValue, deleteConfigValue } from '../../config/index.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { Octokit } from '@octokit/rest';
import { createAppAuth } from '@octokit/auth-app';
import { logger } from '../../utils/logger.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { ConnectorInstallationsRepository } from '../../dal/connector-installations.js';

const githubRouter = Router();

// GitHub status endpoint
githubRouter.get('/status', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.json({ installed: false });
    }

    // Check for GitHub App installation first (from connector_installations)
    const connectorsRepo = new ConnectorInstallationsRepository();
    const connectorInstallation = await connectorsRepo.getByTenantAndType(
      tenantId,
      ConnectorType.GitHub
    );

    if (connectorInstallation) {
      return res.json({
        installed: true,
        type: 'github_app',
        installation_id: parseInt(connectorInstallation.external_id, 10),
      });
    }

    // Check legacy PAT token
    const hasLegacyToken = await getConfigValue('GITHUB_TOKEN', tenantId);
    if (hasLegacyToken) {
      return res.json({
        installed: true,
        type: 'pat',
        message: 'Using legacy Personal Access Token authentication',
        migration_available: true,
      });
    }

    return res.json({ installed: false });
  } catch (error) {
    logger.error('Error checking GitHub status', error);
    res.status(500).json({ error: 'Failed to check GitHub status' });
  }
});

githubRouter.get(
  '/installation/:installationId/manage-url',
  requireAdmin,
  async (req: Request, res: Response) => {
    try {
      const { installationId } = req.params;
      const tenantId = req.user?.tenantId;

      if (!tenantId) {
        return res.status(400).json({ error: 'No tenant found for organization' });
      }

      const appId = process.env.GITHUB_APP_ID;
      const privateKey = process.env.GITHUB_APP_PRIVATE_KEY;

      if (!appId || !privateKey) {
        return res.status(500).json({ error: 'GitHub App credentials not configured' });
      }

      const octokit = new Octokit({
        authStrategy: createAppAuth,
        auth: {
          appId,
          privateKey,
          installationId,
        },
      });

      const { data: installation } = await octokit.rest.apps.getInstallation({
        installation_id: parseInt(installationId as string),
      });

      if (!installation.account) {
        return res.status(404).json({ error: 'Installation account not found' });
      }

      let manageUrl: string;
      let accountName: string;
      let accountType: string;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const account = installation.account as any;

      if (account.slug || (account.login && account.type === 'Organization')) {
        accountType = 'Organization';
        const orgSlug = account.login || account.slug;
        manageUrl = `https://github.com/organizations/${orgSlug}/settings/installations/${installationId}`;
        accountName = account.name || orgSlug;
      } else {
        accountType = 'User';
        manageUrl = `https://github.com/settings/installations/${installationId}`;
        accountName = account.name || account.login;
      }

      return res.json({
        url: manageUrl,
        type: accountType,
        accountName,
      });
    } catch (error) {
      logger.error('Error generating GitHub installation management URL', error);
      res.status(500).json({
        error: 'Failed to generate installation management URL',
      });
    }
  }
);

githubRouter.post('/installation', requireAdmin, async (req, res) => {
  try {
    const { installation_id, setup_action } = req.body;

    if (!installation_id) {
      return res.status(400).json({
        error: 'installation_id is required',
      });
    }

    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'Organization not provisioned yet',
      });
    }

    logger.info('Storing GitHub App installation for tenant', {
      tenant_id: tenantId,
      installation_id,
      setup_action,
    });

    const connectorInstallation = await installConnector({
      tenantId,
      type: ConnectorType.GitHub,
      externalId: installation_id.toString(),
    });

    if (!connectorInstallation) {
      return res.status(500).json({
        error: 'Failed to store GitHub App installation',
      });
    }

    try {
      await saveConfigValue('GITHUB_SETUP_COMPLETE', 'true', tenantId);
      logger.info('GitHub setup marked as complete', { tenant_id: tenantId });
    } catch (githubError) {
      logger.warn('Could not mark GitHub setup as complete', {
        tenant_id: tenantId,
        installation_id,
        error: githubError,
      });
    }

    // Update Notion CRM - GitHub integration connected
    await updateIntegrationStatus(tenantId, 'github', true);

    if (isSqsConfigured()) {
      const sqsClient = getSqsClient();
      logger.info('Triggering GitHub App backfill ingest jobs', { tenant_id: tenantId });

      try {
        await Promise.all([
          sqsClient.sendGitHubPRBackfillIngestJob(tenantId, {
            organizations: [], // all orgs accessible by the app
            repositories: [], // all repos accessible by the app
          }),
          sqsClient.sendGitHubFileBackfillIngestJob(
            tenantId,
            [], // all repos for now
            [] // all orgs accessible by the app
          ),
        ]);

        logger.info('GitHub App backfill ingest jobs queued successfully', {
          tenant_id: tenantId,
        });
      } catch (sqsError) {
        logger.error('Error queuing GitHub App backfill jobs', sqsError, {
          tenant_id: tenantId,
        });
        // Don't fail the endpoint, just log the error
      }
    } else {
      logger.error('SQS not configured - skipping GitHub App backfill', {
        tenant_id: tenantId,
      });
    }

    res.json({
      success: true,
      message: 'GitHub App installation stored successfully',
      installation_id,
    });
  } catch (error) {
    logger.error('Error storing GitHub App installation', error, {
      tenant_id: req.user?.tenantId,
      installation_id: req.body?.installation_id,
    });
    res.status(500).json({
      error: 'Failed to store GitHub App installation',
    });
  }
});

// GitHub backfill endpoints (localhost only)
githubRouter.post('/backfill/pr', requireAdmin, async (req, res) => {
  try {
    // Only allow on localhost
    if (req.hostname !== 'localhost' && req.hostname !== '127.0.0.1') {
      return res.status(403).json({
        error: 'This endpoint is only available on localhost',
      });
    }

    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for organization',
      });
    }

    if (!isSqsConfigured()) {
      return res.status(500).json({
        error: 'SQS not configured',
      });
    }

    const sqsClient = getSqsClient();

    logger.info('Triggering GitHub PR backfill job manually', {
      tenant_id: tenantId,
    });

    const config = {
      message_type: 'backfill' as const,
      source: 'github_pr_backfill_root' as const,
      tenant_id: tenantId,
      repositories: [],
      organizations: [],
    };

    await sqsClient.sendBackfillIngestJob(config);

    res.json({
      success: true,
      message: 'GitHub PR backfill job triggered',
    });
  } catch (error) {
    logger.error('Error triggering GitHub PR backfill', error);
    res.status(500).json({ error: 'Failed to trigger GitHub PR backfill' });
  }
});

githubRouter.post('/backfill/file', requireAdmin, async (req, res) => {
  try {
    // Only allow on localhost
    if (req.hostname !== 'localhost' && req.hostname !== '127.0.0.1') {
      return res.status(403).json({
        error: 'This endpoint is only available on localhost',
      });
    }

    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({
        error: 'No tenant found for organization',
      });
    }

    if (!isSqsConfigured()) {
      return res.status(500).json({
        error: 'SQS not configured',
      });
    }

    const sqsClient = getSqsClient();

    logger.info('Triggering GitHub file backfill job manually', {
      tenant_id: tenantId,
    });

    const config = {
      message_type: 'backfill' as const,
      source: 'github_file_backfill_root' as const,
      tenant_id: tenantId,
      repositories: [],
      organizations: [],
    };

    await sqsClient.sendBackfillIngestJob(config);

    res.json({
      success: true,
      message: 'GitHub file backfill job triggered',
    });
  } catch (error) {
    logger.error('Error triggering GitHub file backfill', error);
    res.status(500).json({ error: 'Failed to trigger GitHub file backfill' });
  }
});

// GitHub disconnect endpoint
githubRouter.delete('/disconnect', requireAdmin, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    const hasLegacyToken = await getConfigValue('GITHUB_TOKEN', tenantId);
    if (!hasLegacyToken) {
      return res.status(400).json({ error: 'No legacy GitHub token found' });
    }

    await deleteConfigValue('GITHUB_TOKEN', tenantId);
    await deleteConfigValue('GITHUB_SETUP_COMPLETE', tenantId);

    logger.info('GitHub PAT disconnected', { tenantId });
    return res.json({ success: true });
  } catch (error) {
    logger.error('Failed to disconnect GitHub', error);
    return res.status(500).json({ error: 'Failed to disconnect' });
  }
});

export { githubRouter };
