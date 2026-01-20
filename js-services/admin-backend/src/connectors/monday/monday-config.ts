/**
 * Monday.com Configuration Keys
 *
 * Defines sensitive and non-sensitive configuration keys for Monday.com OAuth.
 *
 * Token characteristics (from Monday.com docs):
 * - OAuth: Tokens do NOT expire and are valid until the user uninstalls the app
 * - No refresh token mechanism - tokens are permanent
 * Source: https://developer.monday.com/apps/docs/oauth
 */

import type { ConfigKey } from '../../config/types.js';
import { deleteConfigValue } from '../../config/index.js';

// Config key constants
export const MONDAY_ACCESS_TOKEN_KEY: ConfigKey = 'MONDAY_ACCESS_TOKEN';
export const MONDAY_ACCOUNT_ID_KEY: ConfigKey = 'MONDAY_ACCOUNT_ID';
export const MONDAY_ACCOUNT_NAME_KEY: ConfigKey = 'MONDAY_ACCOUNT_NAME';
export const MONDAY_ACCOUNT_SLUG_KEY: ConfigKey = 'MONDAY_ACCOUNT_SLUG';

// Backfill state key (stored in tenant database config table)
const MONDAY_INCR_BACKFILL_SYNCED_UNTIL_KEY: ConfigKey = 'MONDAY_INCR_BACKFILL_ITEMS_SYNCED_UNTIL';

/**
 * Sensitive keys stored in AWS SSM Parameter Store
 */
export const MONDAY_SENSITIVE_KEYS: ConfigKey[] = [
  MONDAY_ACCESS_TOKEN_KEY,
  // Note: Monday.com OAuth does not return refresh tokens per documentation
] as const;

/**
 * Non-sensitive keys stored in PostgreSQL
 */
export const MONDAY_NON_SENSITIVE_KEYS: ConfigKey[] = [
  MONDAY_ACCOUNT_ID_KEY,
  MONDAY_ACCOUNT_NAME_KEY,
  MONDAY_ACCOUNT_SLUG_KEY,
] as const;

/**
 * All Monday.com configuration keys
 * Used for operations like disconnect that need to clean up all config
 */
export const MONDAY_CONFIG_KEYS = [...MONDAY_SENSITIVE_KEYS, ...MONDAY_NON_SENSITIVE_KEYS] as const;

/**
 * Check if Monday.com connector is complete/configured
 */
export const isMondayComplete = (config: Record<ConfigKey, unknown>): boolean => {
  return !!config[MONDAY_ACCESS_TOKEN_KEY];
};

/**
 * Reset Monday.com backfill state to allow a fresh sync on reconnect.
 * Deletes backfill progress tracking key from the tenant config.
 */
export const resetMondayBackfillState = async (tenantId: string): Promise<void> => {
  await deleteConfigValue(MONDAY_INCR_BACKFILL_SYNCED_UNTIL_KEY, tenantId);
};
