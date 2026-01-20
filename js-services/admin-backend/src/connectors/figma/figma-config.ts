/**
 * Figma Configuration Keys
 *
 * OAuth tokens are stored in SSM Parameter Store.
 * Non-sensitive metadata is stored in the tenant config table.
 *
 * Figma OAuth:
 * - Authorization codes expire in 30 seconds
 * - Access tokens expire after 90 days (long-lived, no refresh on every request needed)
 * - Refresh tokens are long-lived
 */

import type { ConfigKey } from '../../config/types.js';

// SSM keys (sensitive)
export const FIGMA_ACCESS_TOKEN_KEY: ConfigKey = 'FIGMA_ACCESS_TOKEN';
export const FIGMA_REFRESH_TOKEN_KEY: ConfigKey = 'FIGMA_REFRESH_TOKEN';
// Webhook passcode (stored in SSM as signing secret)
export const FIGMA_WEBHOOK_PASSCODE_KEY: ConfigKey = 'FIGMA_WEBHOOK_PASSCODE';

// DB config keys (non-sensitive)
export const FIGMA_USER_ID_KEY: ConfigKey = 'FIGMA_USER_ID';
export const FIGMA_USER_EMAIL_KEY: ConfigKey = 'FIGMA_USER_EMAIL';
export const FIGMA_USER_HANDLE_KEY: ConfigKey = 'FIGMA_USER_HANDLE';
export const FIGMA_TOKEN_EXPIRES_AT_KEY: ConfigKey = 'FIGMA_TOKEN_EXPIRES_AT';

// Sync state keys
export const FIGMA_FULL_BACKFILL_COMPLETE_KEY: ConfigKey = 'FIGMA_FULL_BACKFILL_COMPLETE';
export const FIGMA_FILES_SYNCED_UNTIL_KEY: ConfigKey = 'FIGMA_FILES_SYNCED_UNTIL';
export const FIGMA_COMMENTS_SYNCED_UNTIL_KEY: ConfigKey = 'FIGMA_COMMENTS_SYNCED_UNTIL';

// Note: Team IDs are stored in connector_installations.external_metadata, not in tenant config

/**
 * Sensitive keys stored in AWS SSM Parameter Store
 */
export const FIGMA_SENSITIVE_KEYS: ConfigKey[] = [
  FIGMA_ACCESS_TOKEN_KEY,
  FIGMA_REFRESH_TOKEN_KEY,
  FIGMA_WEBHOOK_PASSCODE_KEY,
];

/**
 * Non-sensitive keys stored in PostgreSQL config table
 */
export const FIGMA_NON_SENSITIVE_KEYS: ConfigKey[] = [
  FIGMA_USER_ID_KEY,
  FIGMA_USER_EMAIL_KEY,
  FIGMA_USER_HANDLE_KEY,
  FIGMA_TOKEN_EXPIRES_AT_KEY,
  FIGMA_FULL_BACKFILL_COMPLETE_KEY,
  FIGMA_FILES_SYNCED_UNTIL_KEY,
  FIGMA_COMMENTS_SYNCED_UNTIL_KEY,
];

/**
 * All Figma config keys for cleanup on disconnect
 */
export const FIGMA_CONFIG_KEYS: ConfigKey[] = [
  ...FIGMA_SENSITIVE_KEYS,
  ...FIGMA_NON_SENSITIVE_KEYS,
];

/**
 * Check if Figma is fully configured
 */
export const isFigmaComplete = (config: Record<ConfigKey, unknown>): boolean => {
  return !!config[FIGMA_ACCESS_TOKEN_KEY];
};
