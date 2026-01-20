import { ConfigKey, ConfigValue } from '../../config/types';
import { saveConfigValue, deleteConfigValue } from '../../config';

// Config key to track if custom data connector has at least one enabled type
const CUSTOM_DATA_HAS_TYPES_CONFIG_KEY = 'CUSTOM_DATA_HAS_TYPES';

const CUSTOM_DATA_SENSITIVE_KEYS = [] as const;
const CUSTOM_DATA_NON_SENSITIVE_KEYS = [CUSTOM_DATA_HAS_TYPES_CONFIG_KEY] as const;

/**
 * Update the config flag indicating whether custom data has any enabled types
 */
const setCustomDataHasTypes = async (tenantId: string, hasTypes: boolean): Promise<void> => {
  if (hasTypes) {
    const saved = await saveConfigValue(CUSTOM_DATA_HAS_TYPES_CONFIG_KEY, 'true', tenantId);
    if (!saved) {
      throw new Error('Failed to save Custom Data config');
    }
  } else {
    await deleteConfigValue(CUSTOM_DATA_HAS_TYPES_CONFIG_KEY, tenantId);
  }
};

/**
 * Check if custom data connector is complete (has at least one enabled type)
 */
const isCustomDataComplete = (config: Record<ConfigKey, ConfigValue>) =>
  config[CUSTOM_DATA_HAS_TYPES_CONFIG_KEY] === 'true';

export {
  isCustomDataComplete,
  setCustomDataHasTypes,
  CUSTOM_DATA_HAS_TYPES_CONFIG_KEY,
  CUSTOM_DATA_SENSITIVE_KEYS,
  CUSTOM_DATA_NON_SENSITIVE_KEYS,
};
