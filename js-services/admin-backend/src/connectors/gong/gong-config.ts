import { ConfigKey, ConfigValue } from '../../config/types';
import { configString } from '../common/utils';

const isGongComplete = (config: Record<ConfigKey, ConfigValue>) => {
  const accessToken = configString(config.GONG_ACCESS_TOKEN);
  const apiBaseUrl = configString(config.GONG_API_BASE_URL);

  return Boolean(accessToken && apiBaseUrl);
};

export { isGongComplete };
