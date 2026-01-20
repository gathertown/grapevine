/**
 * Configuration Key Definitions
 * Central registry of all configuration keys with their sensitivity classification
 */

import {
  ZENDESK_NON_SENSITIVE_KEYS,
  ZENDESK_SENSITIVE_KEYS,
} from '../connectors/zendesk/zendesk-config.js';
import {
  SNOWFLAKE_NON_SENSITIVE_KEYS,
  SNOWFLAKE_SENSITIVE_KEYS,
} from '../connectors/snowflake/snowflake-config.js';
import type { ConfigKey } from './types.js';
import {
  ASANA_NON_SENSITIVE_KEYS,
  ASANA_SENSITIVE_KEYS,
} from '../connectors/asana/asana-config.js';
import {
  INTERCOM_SENSITIVE_KEYS,
  INTERCOM_NON_SENSITIVE_KEYS,
} from '../connectors/intercom/intercom-config-keys.js';
import {
  ATTIO_SENSITIVE_KEYS,
  ATTIO_NON_SENSITIVE_KEYS,
} from '../connectors/attio/attio-config.js';
import {
  FIREFLIES_NON_SENSITIVE_KEYS,
  FIREFLIES_SENSITIVE_KEYS,
} from '../connectors/fireflies/fireflies-config.js';
import {
  GITLAB_SENSITIVE_KEYS,
  GITLAB_NON_SENSITIVE_KEYS,
} from '../connectors/gitlab/gitlab-config-keys.js';
import {
  CLICKUP_NON_SENSITIVE_KEYS,
  CLICKUP_SENSITIVE_KEYS,
} from '../connectors/clickup/clickup-config.js';
import {
  PYLON_SENSITIVE_KEYS,
  PYLON_NON_SENSITIVE_KEYS,
} from '../connectors/pylon/pylon-config.js';
import {
  MONDAY_SENSITIVE_KEYS,
  MONDAY_NON_SENSITIVE_KEYS,
} from '../connectors/monday/monday-config.js';
import {
  PIPEDRIVE_SENSITIVE_KEYS,
  PIPEDRIVE_NON_SENSITIVE_KEYS,
} from '../connectors/pipedrive/pipedrive-config.js';
import {
  FIGMA_SENSITIVE_KEYS,
  FIGMA_NON_SENSITIVE_KEYS,
} from '../connectors/figma/figma-config.js';
import {
  POSTHOG_SENSITIVE_KEYS,
  POSTHOG_NON_SENSITIVE_KEYS,
} from '../connectors/posthog/posthog-config.js';
import {
  CANVA_SENSITIVE_KEYS,
  CANVA_NON_SENSITIVE_KEYS,
} from '../connectors/canva/canva-config.js';
import {
  TEAMWORK_SENSITIVE_KEYS,
  TEAMWORK_NON_SENSITIVE_KEYS,
} from '../connectors/teamwork/teamwork-config.js';

/**
 * Sensitive configuration keys that must be stored in SSM
 * These contain secrets, API keys, and other sensitive data that should be encrypted
 */
export const SENSITIVE_KEYS: ConfigKey[] = [
  'GITHUB_TOKEN',
  'GITHUB_WEBHOOK_SECRET',
  'SLACK_BOT_TOKEN',
  'SLACK_CLIENT_SECRET',
  'SLACK_SIGNING_SECRET',
  'NOTION_TOKEN',
  'NOTION_WEBHOOK_SECRET',
  'LINEAR_API_KEY',
  'LINEAR_ACCESS_TOKEN',
  'LINEAR_REFRESH_TOKEN',
  'LINEAR_WEBHOOK_SECRET',
  'GOOGLE_DRIVE_ADMIN_EMAIL',
  'GOOGLE_DRIVE_SERVICE_ACCOUNT',
  'GOOGLE_EMAIL_ADMIN_EMAIL',
  'GOOGLE_EMAIL_PUB_SUB_TOPIC',
  'GOOGLE_EMAIL_SERVICE_ACCOUNT',
  'SALESFORCE_REFRESH_TOKEN',
  'HUBSPOT_ACCESS_TOKEN',
  'HUBSPOT_REFRESH_TOKEN',
  'GONG_ACCESS_TOKEN',
  'GONG_REFRESH_TOKEN',
  'GONG_WEBHOOK_PUBLIC_KEY',
  'GATHER_API_KEY',
  'GATHER_WEBHOOK_SECRET',
  'TRELLO_ACCESS_TOKEN',
  'TRELLO_WEBHOOK_SECRET',
  ...ZENDESK_SENSITIVE_KEYS,
  ...SNOWFLAKE_SENSITIVE_KEYS,
  ...ASANA_SENSITIVE_KEYS,
  ...INTERCOM_SENSITIVE_KEYS,
  ...ATTIO_SENSITIVE_KEYS,
  ...FIREFLIES_SENSITIVE_KEYS,
  ...GITLAB_SENSITIVE_KEYS,
  ...CLICKUP_SENSITIVE_KEYS,
  ...PYLON_SENSITIVE_KEYS,
  ...MONDAY_SENSITIVE_KEYS,
  ...PIPEDRIVE_SENSITIVE_KEYS,
  ...FIGMA_SENSITIVE_KEYS,
  ...POSTHOG_SENSITIVE_KEYS,
  ...CANVA_SENSITIVE_KEYS,
  ...TEAMWORK_SENSITIVE_KEYS,
] as const;

