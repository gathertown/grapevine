import { ConfigData, ConnectorStatus } from '../api/config';

/**
 * Jira site URL validation
 */
export const validateJiraSiteUrl = (
  url: string
): { isValid: boolean; normalizedUrl?: string; error?: string } => {
  try {
    const trimmedUrl = url.trim();

    if (!trimmedUrl) {
      return { isValid: false, error: 'Please enter a Jira site URL' };
    }

    // Pattern 1: https://[site-id].atlassian.net
    const httpsPattern = /^https:\/\/([a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9])\.atlassian\.net$/;
    const httpsMatch = trimmedUrl.match(httpsPattern);
    if (httpsMatch) {
      return { isValid: true, normalizedUrl: trimmedUrl };
    }

    // Pattern 2: [site-id].atlassian.net
    const domainPattern = /^([a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9])\.atlassian\.net$/;
    const domainMatch = trimmedUrl.match(domainPattern);
    if (domainMatch) {
      return { isValid: true, normalizedUrl: `https://${trimmedUrl}` };
    }

    return {
      isValid: false,
      error: 'Please enter a valid Jira site URL (e.g., acme.atlassian.net)',
    };
  } catch (_error) {
    return { isValid: false, error: 'Invalid URL format' };
  }
};

/**
 * Confluence site URL validation
 */
export const validateConfluenceSiteUrl = (
  url: string
): { isValid: boolean; normalizedUrl?: string; error?: string } => {
  try {
    const trimmedUrl = url.trim();

    if (!trimmedUrl) {
      return { isValid: false, error: 'Please enter a Confluence site URL' };
    }

    // Pattern 1: https://[site-id].atlassian.net
    const httpsPattern = /^https:\/\/([a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9])\.atlassian\.net$/;
    const httpsMatch = trimmedUrl.match(httpsPattern);
    if (httpsMatch) {
      return { isValid: true, normalizedUrl: trimmedUrl };
    }

    // Pattern 2: [site-id].atlassian.net
    const domainPattern = /^([a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9])\.atlassian\.net$/;
    const domainMatch = trimmedUrl.match(domainPattern);
    if (domainMatch) {
      return { isValid: true, normalizedUrl: `https://${trimmedUrl}` };
    }

    return {
      isValid: false,
      error: 'Please enter a valid Confluence site URL (e.g., acme.atlassian.net)',
    };
  } catch (_error) {
    return { isValid: false, error: 'Invalid URL format' };
  }
};

/**
 * Check if Slack bot is fully configured with valid tokens
 * For centralized OAuth flow, we only need bot token and signing secret
 * Bot name is optional and only used for legacy per-tenant apps
 */
export const isSlackBotConfigured = (configData: ConfigData): boolean => {
  const signingSecret = configData.SLACK_SIGNING_SECRET || '';
  const botToken = configData.SLACK_BOT_TOKEN || '';

  const signingSecretValid = /^[a-fA-F0-9]{32}$/.test(signingSecret.trim());
  const botTokenValid = botToken.trim().startsWith('xoxb-') && botToken.trim().length > 10;

  return signingSecretValid && botTokenValid;
};

/**
 * Check if a specific data source is fully configured and complete
 * This uses the same logic as DataSources.tsx to ensure consistency
 */
export const isDataSourceComplete = (source: string, connectorStatus: ConnectorStatus[]): boolean =>
  connectorStatus.find((connectorStatus) => source === connectorStatus.source)?.isComplete ?? false;

/**
 * Get count of completed data sources
 */
export const getCompletedDataSourcesCount = (connectorStatus: ConnectorStatus[]): number => {
  return connectorStatus.reduce((count, { isComplete }) => {
    return isComplete ? count + 1 : count;
  }, 0);
};
