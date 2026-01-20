import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isNotionComplete = (config: Record<ConfigKey, ConfigValue>) => {
  // Notion is complete if token is valid, webhook is verified, and user clicked "Complete"
  const notionToken = configString(config.NOTION_TOKEN);
  const notionWebhookSecret = configString(config.NOTION_WEBHOOK_SECRET);
  const notionComplete = configString(config.NOTION_COMPLETE);

  const tokenValid = notionToken.trim().startsWith('ntn_') && notionToken.trim().length > 10;
  const webhookVerified = notionWebhookSecret.trim().length > 0;

  return tokenValid && webhookVerified && !!notionComplete;
};

export { isNotionComplete };