/**
 * Non-sensitive configuration keys that can be stored in the database
 * These are general configuration values that don't require encryption
 */
export const NON_SENSITIVE_KEYS: ConfigKey[] = [
  'COMPANY_NAME',
  'COMPANY_CONTEXT',
  'SLACK_BOT_NAME',
  'SLACK_CLIENT_ID',
  'SLACK_INSTALLER_USER_ID',
  'SLACK_INSTALLER_DM_SENT',
  'SLACK_EXPORT_INFO',
  'SLACK_EXPORT_JOB_ID',
  'SLACK_EXPORTS_UPLOADED',
  'SLACK_BOT_MIRROR_QUESTIONS_CHANNEL_NAME',
  'SLACK_BOT_QA_ALL_CHANNELS', // is proactivity enabled for all channels? (excluding `SLACK_BOT_QA_DISALLOWED_CHANNELS`)
  'SLACK_BOT_QA_ALLOWED_CHANNELS',
  'SLACK_BOT_QA_DISALLOWED_CHANNELS',
  'SLACK_BOT_QA_CONFIDENCE_THRESHOLD',
  'SLACK_BOT_QA_SKIP_CHANNELS_WITH_EXTERNAL_GUESTS',
  'SLACK_BOT_QA_SKIP_MENTIONS_BY_NON_MEMBERS',
  'GITHUB_SETUP_COMPLETE',
  'NOTION_COMPLETE',
  'ALLOW_DATA_SHARING_FOR_IMPROVEMENTS',
  'SELECTED_INTEGRATIONS',
  'TENANT_MODE',
  'SALESFORCE_INSTANCE_URL',
  'SALESFORCE_ORG_ID',
  'SALESFORCE_USER_ID',
  'JIRA_SITE_URL',
  'JIRA_CLOUD_ID',
  'JIRA_WEBTRIGGER_BACKFILL_URL',
  'HUBSPOT_PORTAL_ID',
  'HUBSPOT_TOKEN_EXPIRES_AT',
  'HUBSPOT_COMPLETE',
  'LINEAR_TOKEN_EXPIRES_AT',
  'GONG_SCOPE',
  'GONG_TOKEN_TYPE',
  'GONG_TOKEN_EXPIRES_IN',
  'GONG_API_BASE_URL',
  'GONG_WEBHOOK_URL',
  'GONG_WEBHOOK_VERIFIED',
  'TRELLO_WEBHOOKS',
  ...ZENDESK_NON_SENSITIVE_KEYS,
  ...SNOWFLAKE_NON_SENSITIVE_KEYS,
  ...ASANA_NON_SENSITIVE_KEYS,
  ...INTERCOM_NON_SENSITIVE_KEYS,
  ...ATTIO_NON_SENSITIVE_KEYS,
  ...FIREFLIES_NON_SENSITIVE_KEYS,
  ...GITLAB_NON_SENSITIVE_KEYS,
  ...CLICKUP_NON_SENSITIVE_KEYS,
  ...PYLON_NON_SENSITIVE_KEYS,
  ...MONDAY_NON_SENSITIVE_KEYS,
  ...PIPEDRIVE_NON_SENSITIVE_KEYS,
  ...FIGMA_NON_SENSITIVE_KEYS,
  ...POSTHOG_NON_SENSITIVE_KEYS,
  ...CANVA_NON_SENSITIVE_KEYS,
  ...TEAMWORK_NON_SENSITIVE_KEYS,
  'GONG_SELECTED_WORKSPACE_IDS',
  'LINEAR_TEAM_SLACK_CHANNEL_MAPPINGS',
  'TRIAGE_BOT_LINEAR_CONNECTED',
] as const;

/**
 * All known configuration keys (combination of sensitive and non-sensitive)
 */
export const ALL_KEYS: ConfigKey[] = [...SENSITIVE_KEYS, ...NON_SENSITIVE_KEYS] as const;

/**
 * Check if a configuration key is sensitive and should use SSM
 * @param key - The configuration key to check
 * @returns True if the key should use SSM, false if it can use database
 */
export function isSensitiveKey(key: ConfigKey): boolean {
  if (SENSITIVE_KEYS.includes(key)) {
    return true;
  }

  for (const sensitiveKey of SENSITIVE_KEYS) {
    if (key.endsWith(`/${sensitiveKey}`)) {
      return true;
    }
  }

  return false;
}
