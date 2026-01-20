import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isGatherComplete = (config: Record<ConfigKey, ConfigValue>) => {
  // Gather is complete if both API key and webhook secret are valid
  const gatherApiKey = configString(config.GATHER_API_KEY);
  const gatherWebhookSecret = configString(config.GATHER_WEBHOOK_SECRET);
  const apiKeyValid = gatherApiKey.trim().length > 10;
  const webhookSecretValid = gatherWebhookSecret.trim().length > 0;
  return apiKeyValid && webhookSecretValid;
};

export { isGatherComplete };
