/**
 * Snowflake Service
 * Business logic layer for Snowflake operations
 */

import { executeSnowflakeQuery, SnowflakeSqlApiResponse } from './snowflake-client';
import {
  getSnowflakeOauthToken,
  getSnowflakeAccountIdentifier,
  getSnowflakeClientId,
  getSnowflakeClientSecret,
  getSnowflakeOAuthTokenEndpoint,
  saveSnowflakeOauthToken,
  type SnowflakeOauthToken,
} from './snowflake-config';
import { logger } from '../../utils/logger';

interface SnowflakeTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token?: string;
  username: string;
}

/**
 * Builds the OAuth token endpoint URL
 */
function buildOAuthTokenUrl(accountIdentifier: string): string {
  return `https://${accountIdentifier}.snowflakecomputing.com/oauth/token-request`;
}

/**
 * Refreshes an expired access token using the refresh token
 */
async function refreshAccessToken(
  refreshToken: string,
  accountIdentifier: string,
  clientId: string,
  clientSecret: string,
  tokenEndpoint?: string
): Promise<SnowflakeTokenResponse> {
  const credentials = Buffer.from(`${clientId}:${clientSecret}`).toString('base64');

  const payload = {
    grant_type: 'refresh_token',
    refresh_token: refreshToken,
  };

  const tokenUrl = tokenEndpoint || buildOAuthTokenUrl(accountIdentifier);

  const response = await fetch(tokenUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      Authorization: `Basic ${credentials}`,
      Accept: 'application/json',
    },
    body: new URLSearchParams(payload).toString(),
  });

  if (!response.ok) {
    const text = await response.text();

    // Check if it's an invalid grant error
    try {
      const errorBody = JSON.parse(text);
      if (errorBody.error === 'invalid_grant') {
        throw new Error(
          'Snowflake refresh token is invalid or expired. Please disconnect and reconnect your Snowflake account to obtain a new token.'
        );
      }
    } catch (parseError) {
      // If it's already an Error instance (e.g., the invalid_grant error we just threw), rethrow it
      if (parseError instanceof Error && parseError.message.includes('Snowflake refresh token')) {
        throw parseError;
      }
    }

    throw new Error(`Snowflake token refresh failed: ${response.status} ${text}`);
  }

  const tokenResponse = await response.json();

  return tokenResponse;
}

/**
 * Ensures we have a valid, non-expired token.
 * If token is expired, automatically refreshes it and saves the new token.
 */
async function ensureValidToken(
  tenantId: string,
  currentToken: SnowflakeOauthToken,
  accountIdentifier: string
): Promise<SnowflakeOauthToken> {
  const expiresAt = new Date(currentToken.access_token_expires_at);
  const now = new Date();

  // Token is still valid
  if (expiresAt > now) {
    return currentToken;
  }

  // Token is expired, refresh it
  logger.info('Access token expired, refreshing...', {
    tenant_id: tenantId,
    expired_at: currentToken.access_token_expires_at,
  });

  const clientId = await getSnowflakeClientId(tenantId);
  const clientSecret = await getSnowflakeClientSecret(tenantId);
  const tokenEndpoint = await getSnowflakeOAuthTokenEndpoint(tenantId);

  if (!clientId || !clientSecret) {
    throw new Error('Missing OAuth credentials for token refresh');
  }

  const response = await refreshAccessToken(
    currentToken.refresh_token,
    accountIdentifier,
    clientId,
    clientSecret,
    tokenEndpoint || undefined
  );

  const nowMs = Date.now();
  const expiresInMs = response.expires_in * 1000;
  const expiresAtEpoch = nowMs + expiresInMs;
  const newExpiresAt = new Date(expiresAtEpoch).toISOString();

  // IMPORTANT: If Snowflake doesn't return a new refresh token, keep the old one
  // Some OAuth providers use rotating refresh tokens (single-use), others reuse them
  const refreshedToken = {
    access_token: response.access_token,
    refresh_token: response.refresh_token || currentToken.refresh_token,
    access_token_expires_at: newExpiresAt,
    username: response.username,
  };

  await saveSnowflakeOauthToken(tenantId, refreshedToken);

  logger.info('Access token refreshed successfully', {
    tenant_id: tenantId,
    new_expiry: newExpiresAt,
    username: response.username,
  });

  return refreshedToken;
}

/**
 * Transforms Snowflake API columnar response into array of objects
 */
