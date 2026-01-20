/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_WORKOS_CLIENT_ID: string;
  readonly VITE_WORKOS_API_HOSTNAME: string;
  readonly VITE_AMPLITUDE_API_KEY: string;
  readonly VITE_POSTHOG_API_KEY: string;
  readonly VITE_POSTHOG_HOST: string;
  readonly VITE_POSTHOG_UI_HOST: string;
  readonly VITE_SSO_ALLOWED_PARENT_ORIGINS: string;
  readonly VITE_NEW_RELIC_LICENSE_KEY: string;
  readonly VITE_NEW_RELIC_APPLICATION_ID: string;
  readonly VITE_NEW_RELIC_ACCOUNT_ID: string;
  readonly VITE_NEW_RELIC_TRUST_KEY: string;
  readonly VITE_NEW_RELIC_AGENT_ID: string;
  readonly VITE_BASE_DOMAIN: string;
  readonly VITE_FRONTEND_URL: string;
  readonly VITE_MCP_BASE_URL: string;
  readonly VITE_TRELLO_POWER_UP_API_KEY: string;
  readonly VITE_INTERCOM_CLIENT_ID: string;
  readonly VITE_SALESFORCE_CLIENT_ID: string;
  readonly VITE_GITLAB_CLIENT_ID: string;
  // Add other env variables as needed
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
