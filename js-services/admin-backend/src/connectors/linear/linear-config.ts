import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isLinearComplete = (config: Record<ConfigKey, ConfigValue>) => {
  // Linear supports both OAuth (new) and API key (legacy) authentication
  // OAuth method: Check for access token
  const linearAccessToken = configString(config.LINEAR_ACCESS_TOKEN);
  const hasOAuthToken = linearAccessToken.trim().length > 10;

  // Legacy API key method: Check for API key and webhook secret
  const linearApiKey = configString(config.LINEAR_API_KEY);
  const linearWebhookSecret = configString(config.LINEAR_WEBHOOK_SECRET);
  const hasLegacyAuth = linearApiKey.trim().length > 10 && linearWebhookSecret.trim().length > 0;

  // Linear is connected if either OAuth OR legacy API key is configured
  return hasOAuthToken || hasLegacyAuth;
};

export { isLinearComplete };
