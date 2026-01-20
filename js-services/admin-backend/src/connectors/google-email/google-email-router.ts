import { Router, Request, Response } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { getConfigValue, saveConfigValue } from '../../config/index.js';
import {
  GoogleServiceAccountManager,
  extractServiceAccountClientId,
} from '../../google-service-account.js';
import { logger } from '../../utils/logger.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { getBaseDomain } from '../../utils/config.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';

const googleEmailRouter = Router();

/**
 * GET /api/google-email/configuration
 * Auto-provisions service account if not exists and returns configuration
 */
googleEmailRouter.get('/configuration', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    // Check if control service account exists
    const controlServiceAccountJson = process.env.GOOGLE_DRIVE_CONTROL_SERVICE_ACCOUNT;
    if (!controlServiceAccountJson) {
      return res.status(500).json({
        error: 'Google Drive control service account not configured. Please contact administrator.',
      });
    }

    // Check if tenant has service account
    let tenantServiceAccount = await getConfigValue('GOOGLE_EMAIL_SERVICE_ACCOUNT', tenantId);
    const adminEmail = await getConfigValue('GOOGLE_EMAIL_ADMIN_EMAIL', tenantId);

    let clientId = null;

    // Auto-provision service account if not exists
    if (!tenantServiceAccount) {
      try {
        logger.info('Auto-provisioning service account for tenant', { tenant_id: tenantId });
        const manager = new GoogleServiceAccountManager();

        // Create the tenant-specific service account
        const serviceAccountDetails = await manager.createTenantServiceAccount(tenantId, true);

        if (!serviceAccountDetails.privateKeyData) {
          throw new Error('Failed to create service account key');
        }

        // Save the service account JSON to SSM
        const serviceAccountSaved = await saveConfigValue(
          'GOOGLE_EMAIL_SERVICE_ACCOUNT',
          serviceAccountDetails.privateKeyData,
          tenantId
        );

        if (!serviceAccountSaved) {
          throw new Error('Failed to save service account credentials');
        }

        tenantServiceAccount = serviceAccountDetails.privateKeyData;
        logger.info('Service account auto-provisioned for tenant', {
          tenant_id: tenantId,
          serviceAccountEmail: serviceAccountDetails.serviceAccountEmail,
        });
      } catch (error) {
        logger.error('Error auto-provisioning service account', error, {
          tenant_id: tenantId,
        });
        // Continue without service account - frontend will handle this state
      }
    }

    // Always run setupPubSubForTenant - it's idempotent and self-heals missing OIDC config
    // This ensures existing subscriptions without OIDC get updated when users visit the config page
    let tenantPubSubTopic = await getConfigValue('GOOGLE_EMAIL_PUB_SUB_TOPIC', tenantId);
    try {
      const manager = new GoogleServiceAccountManager();
      const baseDomain = getBaseDomain();
      const pubSubTopic = await manager.setupPubSubForTenant(
        tenantId,
        `https://${tenantId}.ingest.${baseDomain}/webhooks/google-email`
      );

      // Save topic if not already saved
      if (!tenantPubSubTopic) {
        tenantPubSubTopic = pubSubTopic;
        const pubSubTopicSaved = await saveConfigValue(
          'GOOGLE_EMAIL_PUB_SUB_TOPIC',
          pubSubTopic,
          tenantId
        );
        if (!pubSubTopicSaved) {
          throw new Error('Failed to save Pub/Sub topic');
        }
        logger.info('Pub/Sub topic created for tenant', {
          tenant_id: tenantId,
          pubSubTopic,
        });
      } else {
        logger.info('Pub/Sub subscription self-heal check completed', {
          tenant_id: tenantId,
        });
      }
    } catch (error) {
      logger.error('Error setting up Pub/Sub topic for tenant', error, {
        tenant_id: tenantId,
      });
    }

    // Extract client ID if service account exists
    if (tenantServiceAccount) {
      try {
        const serviceAccountData =
          typeof tenantServiceAccount === 'string'
            ? JSON.parse(tenantServiceAccount)
            : tenantServiceAccount;
        clientId = serviceAccountData.client_id;
      } catch (error) {
        logger.error('Error parsing tenant service account data', error, {
          tenant_id: tenantId,
        });
      }
    }

    res.json({
      clientId,
      adminEmail: adminEmail || null,
      isConfigured: !!(adminEmail && clientId),
    });
  } catch (error) {
    logger.error('Error getting Google Email configuration', error);
    res.status(500).json({ error: 'Failed to get configuration' });
  }
});

/**
 * POST /api/google-email/configuration
 * Saves admin email and starts background monitoring for auto-indexing
 */
