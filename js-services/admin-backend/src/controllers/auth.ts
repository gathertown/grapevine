import { Router, Request, Response } from 'express';
import { requireUser } from '../middleware/auth-middleware.js';
import { getTenantInfoById } from '../control-db.js';
import { logger } from '../utils/logger.js';
import { getAllConfigValues } from '../config/index.js';
import { z } from 'zod';

const authRouter = Router();

// Test endpoint for authentication
authRouter.get('/test', (req: Request, res: Response) => {
  res.json({
    message: 'Hello from the backend!',
    authenticated: !!req.user,
    user: req.user ? { id: req.user.id, email: req.user.email } : null,
  });
});

const tenantStatusQuerySchema = z.object({
  expand: z
    .string()
    .optional()
    .transform(
      (s) =>
        s
          ?.split(',')
          .map((v) => v.trim())
          .filter(Boolean) ?? []
    )
    .refine((arr) => arr.every((v) => ['sources'].includes(v)), {
      message: 'Invalid expand value',
    }),
});

/**
 * Get tenant provisioning status
 * Returns the current provisioning status of the user's tenant
 */
const tenantStatusHandler = async (req: Request, res: Response) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.json({ status: null, message: 'No tenant found for user' });
    }

    // Parse and validate query params with Zod
    const parsed = tenantStatusQuerySchema.safeParse(req.query);
    if (!parsed.success) {
      return res
        .status(400)
        .json({ error: 'Invalid query parameters', details: parsed.error.flatten() });
    }
    const expand = new Set(parsed.data.expand);

    const tenantInfo = await getTenantInfoById(tenantId);
    if (!tenantInfo) {
      return res.json({
        status: null,
        message: 'Could not get status for tenant',
      });
    }

    // Map state to status and provide appropriate message
    const { status, message } = (() => {
      switch (tenantInfo.state) {
        case 'provisioned':
          return { status: 'provisioned', message: 'Tenant is provisioned and ready' };
        case 'error':
          return {
            status: 'error',
            message: tenantInfo.errorMessage || 'Tenant provisioning failed',
          };
        default:
          return { status: 'pending', message: 'Tenant is being provisioned' };
      }
    })();

    // Base response
    const baseResponse: Record<string, unknown> = {
      status,
      tenantId: tenantInfo.tenantId,
      message,
      errorMessage: tenantInfo.state === 'error' ? tenantInfo.errorMessage : undefined,
    };

    // Optionally include data source configuration status when provisioned
    if (status === 'provisioned' && tenantInfo.tenantId && expand.has('sources')) {
      try {
        const config = await getAllConfigValues(tenantInfo.tenantId);

        const str = (v: unknown): string =>
          typeof v === 'string' ? v : v == null ? '' : String(v);

        // Slack
        const slackSigningSecret = str(config.SLACK_SIGNING_SECRET).trim();
        const slackBotToken = str(config.SLACK_BOT_TOKEN).trim();
        const slackBotConfigured =
          /^[a-fA-F0-9]{32}$/.test(slackSigningSecret) &&
          slackBotToken.startsWith('xoxb-') &&
          slackBotToken.length > 10;

        const uploadsJson = str(config.SLACK_EXPORTS_UPLOADED);
        let slackExportsUploaded = 0;
        try {
          const arr = uploadsJson ? (JSON.parse(uploadsJson) as unknown[]) : [];
          slackExportsUploaded = Array.isArray(arr) ? arr.length : 0;
        } catch {
          slackExportsUploaded = 0;
        }

        // Notion
        const notionToken = str(config.NOTION_TOKEN).trim();
        const notionWebhookSecret = str(config.NOTION_WEBHOOK_SECRET).trim();
        const notionConfigured = notionToken.startsWith('ntn_') && notionToken.length > 10;
        const notionComplete = notionConfigured && notionWebhookSecret.length > 0;

        // GitHub
        const githubToken = str(config.GITHUB_TOKEN).trim();
        const githubTokenValid =
          (githubToken.startsWith('ghp_') || githubToken.startsWith('github_pat_')) &&
          githubToken.length > 10;
        const githubSetupComplete = str(config.GITHUB_SETUP_COMPLETE).trim() === 'true';
        const githubComplete = githubTokenValid && githubSetupComplete;

        // Linear
        const linearApiKey = str(config.LINEAR_API_KEY).trim();
        const linearWebhookSecret = str(config.LINEAR_WEBHOOK_SECRET).trim();
        const linearConfigured = linearApiKey.length > 10;
        const linearComplete = linearConfigured && linearWebhookSecret.length > 0;

        // Google Drive
        const googleDriveAdminEmail = str(config.GOOGLE_DRIVE_ADMIN_EMAIL).trim();
        const googleDriveComplete = googleDriveAdminEmail.length > 0;

        baseResponse.sources = {
          slack: {
            configured: slackBotConfigured,
            exportsUploaded: slackExportsUploaded,
            complete: slackBotConfigured && slackExportsUploaded > 0,
          },
          notion: {
            configured: notionConfigured,
            complete: notionComplete,
          },
          github: {
            configured: githubTokenValid,
            complete: githubComplete,
          },
          linear: {
            configured: linearConfigured,
            complete: linearComplete,
          },
          googledrive: {
            configured: googleDriveComplete,
            complete: googleDriveComplete,
          },
        };
      } catch (e) {
        // If config fetch fails, still return base response
        console.warn('Failed to expand tenant status with sources:', e);
      }
    }

    res.json(baseResponse);
  } catch (error) {
    logger.error('Error getting tenant status', error, {
      operation: 'get-tenant-status',
    });
    res.status(500).json({
      error: 'Failed to get tenant status',
      details: error instanceof Error ? error.message : 'Unknown error',
    });
  }
};

// Make it so tenant status can be called with GET or POST. Normally GET would be fine, but Gather
// other requires body params and must therefore be POSTed.
authRouter
  .route('/tenant/status')
  .get(requireUser, tenantStatusHandler)
  .post(requireUser, tenantStatusHandler);

export { authRouter };
