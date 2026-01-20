/// <reference path="./types/external-modules.d.ts" />

import { initializeNewRelicIfEnabled } from '@corporate-context/backend-common';
initializeNewRelicIfEnabled('grapevine-app');

// __dirname is available in CommonJS
import path from 'node:path';
import fs from 'node:fs';

import express, { Request, Response, Application } from 'express';
import cors from 'cors';
import { injectUserContext } from './middleware/auth-middleware.js';
import type { AuthUser } from './types/auth.js';
import { Pool } from 'pg';
import { closeAllConnections, dbMiddleware } from './middleware/db-middleware.js';
import { closeControlDbPool } from './control-db.js';
import { logger } from './utils/logger.js';
import { userContextMiddleware } from './middleware/user-context.js';

// Import route modules
import { healthRouter } from './controllers/health.js';
import { authRouter } from './controllers/auth.js';
import { billingRouter } from './controllers/billing.js';
import { companyRouter } from './controllers/company.js';
import { organizationsRouter } from './controllers/organizations.js';
import { invitationsRouter } from './controllers/invitations.js';
import { slackRouter } from './controllers/slack.js';
import { slackOAuthRouter } from './controllers/slack-oauth.js';
import { integrationsRouter } from './controllers/integrations.js';
import { googleDriveRouter } from './connectors/google-drive/google-drive-router.js';
import { googleEmailRouter } from './connectors/google-email/google-email-router.js';
import { salesforceRouter } from './connectors/salesforce/salesforce-router.js';
import { jiraRouter } from './connectors/jira/jira-router.js';
import { confluenceRouter } from './connectors/confluence/confluence-router.js';
import { githubRouter } from './connectors/github/github-router.js';
import { hubspotRouter } from './connectors/hubspot/hubspot-router.js';
import { gatherRouter } from './connectors/gather/gather-router.js';
import { statsRouter } from './controllers/stats.js';
import { webhooksRouter } from './controllers/webhooks.js';
import { mcpRouter } from './controllers/mcp.js';
import { sampleQuestionsRouter } from './controllers/sample-questions.js';
import { webhookSubscriptionsRouter } from './controllers/webhook-subscriptions.js';
import { apiKeysRouter } from './controllers/api-keys.js';
import { gongRouter } from './connectors/gong/gong-router.js';
import { trelloRouter } from './connectors/trello/trello-router.js';
import { featuresRouter } from './controllers/features.js';
import { zendeskRouter } from './connectors/zendesk/zendesk-router.js';
import { asanaRouter } from './connectors/asana/router/asana-router.js';
import { firefliesRouter } from './connectors/fireflies/fireflies-router.js';
import { pylonRouter } from './connectors/pylon/pylon-router.js';
import { snowflakeRouter } from './connectors/snowflake/router/snowflake-router.js';
import { linearOAuthRouter } from './connectors/linear/linear-router.js';
import { intercomRouter } from './connectors/intercom/intercom-router.js';
import { gitlabRouter } from './connectors/gitlab/gitlab-router.js';
import { attioRouter } from './connectors/attio/attio-router.js';
import { mondayRouter } from './connectors/monday/monday-router.js';
import { pipedriveRouter } from './connectors/pipedrive/pipedrive-router.js';
import { figmaRouter } from './connectors/figma/figma-router.js';
import { posthogRouter } from './connectors/posthog/posthog-router.js';
import { canvaRouter } from './connectors/canva/canva-router.js';
import { teamworkRouter } from './connectors/teamwork/teamwork-router.js';
import { clickupRouter } from './connectors/clickup/router/clickup-router.js';
import { customDataRouter } from './connectors/custom-data/custom-data-router.js';
import { exponentRouter } from './controllers/exponent.js';
import { connectorStatusRouter } from './controllers/connector-status.js';
import { mcpJwtRouter } from './controllers/mcp-jwt.js';
import { knowledgeBasesRouter } from './controllers/knowledge-bases.js';
import { evalCaptureRouter } from './controllers/eval-capture.js';
import { prReviewRouter } from './controllers/pr-review.js';

// Extend Express Request to include our custom properties
declare global {
  namespace Express {
    interface Request {
      user?: AuthUser | null;
      db?: Pool;
    }
  }
}

// Service clients are initialized in their respective modules

const app: Application = express();

// Function to get admin backend port with fallback priority
function getAdminBackendPort(): number {
  // Priority: ADMIN_WEB_UI_BACKEND_PORT env var > default 5002
  if (process.env.ADMIN_WEB_UI_BACKEND_PORT) {
    return parseInt(process.env.ADMIN_WEB_UI_BACKEND_PORT, 10);
  }

  // Default fallback
  return 5002;
}

const PORT = getAdminBackendPort();

