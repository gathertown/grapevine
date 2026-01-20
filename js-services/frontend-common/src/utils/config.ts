/**
 * Runtime configuration accessor for frontend-common
 * Reads from runtime environment config injected at container startup,
 * with fallback to build-time VITE environment variables for local development.
 */

export interface EnvConfig {
  AMPLITUDE_API_KEY?: string;
  POSTHOG_API_KEY?: string;
  POSTHOG_HOST?: string;
  POSTHOG_UI_HOST?: string;
  MCP_BASE_URL?: string;
  SUPPORT_EMAIL?: string;
  DOCS_URL?: string;
}

// Extend the Window interface to include our runtime config
declare global {
  interface Window {
    __ENV_CONFIG__?: EnvConfig;
  }
}

/**
 * Get configuration from runtime environment or fallback to build-time values
 */
export function getConfig(): EnvConfig {
  // In development, use build-time VITE environment variables
  if (import.meta.env.DEV) {
    return {
      AMPLITUDE_API_KEY: import.meta.env.VITE_AMPLITUDE_API_KEY,
      POSTHOG_API_KEY: import.meta.env.VITE_POSTHOG_API_KEY,
      POSTHOG_HOST: import.meta.env.VITE_POSTHOG_HOST,
      POSTHOG_UI_HOST: import.meta.env.VITE_POSTHOG_UI_HOST,
      MCP_BASE_URL: import.meta.env.VITE_MCP_BASE_URL,
      SUPPORT_EMAIL: import.meta.env.VITE_SUPPORT_EMAIL,
      DOCS_URL: import.meta.env.VITE_DOCS_URL,
    };
  }

  // In production/staging, use runtime config injected at container startup
  return window.__ENV_CONFIG__ || {};
}
