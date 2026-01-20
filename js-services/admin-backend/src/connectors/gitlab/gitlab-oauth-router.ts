import { Router } from 'express';
import { requireUser } from '../../middleware/auth-middleware';
import { saveConfigValue, deleteConfigValue, getConfigValue } from '../../config';
import { logger } from '../../utils/logger';
import { installConnector, uninstallConnector } from '../../dal/connector-utils.js';
import { ConnectorType } from '../../types/connector.js';
import { isSqsConfigured, getSqsClient } from '../../jobs/sqs-client.js';

// GitLab OAuth configuration (gitlab.com only)
const GITLAB_TOKEN_URL = 'https://gitlab.com/oauth/token';
const GITLAB_USER_URL = 'https://gitlab.com/api/v4/user';

// Config keys for storing GitLab OAuth tokens
const GITLAB_CONFIG_KEY_ACCESS_TOKEN = 'GITLAB_ACCESS_TOKEN';
const GITLAB_CONFIG_KEY_REFRESH_TOKEN = 'GITLAB_REFRESH_TOKEN';
const GITLAB_CONFIG_KEY_TOKEN_TYPE = 'GITLAB_TOKEN_TYPE';

const gitlabOAuthRouter = Router();

function getGitLabClientId(): string {
  const value = process.env.GITLAB_CLIENT_ID;
  if (!value) {
    throw new Error('GITLAB_CLIENT_ID environment variable is required for GitLab OAuth');
  }
  return value;
}

function getGitLabClientSecret(): string {
  const value = process.env.GITLAB_CLIENT_SECRET;
  if (!value) {
    throw new Error('GITLAB_CLIENT_SECRET environment variable is required for GitLab OAuth');
  }
  return value;
}

/**
 * POST /api/gitlab/callback
 * Handles OAuth callback and exchanges code for tokens
 */
gitlabOAuthRouter.post('/callback', requireUser, async (req, res) => {
  try {
    const { code, state } = req.body;
    const tenantId = req.user?.tenantId;

    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    if (!code || !state) {
      return res.status(400).json({ error: 'Missing code or state' });
    }

    logger.info('Processing GitLab OAuth callback', {
      tenantId,
      hasCode: !!code,
      hasState: !!state,
    });

    // Get redirect URI from the request origin
    const redirectUri = req.body.redirectUri;
    if (!redirectUri) {
      return res.status(400).json({ error: 'Missing redirectUri' });
    }

    // Exchange code for tokens using shared credentials from environment
    // GitLab uses form-urlencoded format for token exchange
    const tokenPayload = new URLSearchParams({
      client_id: getGitLabClientId(),
      client_secret: getGitLabClientSecret(),
      code,
      grant_type: 'authorization_code',
      redirect_uri: redirectUri,
    });

    const tokenResponse = await fetch(GITLAB_TOKEN_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        Accept: 'application/json',
      },
      body: tokenPayload.toString(),
    });

    if (!tokenResponse.ok) {
      const errorText = await tokenResponse.text();
      logger.error('GitLab token exchange failed', {
        status: tokenResponse.status,
        statusText: tokenResponse.statusText,
        error: errorText,
        tenantId,
      });
      throw new Error(`Failed to exchange code for tokens: ${tokenResponse.status}`);
    }

    const tokens = await tokenResponse.json();

    // Validate token response structure
    if (!tokens || typeof tokens !== 'object') {
      logger.error('Invalid token response from GitLab', { tenantId });
      throw new Error('Invalid token response structure');
    }

    if (!tokens.access_token || typeof tokens.access_token !== 'string') {
      logger.error('Missing or invalid access token in GitLab response', { tenantId });
      throw new Error('Missing access token in response');
    }

    // Log token response for debugging
    logger.info('GitLab token exchange response', {
      tenantId,
      hasAccessToken: !!tokens.access_token,
      hasRefreshToken: !!tokens.refresh_token,
      tokenType: tokens.token_type,
      expiresIn: tokens.expires_in,
    });

    // Save tokens to SSM Parameter Store
    await saveConfigValue(GITLAB_CONFIG_KEY_ACCESS_TOKEN, tokens.access_token, tenantId);

    if (tokens.refresh_token && typeof tokens.refresh_token === 'string') {
      await saveConfigValue(GITLAB_CONFIG_KEY_REFRESH_TOKEN, tokens.refresh_token, tenantId);
    }

    if (tokens.token_type && typeof tokens.token_type === 'string') {
      await saveConfigValue(GITLAB_CONFIG_KEY_TOKEN_TYPE, tokens.token_type, tenantId);
    }

    // Get user information from GitLab API for connector metadata
    interface GitLabUserMetadata {
      user_id: number;
      username: string;
      name?: string;
      email?: string;
      avatar_url?: string;
      web_url?: string;
      token_type?: string;
      [key: string]: unknown;
    }

    const userResponse = await fetch(GITLAB_USER_URL, {
      headers: {
        Authorization: `Bearer ${tokens.access_token}`,
        Accept: 'application/json',
      },
    });

    if (!userResponse.ok) {
      const errorText = await userResponse.text();
      logger.error('Failed to retrieve GitLab user metadata', {
        tenantId,
        status: userResponse.status,
        statusText: userResponse.statusText,
        error: errorText,
      });
      throw new Error(`Failed to retrieve GitLab user metadata: ${userResponse.status}`);
    }

    const userData = await userResponse.json();

    const userId = userData.id;
    if (!userId) {
      logger.error('GitLab user_id not found in /user response', {
        tenantId,
        userDataKeys: Object.keys(userData),
      });
      throw new Error('GitLab user_id not found in API response');
    }

    const userMetadata: GitLabUserMetadata = {
      user_id: userId,
      username: userData.username,
      name: userData.name,
      email: userData.email,
      avatar_url: userData.avatar_url,
      web_url: userData.web_url,
      token_type: tokens.token_type,
    };

    logger.info('Retrieved GitLab user metadata', {
      tenantId,
      userId: userMetadata.user_id,
      username: userMetadata.username,
    });

    // Create or update connector installation record
    const externalId = String(userMetadata.user_id);
    await installConnector({
      tenantId,
      type: ConnectorType.GitLab,
      externalId,
      externalMetadata: userMetadata,
      updateMetadataOnExisting: true,
    });

    // Trigger GitLab backfill and send Slack notification
    if (isSqsConfigured()) {
      try {
        const sqsClient = getSqsClient();
        await sqsClient.sendGitLabBackfillIngestJob(tenantId);
        logger.info('GitLab backfill job triggered', { tenantId });
      } catch (sqsError) {
        // Don't fail the OAuth flow if backfill trigger fails
        logger.error('Failed to trigger GitLab backfill job', sqsError, { tenantId });
      }
    } else {
      logger.warn('SQS not configured - skipping GitLab backfill', { tenantId });
    }

    logger.info('GitLab OAuth flow completed successfully', { tenantId, externalId });

    return res.json({ success: true, redirectTo: null });
  } catch (error) {
    logger.error('GitLab OAuth callback failed', error);
    return res.status(500).json({ error: 'OAuth callback failed' });
  }
});

