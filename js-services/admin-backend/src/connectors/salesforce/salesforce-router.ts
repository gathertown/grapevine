import express, { Router, Request, Response } from 'express';
import { requireAdmin } from '../../middleware/auth-middleware.js';
import { dbMiddleware } from '../../middleware/db-middleware.js';
import { saveConfigValue } from '../../config/index.js';
import { logger } from '../../utils/logger.js';
import { updateTenantHasSalesforceConnected } from '../../control-db.js';
import { getSqsClient, isSqsConfigured } from '../../jobs/sqs-client.js';
import { updateIntegrationStatus } from '../../utils/notion-crm.js';
import { installConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';

const salesforceRouter = Router();

/**
 * POST /api/salesforce/oauth/token-proxy
 * Proxy endpoint for our clients to talk to Salesforce's token endpoint
 */
salesforceRouter.post(
  '/oauth/token-proxy',
  // `oidc-client-ts` sends form-encoded data
  express.urlencoded({ extended: true }),
  async (req: Request, res: Response) => {
    try {
      let requestBody: string;

      if (typeof req.body === 'string' || typeof req.body === 'object') {
        const params = new URLSearchParams(req.body);
        params.set('client_secret', process.env.SALESFORCE_CONSUMER_SECRET || '');
        requestBody = params.toString();
      } else {
        throw new Error('Unexpected request body format');
      }

      // Forward the token request to Salesforce's actual token endpoint
      const tokenResponse = await fetch('https://login.salesforce.com/services/oauth2/token', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: requestBody,
      });

      const tokenData = await tokenResponse.text();

      logger.info('Salesforce token response', {
        status: tokenResponse.status,
        body: tokenData,
        headers: Object.fromEntries(tokenResponse.headers.entries()),
      });

      if (!tokenResponse.ok) {
        // Forward error responses as-is
        res
          .status(tokenResponse.status)
          .set('Content-Type', tokenResponse.headers.get('content-type') || 'application/json')
          .send(tokenData);
        return;
      }

      // Parse and potentially modify the success response for oidc-client-ts compatibility
      const tokenJson = JSON.parse(tokenData);

      // Extract organization and user IDs from Salesforce identity URL
      // Format: https://login.salesforce.com/id/{ORG_ID}/{USER_ID}
      const identityUrl = tokenJson.id || '';
      const urlParts = identityUrl.split('/');
      const orgId = urlParts[4] || ''; // Organization ID
      const userId = urlParts[5] || ''; // User ID

      // Create a simple ID token with Salesforce-specific fields in the profile
      // This allows oidc-client-ts to expose them via user.profile
      const idTokenPayload = {
        iss: 'https://login.salesforce.com',
        sub: userId, // Use actual user ID as subject
        aud: tokenJson.client_id,
        exp: Math.floor(Date.now() / 1000) + 3600, // 1 hour
        iat: Math.floor(Date.now() / 1000),
        // Include Salesforce-specific fields in the profile
        instance_url: tokenJson.instance_url,
        org_id: orgId,
        user_id: userId,
      };

      // Create a simple unsigned JWT
      const header = { alg: 'none', typ: 'JWT' };
      const headerB64 = Buffer.from(JSON.stringify(header)).toString('base64url');
      const payloadB64 = Buffer.from(JSON.stringify(idTokenPayload)).toString('base64url');
      const idToken = `${headerB64}.${payloadB64}.`; // No signature for 'alg: none'

      const response = {
        access_token: tokenJson.access_token,
        token_type: tokenJson.token_type,
        expires_in: tokenJson.expires_in,
        refresh_token: tokenJson.refresh_token,
        scope: tokenJson.scope,
        id_token: idToken, // Include our custom ID token
      };

      res.status(200).set('Content-Type', 'application/json').json(response);
    } catch (error) {
      logger.error('Error in Salesforce token proxy', {
        error: error instanceof Error ? error.message : 'Unknown error',
      });
      res.status(500).json({ error: 'Token proxy error' });
    }
  }
);

/**
 * POST /api/salesforce/config
 * Save Salesforce config to config stores
 */
salesforceRouter.post('/config', requireAdmin, async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found for organization' });
    }

    const { refresh_token, instance_url, org_id, user_id } = req.body;
    if (!refresh_token || !instance_url || !org_id || !user_id) {
      return res.status(400).json({ error: 'Missing required parameter!' });
    }

    // First, mark the tenant as having a Salesforce connection. We'd rather have this
    // be incorrectly `true` than incorrectly `false`, since in the former case the user
    // won't realize anything is wrong (but we'll get lots of errors).
    await updateTenantHasSalesforceConnected(tenantId, true);

    await Promise.all([
      saveConfigValue('SALESFORCE_REFRESH_TOKEN', refresh_token, tenantId),
      saveConfigValue('SALESFORCE_INSTANCE_URL', instance_url, tenantId),
      saveConfigValue('SALESFORCE_ORG_ID', org_id, tenantId),
      saveConfigValue('SALESFORCE_USER_ID', user_id, tenantId),
    ]);

    logger.info('Salesforce config saved successfully', {
      tenant_id: tenantId,
      instance_url,
      org_id,
      user_id,
    });

    await installConnector({
      tenantId,
      type: ConnectorType.Salesforce,
      externalId: org_id,
      externalMetadata: {
        instance_url,
        user_id,
      },
      updateMetadataOnExisting: true,
    });

    // Update Notion CRM - Salesforce integration connected
    await updateIntegrationStatus(tenantId, 'salesforce', true);

    // Trigger Salesforce backfill job if SQS is configured
    if (isSqsConfigured()) {
      try {
        const sqsClient = getSqsClient();
        await sqsClient.sendSalesforceBackfillRootIngestJob(tenantId);
        logger.info('Successfully triggered Salesforce backfill job', {
          tenant_id: tenantId,
        });
      } catch (error) {
        logger.error('Failed to trigger Salesforce backfill job', {
          error: error instanceof Error ? error.message : 'Unknown error',
          tenant_id: tenantId,
        });
        // Don't fail the entire request if SQS job fails
        // The credentials are still saved successfully
      }
    } else {
      logger.error('SQS not configured, skipping Salesforce backfill job trigger', {
        tenant_id: tenantId,
      });
    }

    res.status(200).json({ success: true });
  } catch (error) {
    logger.error('Error in Salesforce OAuth token storage', {
      error: error instanceof Error ? error.message : 'Unknown error',
      tenant_id: req.user?.tenantId,
    });
    res.status(500).json({ error: 'Internal server error during token storage' });
  }
});

// Apply database middleware to all routes
salesforceRouter.use(dbMiddleware);

export { salesforceRouter };