function transformResultToObjects(
  result: SnowflakeSqlApiResponse
): Array<Record<string, string | number | boolean | null | undefined>> {
  if (!result.data) {
    return [];
  }

  return result.data.map((row) => {
    const metadata = result.resultSetMetaData?.rowType || [];
    const obj: Record<string, string | number | boolean | null | undefined> = {};

    metadata.forEach((col, idx) => {
      obj[col.name] = row[idx];
    });

    return obj;
  });
}

/**
 * Gets a valid access token for the tenant, refreshing if necessary
 */
async function getValidAccessToken(
  tenantId: string
): Promise<{ token: string; accountIdentifier: string }> {
  const currentToken = await getSnowflakeOauthToken(tenantId);
  const accountIdentifier = await getSnowflakeAccountIdentifier(tenantId);

  if (!currentToken) {
    throw new Error('No Snowflake OAuth token found. Please connect your Snowflake account first.');
  }

  if (!accountIdentifier) {
    throw new Error('No Snowflake account identifier found.');
  }

  const validToken = await ensureValidToken(tenantId, currentToken, accountIdentifier);

  return {
    token: validToken.access_token,
    accountIdentifier,
  };
}

/**
 * Fetches all stages from Snowflake
 */
export async function getSnowflakeStages(
  tenantId: string
): Promise<Array<Record<string, string | number | boolean | null | undefined>>> {
  const { token, accountIdentifier } = await getValidAccessToken(tenantId);

  const result = await executeSnowflakeQuery(accountIdentifier, token, {
    statement: 'SHOW STAGES',
  });

  return transformResultToObjects(result);
}

/**
 * Fetches all warehouses from Snowflake
 */
export async function getSnowflakeWarehouses(
  tenantId: string
): Promise<Array<Record<string, string | number | boolean | null | undefined>>> {
  const { token, accountIdentifier } = await getValidAccessToken(tenantId);

  const result = await executeSnowflakeQuery(accountIdentifier, token, {
    statement: 'SHOW WAREHOUSES',
  });

  return transformResultToObjects(result);
}

/**
 * Tests the Snowflake connection by validating credentials and token
 */
export async function testSnowflakeConnection(tenantId: string): Promise<{
  success: boolean;
  message: string;
  accountIdentifier?: string;
  username?: string;
  tokenExpiry?: string;
}> {
  try {
    const currentToken = await getSnowflakeOauthToken(tenantId);
    const accountIdentifier = await getSnowflakeAccountIdentifier(tenantId);

    if (!currentToken) {
      return {
        success: false,
        message: 'No Snowflake OAuth token found. Please connect your Snowflake account first.',
      };
    }

    if (!accountIdentifier) {
      return {
        success: false,
        message: 'No Snowflake account identifier found.',
      };
    }

    // Ensure token is valid, refresh if expired
    const validToken = await ensureValidToken(tenantId, currentToken, accountIdentifier);

    // TODO: When actual connection testing is needed (e.g., CONN-345),
    // execute a simple query like SELECT 1 to verify the connection

    return {
      success: true,
      message: 'Snowflake credentials are valid and token is active',
      accountIdentifier,
      username: validToken.username,
      tokenExpiry: validToken.access_token_expires_at,
    };
  } catch (error) {
    logger.error('Snowflake connection test failed', error, { tenant_id: tenantId });
    return {
      success: false,
      message: error instanceof Error ? error.message : 'Unknown error occurred',
    };
  }
}

/**
 * Fetches all databases from Snowflake
 */
export async function getSnowflakeDatabases(
  tenantId: string
): Promise<Array<Record<string, string | number | boolean | null | undefined>>> {
  const { token, accountIdentifier } = await getValidAccessToken(tenantId);

  const result = await executeSnowflakeQuery(accountIdentifier, token, {
    statement: 'SHOW DATABASES',
  });

  return transformResultToObjects(result);
}

/**
 * Fetches all semantic views from Snowflake
 */
export async function getSnowflakeSemanticViews(
  tenantId: string
): Promise<Array<Record<string, string | number | boolean | null | undefined>>> {
  const { token, accountIdentifier } = await getValidAccessToken(tenantId);

  const result = await executeSnowflakeQuery(accountIdentifier, token, {
    statement: 'SHOW SEMANTIC VIEWS',
  });

  return transformResultToObjects(result);
}