// Webhooks need to be set up _before_ the JSON parsing middleware takes effect
app.use('/api/webhooks', webhooksRouter);

// Configuration management and authentication middleware are imported from their respective modules
app.use(cors());
app.use(express.json({ limit: '2mb' }));

// Apply user context injection globally - every route gets req.user (null if not authenticated)
app.use(injectUserContext);

// Apply user context to logging after authentication
app.use(userContextMiddleware);

// Apply database middleware globally - injects req.db for authenticated users
app.use(dbMiddleware);

// Mount route controllers
app.use('/api/billing', billingRouter);
app.use('/api/health', healthRouter);
app.use('/api', authRouter); // Mount auth routes directly under /api (includes /test, /tenant/status)
app.use('/api', companyRouter); // Mount company/config routes directly under /api
app.use('/api/organizations', organizationsRouter);
app.use('/api/invitations', invitationsRouter);

// TODO migrate these routes to gatekeeper
app.use('/api/slack-export', slackRouter); // Note: slack-export prefix, not slack/
app.use('/api/slack-exports', slackRouter); // For /list endpoint
app.use('/api/slack', slackOAuthRouter); // Slack OAuth routes
// end gatekeeper migration

app.use('/api', integrationsRouter); // Mount integrations routes directly under /api

// TODO migrate these routes to gatekeeper
app.use('/api/connector-status', connectorStatusRouter);
app.use('/api/google-drive', googleDriveRouter);
app.use('/api/google-email', googleEmailRouter);
app.use('/api/salesforce', salesforceRouter);
app.use('/api/jira', jiraRouter);
app.use('/api/confluence', confluenceRouter);
app.use('/api/github', githubRouter);
app.use('/api/hubspot', hubspotRouter);
app.use('/api/gong', gongRouter);
app.use('/api/trello', trelloRouter);
app.use('/api/linear', linearOAuthRouter);
app.use('/api/intercom', intercomRouter);
app.use('/api/gitlab', gitlabRouter);
app.use('/api/attio', attioRouter);
app.use('/api/gather', gatherRouter);
app.use('/api/zendesk', zendeskRouter);
app.use('/api/asana', asanaRouter);
app.use('/api/snowflake', snowflakeRouter);
app.use('/api/fireflies', firefliesRouter);
app.use('/api/clickup', clickupRouter);
app.use('/api/monday', mondayRouter);
app.use('/api/pipedrive', pipedriveRouter);
app.use('/api/figma', figmaRouter);
app.use('/api/posthog', posthogRouter);
app.use('/api/canva', canvaRouter);
app.use('/api/teamwork', teamworkRouter);
app.use('/api/pylon', pylonRouter);
app.use('/api/custom-data', customDataRouter);
app.use('/api/stats', statsRouter);
// end gatekeeper migration

app.use('/api/mcp', mcpRouter);
app.use('/api/sample-questions', sampleQuestionsRouter);
app.use('/api/webhook-subscriptions', webhookSubscriptionsRouter);
app.use('/api/api-keys', apiKeysRouter);
app.use('/api/features', featuresRouter);
app.use('/api/exponent', exponentRouter);
app.use('/api/mcp', mcpJwtRouter);
app.use('/api/knowledge-bases', knowledgeBasesRouter);
app.use('/api/eval', evalCaptureRouter);
app.use('/api/pr-review', prReviewRouter);

/**
 * Global Authentication System:
 *
 * EVERY ROUTE automatically gets req.user injected:
 * - req.user = authenticated user object (if valid token provided)
 * - req.user = null (if no token or invalid token)
 *
 * For routes requiring authentication, add `requireUser` middleware:
 * - Will return 401 error if req.user is null
 * - Use for sensitive operations that must be authenticated
 *
 * For routes working with optional auth, just use req.user directly:
 * - Check `if (req.user)` to provide different functionality
 * - No additional middleware needed
 *
 * Examples:
 * app.post("/api/sensitive", requireUser, handler)  // Auth required
 * app.get("/api/flexible", handler)                            // Auth optional, check req.user
 */

// Note: File uploads are handled via S3 multipart upload endpoints, not multer

