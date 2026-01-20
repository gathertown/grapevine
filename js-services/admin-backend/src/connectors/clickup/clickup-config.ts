import { ConfigKey, ConfigValue } from '../../config/types';
import { saveConfigValue, deleteConfigValue } from '../../config';

const CLICKUP_OAUTH_TOKEN_CONFIG_KEY = 'CLICKUP_OAUTH_TOKEN';

const CLICKUP_SENSITIVE_KEYS = [CLICKUP_OAUTH_TOKEN_CONFIG_KEY] as const;
const CLICKUP_NON_SENSITIVE_KEYS = [] as const;

const saveClickupOauthToken = async (tenantId: string, token: string): Promise<void> => {
  const saved = await saveConfigValue(CLICKUP_OAUTH_TOKEN_CONFIG_KEY, token, tenantId);
  if (!saved) {
    throw new Error('Failed to save Clickup OAuth token');
  }
};

const deleteClickupOauthToken = async (tenantId: string): Promise<void> => {
  // if not deleted could have been missing from ssm, lets not error.
  await deleteConfigValue(CLICKUP_OAUTH_TOKEN_CONFIG_KEY, tenantId);
};

const isClickupComplete = (config: Record<ConfigKey, ConfigValue>) =>
  !!config[CLICKUP_OAUTH_TOKEN_CONFIG_KEY];

export {
  isClickupComplete,
  saveClickupOauthToken,
  deleteClickupOauthToken,
  CLICKUP_SENSITIVE_KEYS,
  CLICKUP_NON_SENSITIVE_KEYS,
};
