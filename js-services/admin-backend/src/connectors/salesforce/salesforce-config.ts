import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isSalesforceComplete = (config: Record<ConfigKey, ConfigValue>) => {
  const refreshToken = configString(config.SALESFORCE_REFRESH_TOKEN);
  const instanceUrl = configString(config.SALESFORCE_INSTANCE_URL);
  const orgId = configString(config.SALESFORCE_ORG_ID);

  return refreshToken.trim().length > 0 && instanceUrl.trim().length > 0 && orgId.trim().length > 0;
};

export { isSalesforceComplete };
