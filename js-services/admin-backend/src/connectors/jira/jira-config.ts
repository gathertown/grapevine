import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isJiraComplete = (config: Record<ConfigKey, ConfigValue>) => {
  const cloudId = configString(config.JIRA_CLOUD_ID);
  const webtriggerUrl = configString(config.JIRA_WEBTRIGGER_BACKFILL_URL);

  // Check if configuration is complete (has all required config values)
  return !!(cloudId && webtriggerUrl);
};

export { isJiraComplete };
