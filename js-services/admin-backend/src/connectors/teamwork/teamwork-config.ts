/**
 * Teamwork Configuration Keys
 *
 * OAuth tokens are stored in SSM Parameter Store.
 * Non-sensitive metadata is stored in the tenant config table.
 *
 * Teamwork OAuth:
 * - Access tokens are long-lived (permanent)
 * - No refresh tokens needed
 * - API domain is instance-specific (e.g., https://yourcompany.teamwork.com)
 */

import type { ConfigKey } from '../../config/types.js';

// SSM keys (sensitive)
export const TEAMWORK_ACCESS_TOKEN_KEY: ConfigKey = 'TEAMWORK_ACCESS_TOKEN';

// DB config keys (non-sensitive)
export const TEAMWORK_API_DOMAIN_KEY: ConfigKey = 'TEAMWORK_API_DOMAIN';
export const TEAMWORK_INSTALLATION_ID_KEY: ConfigKey = 'TEAMWORK_INSTALLATION_ID';
export const TEAMWORK_USER_ID_KEY: ConfigKey = 'TEAMWORK_USER_ID';
export const TEAMWORK_USER_NAME_KEY: ConfigKey = 'TEAMWORK_USER_NAME';

// Sync state keys
export const TEAMWORK_TASKS_SYNCED_UNTIL_KEY: ConfigKey = 'TEAMWORK_TASKS_SYNCED_UNTIL';
export const TEAMWORK_FULL_BACKFILL_COMPLETE_KEY: ConfigKey = 'TEAMWORK_FULL_BACKFILL_COMPLETE';

// Pagination cursor keys
export const TEAMWORK_TASKS_CURSOR_KEY: ConfigKey = 'TEAMWORK_TASKS_CURSOR';

/**
 * Sensitive keys stored in AWS SSM Parameter Store
 */
export const TEAMWORK_SENSITIVE_KEYS: ConfigKey[] = [TEAMWORK_ACCESS_TOKEN_KEY];

/**
 * Non-sensitive keys stored in PostgreSQL config table
 */
export const TEAMWORK_NON_SENSITIVE_KEYS: ConfigKey[] = [
  TEAMWORK_API_DOMAIN_KEY,
  TEAMWORK_INSTALLATION_ID_KEY,
  TEAMWORK_USER_ID_KEY,
  TEAMWORK_USER_NAME_KEY,
  TEAMWORK_TASKS_SYNCED_UNTIL_KEY,
  TEAMWORK_FULL_BACKFILL_COMPLETE_KEY,
  TEAMWORK_TASKS_CURSOR_KEY,
];

/**
 * All Teamwork config keys for cleanup on disconnect
 */
export const TEAMWORK_CONFIG_KEYS: ConfigKey[] = [
  ...TEAMWORK_SENSITIVE_KEYS,
  ...TEAMWORK_NON_SENSITIVE_KEYS,
];

/**
 * Check if Teamwork is fully configured
 */
export const isTeamworkComplete = (config: Record<ConfigKey, unknown>): boolean => {
  return !!config[TEAMWORK_ACCESS_TOKEN_KEY];
};
