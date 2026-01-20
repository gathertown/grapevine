import { ConfigKey, ConfigValue } from '../../config/types';
import { saveConfigValue, deleteConfigValue } from '../../config';

// Sensitive keys (stored in SSM)
const POSTHOG_API_KEY_CONFIG_KEY = 'POSTHOG_PERSONAL_API_KEY';
const POSTHOG_HOST_CONFIG_KEY = 'POSTHOG_HOST';

// Non-sensitive keys (stored in tenant database config table)
const POSTHOG_FULL_BACKFILL_COMPLETE_KEY = 'POSTHOG_FULL_BACKFILL_COMPLETE';
const POSTHOG_LAST_SYNCED_AT_KEY = 'POSTHOG_LAST_SYNCED_AT';

const POSTHOG_SENSITIVE_KEYS = [POSTHOG_API_KEY_CONFIG_KEY, POSTHOG_HOST_CONFIG_KEY] as const;

const POSTHOG_NON_SENSITIVE_KEYS = [
  POSTHOG_FULL_BACKFILL_COMPLETE_KEY,
  POSTHOG_LAST_SYNCED_AT_KEY,
] as const;

const savePostHogApiKey = async (tenantId: string, apiKey: string): Promise<void> => {
  const saved = await saveConfigValue(POSTHOG_API_KEY_CONFIG_KEY, apiKey, tenantId);
  if (!saved) {
    throw new Error('Failed to save PostHog API key');
  }
};

const savePostHogHost = async (tenantId: string, host: string): Promise<void> => {
  const saved = await saveConfigValue(POSTHOG_HOST_CONFIG_KEY, host, tenantId);
  if (!saved) {
    throw new Error('Failed to save PostHog host');
  }
};

const deletePostHogApiKey = async (tenantId: string): Promise<void> => {
  await deleteConfigValue(POSTHOG_API_KEY_CONFIG_KEY, tenantId);
};

const deletePostHogHost = async (tenantId: string): Promise<void> => {
  await deleteConfigValue(POSTHOG_HOST_CONFIG_KEY, tenantId);
};

/**
 * Reset PostHog backfill state to allow a fresh sync on reconnect.
 * Deletes all backfill progress tracking keys from the tenant config.
 */
const resetPostHogBackfillState = async (tenantId: string): Promise<void> => {
  await Promise.all([
    deleteConfigValue(POSTHOG_FULL_BACKFILL_COMPLETE_KEY, tenantId),
    deleteConfigValue(POSTHOG_LAST_SYNCED_AT_KEY, tenantId),
  ]);
};

const isPostHogComplete = (config: Record<ConfigKey, ConfigValue>) =>
  !!config[POSTHOG_API_KEY_CONFIG_KEY];

export {
  isPostHogComplete,
  savePostHogApiKey,
  savePostHogHost,
  deletePostHogApiKey,
  deletePostHogHost,
  resetPostHogBackfillState,
  POSTHOG_SENSITIVE_KEYS,
  POSTHOG_NON_SENSITIVE_KEYS,
  POSTHOG_API_KEY_CONFIG_KEY,
  POSTHOG_HOST_CONFIG_KEY,
};
