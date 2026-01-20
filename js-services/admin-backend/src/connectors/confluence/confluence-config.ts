import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isConfluenceComplete = (config: Record<ConfigKey, ConfigValue>) => {
  const cloudId = configString(config.CONFLUENCE_CLOUD_ID);
  const webtriggerUrl = configString(config.CONFLUENCE_WEBTRIGGER_BACKFILL_URL);

  // Check if configuration is complete (has all required config values)
  return !!(cloudId && webtriggerUrl);
};

export { isConfluenceComplete };