/**
 * GET /api/gitlab/status
 * Get GitLab connection status
 */
gitlabOAuthRouter.get('/status', requireUser, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    // Check if we have an access token stored
    const accessToken = await getConfigValue(GITLAB_CONFIG_KEY_ACCESS_TOKEN, tenantId);
    const hasAccessToken = !!accessToken;

    // If connected, try to get user info for display
    let username: string | undefined;
    let name: string | undefined;

    if (hasAccessToken) {
      try {
        const userResponse = await fetch(GITLAB_USER_URL, {
          headers: {
            Authorization: `Bearer ${accessToken}`,
            Accept: 'application/json',
          },
        });

        if (userResponse.ok) {
          const userData = await userResponse.json();
          username = userData.username;
          name = userData.name;
        }
      } catch (error) {
        // Ignore errors fetching user info - just return connected status
        logger.warn('Failed to fetch GitLab user info for status', { tenantId, error });
      }
    }

    return res.json({
      connected: hasAccessToken,
      configured: hasAccessToken,
      username,
      name,
    });
  } catch (error) {
    logger.error('Failed to fetch GitLab status', error);
    return res.status(500).json({ error: 'Failed to fetch status' });
  }
});

/**
 * DELETE /api/gitlab/disconnect
 * Disconnect GitLab
 */
gitlabOAuthRouter.delete('/disconnect', requireUser, async (req, res) => {
  try {
    const tenantId = req.user?.tenantId;
    if (!tenantId) {
      return res.status(400).json({ error: 'No tenant found' });
    }

    // Delete GitLab OAuth tokens
    await deleteConfigValue(GITLAB_CONFIG_KEY_ACCESS_TOKEN, tenantId);
    await deleteConfigValue(GITLAB_CONFIG_KEY_REFRESH_TOKEN, tenantId);
    await deleteConfigValue(GITLAB_CONFIG_KEY_TOKEN_TYPE, tenantId);

    // Mark connector as disconnected in connector_installations table
    await uninstallConnector(tenantId, ConnectorType.GitLab);

    logger.info('GitLab disconnected', { tenantId });
    return res.json({ success: true });
  } catch (error) {
    logger.error('Failed to disconnect GitLab', error);
    return res.status(500).json({ error: 'Failed to disconnect' });
  }
});

export { gitlabOAuthRouter };