googleEmailRouter.post('/configuration', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const { adminEmail } = req.body;
    if (!adminEmail || !adminEmail.trim()) {
      return res.status(400).json({ error: 'Admin email is required' });
    }

    // Validate email format
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(adminEmail.trim())) {
      return res.status(400).json({ error: 'Invalid email format' });
    }

    // Ensure service account exists (should have been auto-provisioned by GET)
    const tenantServiceAccount = await getConfigValue('GOOGLE_EMAIL_SERVICE_ACCOUNT', tenantId);
    if (!tenantServiceAccount) {
      return res.status(400).json({
        error: 'Service account not found. Please refresh the page and try again.',
      });
    }

    // Save admin email
    const success = await saveConfigValue('GOOGLE_EMAIL_ADMIN_EMAIL', adminEmail.trim(), tenantId);
    if (!success) {
      return res.status(500).json({ error: 'Failed to save admin email' });
    }

    logger.info('Google Email configuration saved for tenant', {
      tenant_id: tenantId,
      adminEmail: adminEmail.trim(),
    });

    // Extract service account client_id to use as external_id
    const serviceAccountClientId = extractServiceAccountClientId(tenantServiceAccount, tenantId, {
      tenant_id: tenantId,
    });

    // Create or update connector record (using service account client_id as external_id)
    await installConnector({
      tenantId,
      type: ConnectorType.GoogleEmail,
      externalId: serviceAccountClientId,
      externalMetadata: {
        admin_email: adminEmail.trim(),
      },
      updateMetadataOnExisting: true,
    });

    // Update Notion CRM - Google Email integration connected
    await updateIntegrationStatus(tenantId, 'google-email', true);

    // Start background monitoring job that will auto-start indexing when ready
    handleGoogleEmailConfigurationSaved(tenantId);

    res.json({
      success: true,
      message:
        'Configuration saved. Indexing will start automatically once domain delegation is configured.',
    });
  } catch (error) {
    logger.error('Error saving Google Email configuration', error);
    res.status(500).json({ error: 'Failed to save configuration' });
  }
});

/**
 * Handle Google Email configuration save event by monitoring for delegation setup
 * and auto-starting indexing when ready
 */
async function handleGoogleEmailConfigurationSaved(tenantId: string): Promise<void> {
  try {
    logger.info('Google Email configuration saved, starting monitoring', { tenant_id: tenantId });

    // Start background monitoring with retries
    const maxAttempts = 20; // ~10 minutes with 30s intervals
    let attempts = 0;

    const checkAndStartIndexing = async () => {
      attempts++;
      try {
        // Try to verify Google API access by attempting a test call
        const adminEmail = await getConfigValue('GOOGLE_EMAIL_ADMIN_EMAIL', tenantId);
        const serviceAccount = await getConfigValue('GOOGLE_EMAIL_SERVICE_ACCOUNT', tenantId);

        if (!adminEmail || !serviceAccount) {
          logger.info('Missing configuration, stopping monitoring', { tenant_id: tenantId });
          return;
        }

        // For now, we'll just trigger the discovery job after a delay
        // In production, you'd want to test the actual Google API access here
        // by attempting to list users or email messages with the service account

        if (isSqsConfigured()) {
          const sqsClient = getSqsClient();
          logger.info('Auto-triggering Google Email discovery job', { tenant_id: tenantId });

          await sqsClient.sendGoogleEmailDiscoveryJob(tenantId);
          logger.info('Google Email discovery job auto-started', { tenant_id: tenantId });
          return; // Success, stop monitoring
        } else {
          logger.info('SQS not configured, skipping Google Email discovery job', {
            tenant_id: tenantId,
          });
        }
      } catch (error) {
        logger.error('Delegation check failed', error, {
          tenant_id: tenantId,
          attempts,
          maxAttempts,
        });
        logger.info('Delegation not ready yet', { tenant_id: tenantId, attempts, maxAttempts });
      }

      // Schedule next check if not at max attempts
      if (attempts < maxAttempts) {
        logger.info('Scheduling next check for Google Email discovery job');
        setTimeout(() => checkAndStartIndexing(), 30000); // Check again in 30 seconds
      } else {
        logger.warn('Delegation setup timeout', { tenant_id: tenantId, maxAttempts });
      }
    };

    setTimeout(() => checkAndStartIndexing(), 30000); // Start checking after 30 seconds
  } catch (error) {
    logger.error('Error handling Google Email configuration save', error, {
      tenant_id: tenantId,
    });
  }
}

export { googleEmailRouter };
