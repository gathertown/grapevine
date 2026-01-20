import { ConfigKey, ConfigValue } from '../../config/types';
import { saveConfigValue, deleteConfigValue } from '../../config';

const FIREFLIES_API_KEY_CONFIG_KEY = 'FIREFLIES_API_KEY';

const FIREFLIES_SENSITIVE_KEYS = [FIREFLIES_API_KEY_CONFIG_KEY] as const;
const FIREFLIES_NON_SENSITIVE_KEYS = [] as const;

const saveFirefliesApiKey = async (tenantId: string, apiKey: string): Promise<void> => {
  const saved = await saveConfigValue(FIREFLIES_API_KEY_CONFIG_KEY, apiKey, tenantId);
  if (!saved) {
    throw new Error('Failed to save Fireflies API key');
  }
};

const deleteFirefliesApiKey = async (tenantId: string): Promise<void> => {
  // if not deleted could have been missing from ssm, lets not error.
  await deleteConfigValue(FIREFLIES_API_KEY_CONFIG_KEY, tenantId);
};

const isFirefliesComplete = (config: Record<ConfigKey, ConfigValue>) =>
  !!config[FIREFLIES_API_KEY_CONFIG_KEY];

export {
  isFirefliesComplete,
  saveFirefliesApiKey,
  deleteFirefliesApiKey,
  FIREFLIES_SENSITIVE_KEYS,
  FIREFLIES_NON_SENSITIVE_KEYS,
};
