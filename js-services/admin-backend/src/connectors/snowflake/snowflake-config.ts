import { ConfigKey, ConfigValue } from '../../config/types';
import { saveConfigValue, getConfigValue } from '../../config';

const SNOWFLAKE_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY = 'SNOWFLAKE_OAUTH_TOKEN_PAYLOAD';
const SNOWFLAKE_ACCOUNT_IDENTIFIER_CONFIG_KEY = 'SNOWFLAKE_ACCOUNT_IDENTIFIER';
const SNOWFLAKE_CLIENT_ID_CONFIG_KEY = 'SNOWFLAKE_CLIENT_ID';
const SNOWFLAKE_CLIENT_SECRET_CONFIG_KEY = 'SNOWFLAKE_CLIENT_SECRET';
const SNOWFLAKE_OAUTH_AUTHORIZATION_ENDPOINT_CONFIG_KEY = 'SNOWFLAKE_OAUTH_AUTHORIZATION_ENDPOINT';
const SNOWFLAKE_OAUTH_TOKEN_ENDPOINT_CONFIG_KEY = 'SNOWFLAKE_OAUTH_TOKEN_ENDPOINT';
const SNOWFLAKE_INTEGRATION_NAME_CONFIG_KEY = 'SNOWFLAKE_INTEGRATION_NAME';

const SNOWFLAKE_SENSITIVE_KEYS = [
  SNOWFLAKE_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY,
  SNOWFLAKE_CLIENT_SECRET_CONFIG_KEY,
] as const;
const SNOWFLAKE_NON_SENSITIVE_KEYS = [
  SNOWFLAKE_ACCOUNT_IDENTIFIER_CONFIG_KEY,
  SNOWFLAKE_CLIENT_ID_CONFIG_KEY,
  SNOWFLAKE_OAUTH_AUTHORIZATION_ENDPOINT_CONFIG_KEY,
  SNOWFLAKE_OAUTH_TOKEN_ENDPOINT_CONFIG_KEY,
  SNOWFLAKE_INTEGRATION_NAME_CONFIG_KEY,
] as const;

/**
 * All Snowflake configuration keys
 * Used for operations like disconnect that need to clean up all config
 */
export const SNOWFLAKE_CONFIG_KEYS = [
  ...SNOWFLAKE_SENSITIVE_KEYS,
  ...SNOWFLAKE_NON_SENSITIVE_KEYS,
] as const;

interface SnowflakeOauthToken {
  access_token: string;
  refresh_token: string;
  access_token_expires_at: string;
  refresh_token_expires_at?: string;
  refresh_token_validity_seconds?: number;
  username: string;
}

const saveSnowflakeOauthToken = async (
  tenantId: string,
  token: SnowflakeOauthToken
): Promise<void> => {
  const tokenJson = JSON.stringify(token);

  const saved = await saveConfigValue(
    SNOWFLAKE_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY,
    tokenJson,
    tenantId
  );
  if (!saved) {
    throw new Error('Failed to save Snowflake OAuth token');
  }
};

const getSnowflakeOauthToken = async (tenantId: string): Promise<SnowflakeOauthToken | null> => {
  const tokenValue = await getConfigValue(SNOWFLAKE_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY, tenantId);
  if (!tokenValue) {
    return null;
  }

  // Handle both cases: SSM auto-parses JSON, so value might already be an object
  if (typeof tokenValue === 'object' && tokenValue !== null) {
    return tokenValue as SnowflakeOauthToken;
  }

  // If it's a string, parse it
  if (typeof tokenValue === 'string') {
    try {
      return JSON.parse(tokenValue) as SnowflakeOauthToken;
    } catch {
      return null;
    }
  }

  return null;
};

const saveSnowflakeAccountIdentifier = async (
  tenantId: string,
  accountIdentifier: string
): Promise<void> => {
  const saved = await saveConfigValue(
    SNOWFLAKE_ACCOUNT_IDENTIFIER_CONFIG_KEY,
    accountIdentifier,
    tenantId
  );
  if (!saved) {
    throw new Error('Failed to save Snowflake account identifier');
  }
};

const getSnowflakeAccountIdentifier = async (tenantId: string): Promise<string | null> => {
  const accountIdentifier = await getConfigValue(SNOWFLAKE_ACCOUNT_IDENTIFIER_CONFIG_KEY, tenantId);
  if (!accountIdentifier || typeof accountIdentifier !== 'string') {
    return null;
  }
  return accountIdentifier;
};

const saveSnowflakeClientId = async (tenantId: string, clientId: string): Promise<void> => {
  const saved = await saveConfigValue(SNOWFLAKE_CLIENT_ID_CONFIG_KEY, clientId, tenantId);
  if (!saved) {
    throw new Error('Failed to save Snowflake client ID');
  }
};

