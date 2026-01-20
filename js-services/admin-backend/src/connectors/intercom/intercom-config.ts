import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isIntercomComplete = (config: Record<ConfigKey, ConfigValue>) => {
  // Check for Intercom OAuth access token
  const intercomAccessToken = configString(config.INTERCOM_ACCESS_TOKEN);
  return intercomAccessToken.trim().length > 10;
};

export { isIntercomComplete };