// Function to rewrite asset paths in index.html to point to S3/CloudFront
// For self-hosted deployments: either don't set ASSETS_COMMIT_SHA (assets served from disk)
// or set both ASSETS_COMMIT_SHA and ASSETS_BASE_URL to your own CDN
function getRewrittenIndexHtml(): string {
  const indexPath = path.join(__dirname, '../public', 'index.html');
  // ASSETS_COMMIT_SHA is set as an environment variable at Docker build time
  const assetsCommitSha = process.env.ASSETS_COMMIT_SHA;
  const assetsBaseUrl = process.env.ASSETS_BASE_URL;

  // If ASSETS_COMMIT_SHA is not set, serve index.html as-is (local/self-hosted development)
  if (!assetsCommitSha || !assetsBaseUrl) {
    return fs.readFileSync(indexPath, 'utf-8');
  }

  // Read index.html
  let indexHtml = fs.readFileSync(indexPath, 'utf-8');

  // Rewrite asset paths: /assets/... -> {ASSETS_BASE_URL}/app/{short-sha}/assets/...
  // Uses short commit SHA (10 characters) to match Docker image tags and S3 paths
  const assetsBasePath = `${assetsBaseUrl}/app/${assetsCommitSha}`;
  // Match href="/assets/..." or src="/assets/..." (handles both single and double quotes, and any attributes before/after)
  indexHtml = indexHtml.replace(
    /(href|src)=(["'])(\/assets\/[^"']+)\2/g,
    (_match, attr, quote, assetPath) => {
      return `${attr}=${quote}${assetsBasePath}${assetPath}${quote}`;
    }
  );

  return indexHtml;
}

// Cache the rewritten HTML (computed once at startup)
let cachedIndexHtml: string | null = null;

// Explicitly handle /index.html requests BEFORE static middleware
// This ensures direct requests to /index.html also get the S3-rewritten version
// instead of being served raw from disk by express.static
app.get('/index.html', (_req: Request, res: Response) => {
  // If ASSETS_COMMIT_SHA is set, rewrite asset paths to point to S3
  if (process.env.ASSETS_COMMIT_SHA) {
    // Cache the rewritten HTML on first request
    if (cachedIndexHtml === null) {
      cachedIndexHtml = getRewrittenIndexHtml();
      logger.info('Rewrote index.html asset paths to CDN', {
        assetsCommitSha: process.env.ASSETS_COMMIT_SHA,
        assetsBaseUrl: process.env.ASSETS_BASE_URL,
      });
    }
    res.setHeader('Content-Type', 'text/html');
    res.send(cachedIndexHtml);
  } else {
    // Local development: serve index.html as-is
    res.sendFile(path.join(__dirname, '../public', 'index.html'));
  }
});

// Serve static files from the public directory (built frontend)
// Disable index option so that root requests (/) go to the catch-all handler
// which rewrites asset paths to point to S3 CDN
// Note: /index.html is handled above, so express.static won't serve it
app.use(express.static(path.join(__dirname, '../public'), { index: false }));

// Catch-all handler: send back React's index.html file for client-side routing
// But return 404 for requests to /assets/ that don't exist
app.get('*', (req: Request, res: Response) => {
  // If request is for assets, return 404 if not found by express.static
  if (req.path.startsWith('/assets/')) {
    return res.status(404).send('Not Found');
  }

  // For all other routes (client-side routing), serve index.html
  // If ASSETS_COMMIT_SHA is set, rewrite asset paths to point to S3
  if (process.env.ASSETS_COMMIT_SHA) {
    // Cache the rewritten HTML on first request
    if (cachedIndexHtml === null) {
      cachedIndexHtml = getRewrittenIndexHtml();
      logger.info('Rewrote index.html asset paths to CDN', {
        assetsCommitSha: process.env.ASSETS_COMMIT_SHA,
        assetsBaseUrl: process.env.ASSETS_BASE_URL,
      });
    }
    res.setHeader('Content-Type', 'text/html');
    res.send(cachedIndexHtml);
  } else {
    // Local development: serve index.html as-is
    res.sendFile(path.join(__dirname, '../public', 'index.html'));
  }
});

app.listen(PORT, () => {
  logger.info(`Admin backend server started successfully on port ${PORT}`, {
    port: PORT,
    environment: process.env.NODE_ENV || 'development',
    operation: 'server-start',
  });
});

// Shutdown handlers are imported at the top of the file

// Graceful shutdown handling
process.on('SIGINT', async () => {
  logger.info('Received SIGINT, shutting down gracefully', {
    operation: 'graceful-shutdown',
    signal: 'SIGINT',
  });
  try {
    // Close all tenant-specific database pools
    await closeAllConnections();
    // Close the control database pool
    await closeControlDbPool();
    logger.info('All database pools closed successfully');
  } catch (error) {
    logger.error('Error closing database pools during shutdown', error);
  }
  process.exit(0);
});

process.on('SIGTERM', async () => {
  logger.info('Received SIGTERM, shutting down gracefully');
  try {
    // Close all tenant-specific database pools
    await closeAllConnections();
    // Close the control database pool
    await closeControlDbPool();
    logger.info('All database pools closed successfully');
  } catch (error) {
    logger.error('Error closing database pools during shutdown', error);
  }
  process.exit(0);
});
