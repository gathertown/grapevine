import { Router, Request, Response } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { dbMiddleware } from '../../middleware/db-middleware.js';
import { getConfigValue, saveConfigValue } from '../../config/index.js';
import {
  GoogleServiceAccountManager,
  extractServiceAccountClientId,
} from '../../google-service-account.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { logger } from '../../utils/logger.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';

const googleDriveRouter = Router();

/**
 * GET /api/google-drive/configuration
 * Auto-provisions service account if not exists and returns configuration
 */
googleDriveRouter.get('/configuration', requireAdmin, async (req: Request, res: Response) => {
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
    let tenantServiceAccount = await getConfigValue('GOOGLE_DRIVE_SERVICE_ACCOUNT', tenantId);
    const adminEmail = await getConfigValue('GOOGLE_DRIVE_ADMIN_EMAIL', tenantId);

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
          'GOOGLE_DRIVE_SERVICE_ACCOUNT',
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
    logger.error('Error getting Google Drive configuration', error);
    res.status(500).json({ error: 'Failed to get configuration' });
  }
});

/**
 * POST /api/google-drive/configuration
 * Saves admin email and starts background monitoring for auto-indexing
 */
googleDriveRouter.post('/configuration', requireAdmin, async (req: Request, res: Response) => {
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
    const tenantServiceAccount = await getConfigValue('GOOGLE_DRIVE_SERVICE_ACCOUNT', tenantId);
    if (!tenantServiceAccount) {
      return res.status(400).json({
        error: 'Service account not found. Please refresh the page and try again.',
      });
    }

    // Save admin email
    const success = await saveConfigValue('GOOGLE_DRIVE_ADMIN_EMAIL', adminEmail.trim(), tenantId);
    if (!success) {
      return res.status(500).json({ error: 'Failed to save admin email' });
    }

    logger.info('Google Drive configuration saved for tenant', {
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
      type: ConnectorType.GoogleDrive,
      externalId: serviceAccountClientId,
      externalMetadata: {
        admin_email: adminEmail.trim(),
      },
      updateMetadataOnExisting: true,
    });

    // Update Notion CRM - Google Drive integration connected
    await updateIntegrationStatus(tenantId, 'google-drive', true);

    // Start background monitoring job that will auto-start indexing when ready
    handleGoogleDriveConfigurationSaved(tenantId);

    res.json({
      success: true,
      message:
        'Configuration saved. Indexing will start automatically once domain delegation is configured.',
    });
  } catch (error) {
    logger.error('Error saving Google Drive configuration', error);
    res.status(500).json({ error: 'Failed to save configuration' });
  }
});

/**
 * GET /api/google-drive/status
 * Returns combined setup and indexing status
 */
googleDriveRouter.get(
  '/status',
  requireAdmin,
  dbMiddleware,
  async (req: Request, res: Response) => {
    try {
      const tenantId = req.user?.tenantId;
      if (!tenantId) {
        return res.status(400).json({ error: 'No tenant found for organization' });
      }

      // Check setup status
      const adminEmail = await getConfigValue('GOOGLE_DRIVE_ADMIN_EMAIL', tenantId);
      const tenantServiceAccount = await getConfigValue('GOOGLE_DRIVE_SERVICE_ACCOUNT', tenantId);
      const isSetup = !!(adminEmail && tenantServiceAccount);

      // Default indexing state
      let indexingStatus: 'pending' | 'indexing' | 'active' | 'error' = 'pending';
      const stats: Record<string, number> = {};
      let total = 0;
      let lastUpdated: string | null = null;
      const errorMessage: string | null = null;

      if (isSetup) {
        // Get indexing status from database
        const db = req.db;
        if (db) {
          try {
            // Query document stats
            const query = `
            SELECT
              ia.metadata->>'mime_type' as mime_type,
              COUNT(DISTINCT d.id) as count,
              MAX(d.updated_at) as latest_updated
            FROM ingest_artifact ia
            INNER JOIN documents d ON d.id = 'google_drive_file_' || ia.entity_id
            WHERE ia.entity = 'google_drive_file'
              AND d.source = 'google_drive'
            GROUP BY ia.metadata->>'mime_type'
            ORDER BY count DESC
          `;

            const result = await db.query(query);

            // Map MIME types to user-friendly categories
            const categoryMap: Record<string, string> = {
              'application/vnd.google-apps.document': 'Document',
              'application/vnd.google-apps.spreadsheet': 'Spreadsheet',
              'application/vnd.google-apps.presentation': 'Presentation',
              'application/pdf': 'PDF',
              'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Document',
              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Spreadsheet',
              'application/vnd.openxmlformats-officedocument.presentationml.presentation':
                'Presentation',
              'text/csv': 'Spreadsheet',
              'application/msword': 'Document',
              'application/vnd.ms-excel': 'Spreadsheet',
              'application/vnd.ms-powerpoint': 'Presentation',
            };

            let latestTimestamp: Date | null = null;

            for (const row of result.rows) {
              const mimeType = row.mime_type || 'Other';
              const category = categoryMap[mimeType] || 'Other';
              stats[category] = (stats[category] || 0) + parseInt(row.count);
              total += parseInt(row.count);

              if (row.latest_updated) {
                const rowDate = new Date(row.latest_updated);
                if (!latestTimestamp || rowDate > latestTimestamp) {
                  latestTimestamp = rowDate;
                }
              }
            }

            lastUpdated = latestTimestamp?.toISOString() || null;

            // Determine indexing status based on data
            if (total > 0) {
              // Check if indexing is currently active (recent updates)
              const isRecent =
                latestTimestamp && Date.now() - latestTimestamp.getTime() < 5 * 60 * 1000; // 5 minutes

              indexingStatus = isRecent ? 'indexing' : 'active';
            }
            // If no documents yet, status remains 'pending' until documents appear
          } catch (dbError) {
            logger.error('Error querying indexing status', dbError);
            // Continue with default status
          }
        }
      }

      const response: {
        isSetup: boolean;
        indexing: {
          status: 'pending' | 'indexing' | 'active' | 'error';
          stats: Record<string, number>;
          total: number;
          lastUpdated: string | null;
          error?: string;
        };
      } = {
        isSetup,
        indexing: {
          status: indexingStatus,
          stats,
          total,
          lastUpdated,
        },
      };

      if (errorMessage) {
        response.indexing.error = errorMessage;
      }

      res.json(response);
    } catch (error) {
      logger.error('Error getting Google Drive status', error);
      res.status(500).json({ error: 'Failed to get status' });
    }
  }
);

