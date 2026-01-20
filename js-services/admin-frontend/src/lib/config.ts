/**
 * Runtime configuration accessor
 * Reads from runtime environment config injected at container startup,
 * with fallback to build-time VITE environment variables for local development.
 */

// Extend the EnvConfig interface from frontend-common with admin-specific config
import type { EnvConfig as BaseEnvConfig } from '@corporate-context/frontend-common';

// Module augmentation to extend the frontend-common EnvConfig interface
declare module '@corporate-context/frontend-common' {
  interface EnvConfig {
    NEW_RELIC_LICENSE_KEY?: string;
    NEW_RELIC_APPLICATION_ID?: string;
    NEW_RELIC_ACCOUNT_ID?: string;
    NEW_RELIC_TRUST_KEY?: string;
    NEW_RELIC_AGENT_ID?: string;
    WORKOS_CLIENT_ID?: string;
    SSO_ALLOWED_PARENT_ORIGINS?: string;
    WORKOS_API_HOSTNAME?: string;
    POSTHOG_UI_HOST?: string;
    BASE_DOMAIN?: string;
    FRONTEND_URL?: string;
    ENVIRONMENT?: string;
    JIRA_APP_ID?: string;
    JIRA_APP_ENVIRONMENT_ID?: string;
    JIRA_APP_INSTALLATION_URL?: string;
    CONFLUENCE_APP_ID?: string;
    CONFLUENCE_APP_ENVIRONMENT_ID?: string;
    CONFLUENCE_APP_INSTALLATION_URL?: string;
    TRELLO_POWER_UP_API_KEY?: string;
    INTERCOM_CLIENT_ID?: string;
    SALESFORCE_CLIENT_ID?: string;
    GITLAB_CLIENT_ID?: string;
    // Configurable support contact and documentation URL (for self-hosted deployments)
    SUPPORT_EMAIL?: string;
    DOCS_URL?: string;
  }
}

// Re-export the augmented EnvConfig type
export type EnvConfig = BaseEnvConfig;

/**
 * Get configuration from runtime environment or fallback to build-time values
 */
export function getConfig(): EnvConfig {
  // In development, use build-time VITE environment variables
  if (import.meta.env.DEV) {
    return {
      AMPLITUDE_API_KEY: import.meta.env.VITE_AMPLITUDE_API_KEY,
      NEW_RELIC_LICENSE_KEY: import.meta.env.VITE_NEW_RELIC_LICENSE_KEY,
      NEW_RELIC_APPLICATION_ID: import.meta.env.VITE_NEW_RELIC_APPLICATION_ID,
      NEW_RELIC_ACCOUNT_ID: import.meta.env.VITE_NEW_RELIC_ACCOUNT_ID,
      NEW_RELIC_TRUST_KEY: import.meta.env.VITE_NEW_RELIC_TRUST_KEY,
      NEW_RELIC_AGENT_ID: import.meta.env.VITE_NEW_RELIC_AGENT_ID,
      WORKOS_CLIENT_ID: import.meta.env.VITE_WORKOS_CLIENT_ID,
      SSO_ALLOWED_PARENT_ORIGINS: import.meta.env.VITE_SSO_ALLOWED_PARENT_ORIGINS,
      WORKOS_API_HOSTNAME: import.meta.env.VITE_WORKOS_API_HOSTNAME,
      POSTHOG_API_KEY: import.meta.env.VITE_POSTHOG_API_KEY,
      POSTHOG_HOST: import.meta.env.VITE_POSTHOG_HOST,
      POSTHOG_UI_HOST: import.meta.env.VITE_POSTHOG_UI_HOST,
      BASE_DOMAIN: import.meta.env.VITE_BASE_DOMAIN,
      FRONTEND_URL: import.meta.env.VITE_FRONTEND_URL,
      ENVIRONMENT: import.meta.env.NODE_ENV,
      MCP_BASE_URL: import.meta.env.VITE_MCP_BASE_URL,
      JIRA_APP_ID: import.meta.env.VITE_JIRA_APP_ID,
      JIRA_APP_ENVIRONMENT_ID: import.meta.env.VITE_JIRA_APP_ENVIRONMENT_ID,
      JIRA_APP_INSTALLATION_URL: import.meta.env.VITE_JIRA_APP_INSTALLATION_URL,
      CONFLUENCE_APP_ID: import.meta.env.VITE_CONFLUENCE_APP_ID,
      CONFLUENCE_APP_INSTALLATION_URL: import.meta.env.VITE_CONFLUENCE_APP_INSTALLATION_URL,
      CONFLUENCE_APP_ENVIRONMENT_ID: import.meta.env.VITE_CONFLUENCE_APP_ENVIRONMENT_ID,
      TRELLO_POWER_UP_API_KEY: import.meta.env.VITE_TRELLO_POWER_UP_API_KEY,
      INTERCOM_CLIENT_ID: import.meta.env.VITE_INTERCOM_CLIENT_ID,
      SALESFORCE_CLIENT_ID: import.meta.env.VITE_SALESFORCE_CLIENT_ID,
      GITLAB_CLIENT_ID: import.meta.env.VITE_GITLAB_CLIENT_ID,
      SUPPORT_EMAIL: import.meta.env.VITE_SUPPORT_EMAIL,
      DOCS_URL: import.meta.env.VITE_DOCS_URL,
    };
  }

  // In production/staging, use runtime config injected at container startup
  return window.__ENV_CONFIG__ || {};
}
