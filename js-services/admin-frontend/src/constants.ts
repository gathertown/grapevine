// Constants for the admin web UI
import { getConfig } from './lib/config';

export const IS_LOCAL = window.location.hostname === 'localhost';

// Staging detection: prefer ENVIRONMENT config, fallback to hostname detection
export const IS_STAGING =
  getConfig().ENVIRONMENT === 'staging' ||
  window.location.hostname.includes('stg.') ||
  window.location.hostname.includes('staging');

// Feature flags
export const JIRA_APP_INSTALLATION_URL = getConfig().JIRA_APP_INSTALLATION_URL;
export const CONFLUENCE_APP_INSTALLATION_URL = getConfig().CONFLUENCE_APP_INSTALLATION_URL;

export const CONFLUENCE_ENABLED = true;

export const GOOGLE_EMAIL_ENABLED = true;
export const GONG_ENABLED = IS_LOCAL || IS_STAGING;
export const INTERCOM_ENABLED = IS_LOCAL || IS_STAGING;

export const SALESFORCE_ENABLED = IS_LOCAL || IS_STAGING;
export const SALESFORCE_CLIENT_ID = getConfig().SALESFORCE_CLIENT_ID;

export const GITLAB_ENABLED = IS_LOCAL || IS_STAGING;

// Configurable contact email - defaults to empty if not configured
// Self-hosted users should set VITE_SUPPORT_EMAIL or SUPPORT_EMAIL env var
export const SUPPORT_EMAIL = getConfig().SUPPORT_EMAIL || '';

// Configurable documentation URL - defaults to empty if not configured
// Self-hosted users should set VITE_DOCS_URL or DOCS_URL env var
export const DOCS_URL = getConfig().DOCS_URL || '';

// Helper to get support contact text - returns generic message if no email configured
export const getSupportContactText = (): string => {
  if (!SUPPORT_EMAIL) {
    return 'Please try again or contact your administrator.';
  }
  return `Please try again or contact support at ${SUPPORT_EMAIL}`;
};

// Webhook endpoint paths
const WEBHOOK_ENDPOINTS = {
  GITHUB: '/webhooks/github',
  SLACK: '/webhooks/slack',
  NOTION: '/webhooks/notion',
  LINEAR: '/webhooks/linear',
  GOOGLE_DRIVE: '/webhooks/google-drive',
  GOOGLE_EMAIL: '/webhooks/google-email',
  GATHER: '/webhooks/gather',
} as const;

// Build tenant-specific webhook URLs
export const buildWebhookUrls = (tenantId: string) => {
  const config = getConfig();
  const baseDomain = config.BASE_DOMAIN;
  if (!baseDomain) {
    throw new Error('BASE_DOMAIN configuration is required');
  }
  const baseUrl = `https://${tenantId}.ingest.${baseDomain}`;

  return {
    GITHUB: `${baseUrl}${WEBHOOK_ENDPOINTS.GITHUB}`,
    // NOTE: in local dev, you can override this to point to your local ngrok domain, then install a new slack app with this webhook url in the manifest
    // You can also go to https://api.slack.com/apps, find your app, and edit its manifest directly
    SLACK: `${baseUrl}${WEBHOOK_ENDPOINTS.SLACK}`,
    NOTION: `${baseUrl}${WEBHOOK_ENDPOINTS.NOTION}`,
    LINEAR: `${baseUrl}${WEBHOOK_ENDPOINTS.LINEAR}`,
    GOOGLE_DRIVE: `${baseUrl}${WEBHOOK_ENDPOINTS.GOOGLE_DRIVE}`,
    GOOGLE_EMAIL: `${baseUrl}${WEBHOOK_ENDPOINTS.GOOGLE_EMAIL}`,
    GATHER: `${baseUrl}${WEBHOOK_ENDPOINTS.GATHER}`,
  } as const;
};

// Type exports for better type safety
export type WebhookEndpoint = keyof typeof WEBHOOK_ENDPOINTS;