const getSnowflakeClientId = async (tenantId: string): Promise<string | null> => {
  const clientId = await getConfigValue(SNOWFLAKE_CLIENT_ID_CONFIG_KEY, tenantId);
  if (!clientId || typeof clientId !== 'string') {
    return null;
  }
  return clientId;
};

const saveSnowflakeClientSecret = async (tenantId: string, clientSecret: string): Promise<void> => {
  const saved = await saveConfigValue(SNOWFLAKE_CLIENT_SECRET_CONFIG_KEY, clientSecret, tenantId);
  if (!saved) {
    throw new Error('Failed to save Snowflake client secret');
  }
};

const getSnowflakeClientSecret = async (tenantId: string): Promise<string | null> => {
  const clientSecret = await getConfigValue(SNOWFLAKE_CLIENT_SECRET_CONFIG_KEY, tenantId);
  if (!clientSecret || typeof clientSecret !== 'string') {
    return null;
  }
  return clientSecret;
};

const saveSnowflakeOAuthAuthorizationEndpoint = async (
  tenantId: string,
  authorizationEndpoint: string
): Promise<void> => {
  const saved = await saveConfigValue(
    SNOWFLAKE_OAUTH_AUTHORIZATION_ENDPOINT_CONFIG_KEY,
    authorizationEndpoint,
    tenantId
  );
  if (!saved) {
    throw new Error('Failed to save Snowflake OAuth authorization endpoint');
  }
};

const getSnowflakeOAuthAuthorizationEndpoint = async (tenantId: string): Promise<string | null> => {
  const endpoint = await getConfigValue(
    SNOWFLAKE_OAUTH_AUTHORIZATION_ENDPOINT_CONFIG_KEY,
    tenantId
  );
  if (!endpoint || typeof endpoint !== 'string') {
    return null;
  }
  return endpoint;
};

const saveSnowflakeOAuthTokenEndpoint = async (
  tenantId: string,
  tokenEndpoint: string
): Promise<void> => {
  const saved = await saveConfigValue(
    SNOWFLAKE_OAUTH_TOKEN_ENDPOINT_CONFIG_KEY,
    tokenEndpoint,
    tenantId
  );
  if (!saved) {
    throw new Error('Failed to save Snowflake OAuth token endpoint');
  }
};

const getSnowflakeOAuthTokenEndpoint = async (tenantId: string): Promise<string | null> => {
  const endpoint = await getConfigValue(SNOWFLAKE_OAUTH_TOKEN_ENDPOINT_CONFIG_KEY, tenantId);
  if (!endpoint || typeof endpoint !== 'string') {
    return null;
  }
  return endpoint;
};

const saveSnowflakeIntegrationName = async (
  tenantId: string,
  integrationName: string
): Promise<void> => {
  const saved = await saveConfigValue(
    SNOWFLAKE_INTEGRATION_NAME_CONFIG_KEY,
    integrationName,
    tenantId
  );
  if (!saved) {
    throw new Error('Failed to save Snowflake integration name');
  }
};

const getSnowflakeIntegrationName = async (tenantId: string): Promise<string | null> => {
  const integrationName = await getConfigValue(SNOWFLAKE_INTEGRATION_NAME_CONFIG_KEY, tenantId);
  if (!integrationName || typeof integrationName !== 'string') {
    return null;
  }
  return integrationName;
};

const isSnowflakeComplete = (config: Record<ConfigKey, ConfigValue>): boolean =>
  !!config[SNOWFLAKE_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY] &&
  !!config[SNOWFLAKE_ACCOUNT_IDENTIFIER_CONFIG_KEY] &&
  !!config[SNOWFLAKE_CLIENT_ID_CONFIG_KEY] &&
  !!config[SNOWFLAKE_CLIENT_SECRET_CONFIG_KEY];

const snowflakeOauthTokenPayloadConfigKey = SNOWFLAKE_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY;

export {
  isSnowflakeComplete,
  saveSnowflakeOauthToken,
  getSnowflakeOauthToken,
  saveSnowflakeAccountIdentifier,
  getSnowflakeAccountIdentifier,
  saveSnowflakeClientId,
  getSnowflakeClientId,
  saveSnowflakeClientSecret,
  getSnowflakeClientSecret,
  saveSnowflakeOAuthAuthorizationEndpoint,
  getSnowflakeOAuthAuthorizationEndpoint,
  saveSnowflakeOAuthTokenEndpoint,
  getSnowflakeOAuthTokenEndpoint,
  saveSnowflakeIntegrationName,
  getSnowflakeIntegrationName,
  SNOWFLAKE_SENSITIVE_KEYS,
  SNOWFLAKE_NON_SENSITIVE_KEYS,
  SNOWFLAKE_CLIENT_ID_CONFIG_KEY,
  SNOWFLAKE_CLIENT_SECRET_CONFIG_KEY,
  snowflakeOauthTokenPayloadConfigKey,
  type SnowflakeOauthToken,
};
