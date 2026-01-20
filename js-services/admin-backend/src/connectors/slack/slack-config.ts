import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isSlackBotConfigured = (config: Record<ConfigKey, ConfigValue>): boolean => {
  const signingSecret = configString(config.SLACK_SIGNING_SECRET);
  const botToken = configString(config.SLACK_BOT_TOKEN);

  const signingSecretValid = /^[a-fA-F0-9]{32}$/.test(signingSecret.trim());
  const botTokenValid = botToken.trim().startsWith('xoxb-') && botToken.trim().length > 10;

  return signingSecretValid && botTokenValid;
};

const hasExports = (config: Record<ConfigKey, ConfigValue>): boolean => {
  const slackExportsJson = configString(config.SLACK_EXPORTS_UPLOADED);

  try {
    const parsed = JSON.parse(slackExportsJson);
    return Array.isArray(parsed) && parsed.length > 0;
  } catch (_e) {
    return false;
  }
};

const isSlackComplete = (config: Record<ConfigKey, ConfigValue>) =>
  hasExports(config) && isSlackBotConfigured(config);

export { isSlackComplete };
