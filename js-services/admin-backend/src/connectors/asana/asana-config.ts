import { ConfigKey, ConfigValue } from '../../config/types';
import { saveConfigValue } from '../../config';

const ASANA_SERVICE_ACCOUNT_TOKEN_CONFIG_KEY = 'ASANA_SERVICE_ACCOUNT_TOKEN';
const ASANA_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY = 'ASANA_OAUTH_TOKEN_PAYLOAD';

const ASANA_SENSITIVE_KEYS = [
  ASANA_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY,
  ASANA_SERVICE_ACCOUNT_TOKEN_CONFIG_KEY,
] as const;
const ASANA_NON_SENSITIVE_KEYS = [] as const;

interface AsanaOauthToken {
  access_token: string;
  refresh_token: string;
  access_token_expires_at: string;
}

const saveAsanaOauthToken = async (tenantId: string, token: AsanaOauthToken): Promise<void> => {
  const tokenJson = JSON.stringify(token);

  const saved = await saveConfigValue(ASANA_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY, tokenJson, tenantId);
  if (!saved) {
    throw new Error('Failed to save Asana access token');
  }
};

const saveAsanaServiceAccountToken = async (tenantId: string, token: string): Promise<void> => {
  const saved = await saveConfigValue(ASANA_SERVICE_ACCOUNT_TOKEN_CONFIG_KEY, token, tenantId);
  if (!saved) {
    throw new Error('Failed to save Asana access token');
  }
};

// Considered complete if either OAuth token or Service Account token is present
const isAsanaComplete = (config: Record<ConfigKey, ConfigValue>) =>
  !!config[ASANA_OAUTH_TOKEN_PAYLOAD_CONFIG_KEY] ||
  !!config[ASANA_SERVICE_ACCOUNT_TOKEN_CONFIG_KEY];

export {
  isAsanaComplete,
  saveAsanaOauthToken,
  saveAsanaServiceAccountToken,
  ASANA_SENSITIVE_KEYS,
  ASANA_NON_SENSITIVE_KEYS,
  type AsanaOauthToken,
};