// Legacy endpoint for backwards compatibility
googleDriveRouter.get('/setup-status', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    // Check if tenant has their own service account and admin email configured
    const adminEmail = await getConfigValue('GOOGLE_DRIVE_ADMIN_EMAIL', tenantId);
    const tenantServiceAccount = await getConfigValue('GOOGLE_DRIVE_SERVICE_ACCOUNT', tenantId);

    const isSetup = !!adminEmail && !!tenantServiceAccount;
    let clientId = null;

    if (tenantServiceAccount) {
      try {
        const serviceAccountData = tenantServiceAccount as { client_id: string };
        clientId = serviceAccountData.client_id;
      } catch (error) {
        logger.error('Error parsing tenant service account data in legacy endpoint', error, {
          tenant_id: tenantId,
        });
      }
    }

    res.json({
      isSetup,
      adminEmail: isSetup ? adminEmail : null,
      clientId,
    });
  } catch (error) {
    logger.error('Error checking Google Drive setup status', error);
    res.status(500).json({ error: 'Failed to check setup status' });
  }
});

/**
 * Handle Google Drive configuration save event by monitoring for delegation setup
 * and auto-starting indexing when ready
 */
async function handleGoogleDriveConfigurationSaved(tenantId: string): Promise<void> {
  try {
    logger.info('Google Drive configuration saved, starting monitoring', { tenant_id: tenantId });

    // Start background monitoring with retries
    const maxAttempts = 20; // ~10 minutes with 30s intervals
    let attempts = 0;

    const checkAndStartIndexing = async () => {
      attempts++;

      try {
        // Try to verify Google API access by attempting a test call
        const adminEmail = await getConfigValue('GOOGLE_DRIVE_ADMIN_EMAIL', tenantId);
        const serviceAccount = await getConfigValue('GOOGLE_DRIVE_SERVICE_ACCOUNT', tenantId);

        if (!adminEmail || !serviceAccount) {
          logger.info('Missing configuration, stopping monitoring', { tenant_id: tenantId });
          return;
        }

        // For now, we'll just trigger the discovery job after a delay
        // In production, you'd want to test the actual Google API access here
        // by attempting to list users or drives with the service account

        if (isSqsConfigured()) {
          const sqsClient = getSqsClient();
          logger.info('Auto-triggering Google Drive discovery job', { tenant_id: tenantId });

          await sqsClient.sendGoogleDriveDiscoveryJob(tenantId);
          logger.info('Google Drive discovery job auto-started', { tenant_id: tenantId });
          return; // Success, stop monitoring
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
        setTimeout(() => checkAndStartIndexing(), 30000); // Check again in 30 seconds
      } else {
        logger.warn('Delegation setup timeout', { tenant_id: tenantId, maxAttempts });
      }
    };

    // Start checking after initial delay to allow for delegation propagation
    setTimeout(() => checkAndStartIndexing(), 30000); // Start checking after 30 seconds
  } catch (error) {
    logger.error('Error handling Google Drive configuration save', error, {
      tenant_id: tenantId,
    });
  }
}

export { googleDriveRouter };
