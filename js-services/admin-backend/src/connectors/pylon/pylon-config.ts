import { ConfigKey, ConfigValue } from '../../config/types';
import { saveConfigValue, deleteConfigValue } from '../../config';

const PYLON_API_KEY_CONFIG_KEY = 'PYLON_API_KEY';

// Backfill state keys (stored in tenant database config table)
const PYLON_FULL_BACKFILL_COMPLETE_KEY = 'PYLON_FULL_BACKFILL_ISSUES_COMPLETE';
const PYLON_FULL_BACKFILL_SYNCED_AFTER_KEY = 'PYLON_FULL_BACKFILL_ISSUES_SYNCED_AFTER';
const PYLON_FULL_BACKFILL_CURSOR_KEY = 'PYLON_FULL_BACKFILL_ISSUES_CURSOR';
const PYLON_INCR_BACKFILL_SYNCED_UNTIL_KEY = 'PYLON_INCR_BACKFILL_ISSUES_SYNCED_UNTIL';
const PYLON_REFERENCE_DATA_SYNCED_AT_KEY = 'PYLON_REFERENCE_DATA_SYNCED_AT';

const PYLON_SENSITIVE_KEYS = [PYLON_API_KEY_CONFIG_KEY] as const;
const PYLON_NON_SENSITIVE_KEYS = [
  PYLON_FULL_BACKFILL_COMPLETE_KEY,
  PYLON_FULL_BACKFILL_SYNCED_AFTER_KEY,
  PYLON_FULL_BACKFILL_CURSOR_KEY,
  PYLON_INCR_BACKFILL_SYNCED_UNTIL_KEY,
  PYLON_REFERENCE_DATA_SYNCED_AT_KEY,
] as const;

const savePylonApiKey = async (tenantId: string, apiKey: string): Promise<void> => {
  const saved = await saveConfigValue(PYLON_API_KEY_CONFIG_KEY, apiKey, tenantId);
  if (!saved) {
    throw new Error('Failed to save Pylon API key');
  }
};

const deletePylonApiKey = async (tenantId: string): Promise<void> => {
  // if not deleted could have been missing from ssm, lets not error.
  await deleteConfigValue(PYLON_API_KEY_CONFIG_KEY, tenantId);
};

/**
 * Reset Pylon backfill state to allow a fresh sync on reconnect.
 * Deletes all backfill progress tracking keys from the tenant config.
 */
const resetPylonBackfillState = async (tenantId: string): Promise<void> => {
  await Promise.all([
    deleteConfigValue(PYLON_FULL_BACKFILL_COMPLETE_KEY, tenantId),
    deleteConfigValue(PYLON_FULL_BACKFILL_SYNCED_AFTER_KEY, tenantId),
    deleteConfigValue(PYLON_FULL_BACKFILL_CURSOR_KEY, tenantId),
    deleteConfigValue(PYLON_INCR_BACKFILL_SYNCED_UNTIL_KEY, tenantId),
    deleteConfigValue(PYLON_REFERENCE_DATA_SYNCED_AT_KEY, tenantId),
  ]);
};

const isPylonComplete = (config: Record<ConfigKey, ConfigValue>) =>
  !!config[PYLON_API_KEY_CONFIG_KEY];

export {
  isPylonComplete,
  savePylonApiKey,
  deletePylonApiKey,
  resetPylonBackfillState,
  PYLON_SENSITIVE_KEYS,
  PYLON_NON_SENSITIVE_KEYS,
};
